"""
OpenRouter API Handler for BFCL Evaluation.

This handler supports multiple models via OpenRouter's unified API:
- meta-llama/llama-3.3-70b-instruct
- mistralai/mistral-small-3.2-24b-instruct
- qwen/qwen3-32b
- qwen/qwen3-14b
- qwen/qwen3-next-80b-a3b-instruct

OpenRouter uses OpenAI-compatible API format.
"""

import json
import os
import re
import time
from typing import Any

from bfcl_eval.constants.enums import ModelStyle
from bfcl_eval.constants.type_mappings import GORILLA_TO_OPENAPI
from bfcl_eval.model_handler.base_handler import BaseHandler
from bfcl_eval.model_handler.utils import (
    convert_to_function_call,
    convert_to_tool,
    default_decode_ast_prompting,
    default_decode_execute_prompting,
    format_execution_results_prompting,
    retry_with_backoff,
    system_prompt_pre_processing_chat_model,
)
from openai import OpenAI, RateLimitError, APIError


class OpenRouterHandler(BaseHandler):
    """
    Handler for OpenRouter API.
    
    OpenRouter provides a unified API for accessing various LLM models.
    It uses OpenAI-compatible API format.
    """

    def __init__(
        self,
        model_name,
        temperature,
        registry_name,
        is_fc_model,
        delay: float = 1.0,
        **kwargs,
    ) -> None:
        super().__init__(model_name, temperature, registry_name, is_fc_model, **kwargs)
        self.model_style = ModelStyle.OPENAI_COMPLETIONS
        self.delay = delay  # Delay between API calls in seconds
        
        # Initialize OpenAI client with OpenRouter configuration
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            default_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://github.com/gorilla-llm/gorilla"),
                "X-Title": os.getenv("OPENROUTER_TITLE", "BFCL Evaluation"),
            }
        )

    def _parse_mistral_tool_calls_text(self, text: str) -> list[dict]:
        """
        Parse Mistral's text-based tool call format.
        
        Handles formats like:
        - "[TOOL_CALLSfunc_name{"param": value}]"
        - "[TOOL_CALLS][{"name": "func", "arguments": {...}}]"
        - "func_name{"param": value}"
        - "[{"name": "func", "arguments": {...}}]"
        
        Returns list of dicts in format: [{func_name: {param: value}}, ...]
        """
        text = text.strip()
        
        # Pattern 1: [TOOL_CALLS][{...}] - Mistral standard format
        if text.startswith("[TOOL_CALLS]"):
            text = text[len("[TOOL_CALLS]"):].strip()
            if text.endswith("</s>"):
                text = text[:-len("</s>")].strip()
        
        # Pattern 2: Try parsing as JSON array of {"name": ..., "arguments": ...}
        try:
            # Handle JSON array format
            if text.startswith("["):
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    result = []
                    for item in parsed:
                        # Handle string items (serialized JSON within list)
                        if isinstance(item, str):
                            try:
                                item = json.loads(item)
                            except json.JSONDecodeError:
                                continue
                        
                        if isinstance(item, dict):
                            # Format: {"name": "func", "parameters": {...}} (Llama style)
                            if "name" in item and "parameters" in item:
                                func_name = item["name"]
                                args = item["parameters"]
                                if isinstance(args, str):
                                    args = json.loads(args)
                                result.append({func_name: args})
                            # Format: {"name": "func", "arguments": {...}} (OpenAI style)
                            elif "name" in item and "arguments" in item:
                                func_name = item["name"]
                                args = item["arguments"]
                                if isinstance(args, str):
                                    args = json.loads(args)
                                result.append({func_name: args})
                            elif len(item) == 1:
                                # Already in {func_name: {params}} format
                                result.append(item)
                    if result:
                        return result
        except json.JSONDecodeError:
            pass
        
        # Pattern 3: func_name{...} or [TOOL_CALLSfunc_name{...}
        # Remove [TOOL_CALLS prefix if present (without closing bracket)
        text = re.sub(r'^\[TOOL_CALLS\]?', '', text)
        
        # Try to extract function calls in format: func_name{"param": value}
        # This regex matches: function_name{json_object}
        pattern = r'([a-zA-Z_][a-zA-Z0-9_\.]*)\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
        matches = re.findall(pattern, text)
        
        if matches:
            result = []
            for func_name, json_str in matches:
                try:
                    # Replace single quotes with double quotes for JSON parsing
                    json_str = json_str.replace("'", '"')
                    params = json.loads(json_str)
                    result.append({func_name: params})
                except json.JSONDecodeError:
                    continue
            if result:
                return result
        
        # Pattern 4: Fall back to default prompting decoder
        raise ValueError(f"Could not parse tool calls from text: {text}")

    def _convert_param_types(self, params: dict) -> dict:
        """
        Convert string values to appropriate types.
        Llama models often return numbers as strings (e.g., "10" instead of 10).
        """
        converted = {}
        for key, value in params.items():
            if isinstance(value, str):
                # Try to convert to int
                try:
                    converted[key] = int(value)
                    continue
                except ValueError:
                    pass
                # Try to convert to float
                try:
                    converted[key] = float(value)
                    continue
                except ValueError:
                    pass
                # Try to convert to boolean
                if value.lower() == "true":
                    converted[key] = True
                    continue
                elif value.lower() == "false":
                    converted[key] = False
                    continue
                # Keep as string
                converted[key] = value
            elif isinstance(value, dict):
                # Recursively convert nested dicts
                converted[key] = self._convert_param_types(value)
            elif isinstance(value, list):
                # Convert list elements
                converted[key] = [
                    self._convert_param_types(v) if isinstance(v, dict) 
                    else (int(v) if isinstance(v, str) and v.isdigit() else v)
                    for v in value
                ]
            else:
                converted[key] = value
        return converted

    def _restore_function_name(self, name: str) -> str:
        """
        Restore function names that were converted by OpenAI API.
        OpenAI API converts '.' to '_' in function names.
        Known module patterns: math_, algebra_, datetime_, os_, sys_, etc.
        """
        # Known module/object prefixes that should have '.' instead of '_'
        known_modules = [
            'math_', 'algebra_', 'datetime_', 'os_', 'sys_', 'json_', 
            're_', 'collections_', 'itertools_', 'functools_', 'operator_',
            'string_', 'random_', 'statistics_', 'decimal_', 'fractions_',
            'numpy_', 'pandas_', 'scipy_', 'sklearn_', 'torch_', 'tf_',
            # Common API/service prefixes
            'spotify_', 'weather_', 'calendar_', 'email_', 'file_',
            'database_', 'api_', 'http_', 'web_', 'user_', 'auth_',
        ]
        
        for module in known_modules:
            if name.startswith(module):
                # Replace only the first underscore with a dot
                return name.replace(module, module[:-1] + '.', 1)
        
        return name

    def decode_ast(self, result, language, has_tool_call_tag):
        if self.is_fc_model:
            # If result is already a list of dicts (from tool_calls API)
            if isinstance(result, list):
                decoded_output = []
                for invoked_function in result:
                    if isinstance(invoked_function, dict):
                        name = list(invoked_function.keys())[0]
                        params = invoked_function[name]
                        # Handle both string and dict arguments
                        if isinstance(params, str):
                            params = json.loads(params)
                        # Restore function name (e.g., math_factorial -> math.factorial)
                        name = self._restore_function_name(name)
                        # Convert parameter types (e.g., "10" -> 10)
                        params = self._convert_param_types(params)
                        decoded_output.append({name: params})
                    else:
                        raise ValueError(f"Expected dict, got {type(invoked_function)}: {invoked_function}")
                return decoded_output
            
            # If result is a string (model returned text instead of tool_calls)
            # This happens when model doesn't properly use tool_calls API
            elif isinstance(result, str):
                # Try parsing Mistral's text-based tool call format
                parsed = self._parse_mistral_tool_calls_text(result)
                # Apply function name restoration and type conversion
                decoded_output = []
                for item in parsed:
                    name = list(item.keys())[0]
                    params = item[name]
                    name = self._restore_function_name(name)
                    params = self._convert_param_types(params)
                    decoded_output.append({name: params})
                return decoded_output
            
            else:
                raise ValueError(f"Unexpected result type: {type(result)}, value: {result}")
        else:
            return default_decode_ast_prompting(result, language, has_tool_call_tag)

    def decode_execute(self, result, has_tool_call_tag):
        if self.is_fc_model:
            return convert_to_function_call(result)
        else:
            return default_decode_execute_prompting(result)

    @retry_with_backoff(error_type=[RateLimitError, APIError], min_wait=10, max_wait=120)
    def generate_with_backoff(self, **kwargs):
        start_time = time.time()
        api_response = self.client.chat.completions.create(**kwargs)
        end_time = time.time()
        
        # Apply delay between API calls
        if self.delay > 0:
            time.sleep(self.delay)

        return api_response, end_time - start_time

    #### FC methods ####

    def _query_FC(self, inference_data: dict):
        message: list[dict] = inference_data["message"]
        tools = inference_data["tools"]
        inference_data["inference_input_log"] = {"message": repr(message), "tools": tools}

        kwargs = {
            "messages": message,
            "model": self.model_name,
            "temperature": self.temperature,
        }

        if len(tools) > 0:
            kwargs["tools"] = tools

        return self.generate_with_backoff(**kwargs)

    def _pre_query_processing_FC(self, inference_data: dict, test_entry: dict) -> dict:
        inference_data["message"] = []
        return inference_data

    def _compile_tools(self, inference_data: dict, test_entry: dict) -> dict:
        functions: list = test_entry["function"]

        tools = convert_to_tool(functions, GORILLA_TO_OPENAPI, self.model_style)

        inference_data["tools"] = tools

        return inference_data

    def _parse_query_response_FC(self, api_response: Any) -> dict:
        try:
            tool_calls = api_response.choices[0].message.tool_calls
            if tool_calls:
                model_responses = []
                tool_call_ids = []
                for func_call in tool_calls:
                    # Handle arguments that might be string or already parsed dict
                    args = func_call.function.arguments
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    model_responses.append({func_call.function.name: args})
                    tool_call_ids.append(func_call.id)
            else:
                model_responses = api_response.choices[0].message.content
                tool_call_ids = []
        except Exception:
            model_responses = api_response.choices[0].message.content
            tool_call_ids = []

        model_responses_message_for_chat_history = api_response.choices[0].message

        return {
            "model_responses": model_responses,
            "model_responses_message_for_chat_history": model_responses_message_for_chat_history,
            "tool_call_ids": tool_call_ids,
            "input_token": api_response.usage.prompt_tokens if api_response.usage else 0,
            "output_token": api_response.usage.completion_tokens if api_response.usage else 0,
        }

    def add_first_turn_message_FC(
        self, inference_data: dict, first_turn_message: list[dict]
    ) -> dict:
        inference_data["message"].extend(first_turn_message)
        return inference_data

    def _add_next_turn_user_message_FC(
        self, inference_data: dict, user_message: list[dict]
    ) -> dict:
        inference_data["message"].extend(user_message)
        return inference_data

    def _add_assistant_message_FC(
        self, inference_data: dict, model_response_data: dict
    ) -> dict:
        inference_data["message"].append(
            model_response_data["model_responses_message_for_chat_history"]
        )
        return inference_data

    def _add_execution_results_FC(
        self,
        inference_data: dict,
        execution_results: list[str],
        model_response_data: dict,
    ) -> dict:
        # Add the execution results to the current round result, one at a time
        for execution_result, tool_call_id in zip(
            execution_results, model_response_data["tool_call_ids"]
        ):
            tool_message = {
                "role": "tool",
                "content": execution_result,
                "tool_call_id": tool_call_id,
            }
            inference_data["message"].append(tool_message)

        return inference_data

    #### Prompting methods ####

    def _query_prompting(self, inference_data: dict):
        inference_data["inference_input_log"] = {"message": repr(inference_data["message"])}

        return self.generate_with_backoff(
            messages=inference_data["message"],
            model=self.model_name,
            temperature=self.temperature,
        )

    def _pre_query_processing_prompting(self, test_entry: dict) -> dict:
        functions: list = test_entry["function"]
        test_entry_id: str = test_entry["id"]

        test_entry["question"][0] = system_prompt_pre_processing_chat_model(
            test_entry["question"][0], functions, test_entry_id
        )

        return {"message": []}

    def _parse_query_response_prompting(self, api_response: Any) -> dict:
        return {
            "model_responses": api_response.choices[0].message.content,
            "model_responses_message_for_chat_history": api_response.choices[0].message,
            "input_token": api_response.usage.prompt_tokens if api_response.usage else 0,
            "output_token": api_response.usage.completion_tokens if api_response.usage else 0,
        }

    def add_first_turn_message_prompting(
        self, inference_data: dict, first_turn_message: list[dict]
    ) -> dict:
        inference_data["message"].extend(first_turn_message)
        return inference_data

    def _add_next_turn_user_message_prompting(
        self, inference_data: dict, user_message: list[dict]
    ) -> dict:
        inference_data["message"].extend(user_message)
        return inference_data

    def _add_assistant_message_prompting(
        self, inference_data: dict, model_response_data: dict
    ) -> dict:
        inference_data["message"].append(
            model_response_data["model_responses_message_for_chat_history"]
        )
        return inference_data

    def _add_execution_results_prompting(
        self, inference_data: dict, execution_results: list[str], model_response_data: dict
    ) -> dict:
        formatted_results_message = format_execution_results_prompting(
            inference_data, execution_results, model_response_data
        )
        inference_data["message"].append(
            {"role": "user", "content": formatted_results_message}
        )

        return inference_data
