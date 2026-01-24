#!/usr/bin/env python3
"""
BFCL Excel Reporter - 평가 결과 엑셀 취합 모듈

모델별 평가 결과를 직관적인 엑셀 보고서로 생성합니다.
- Sheet 1: Evaluation Criteria (평가 기준)
- Sheet 2: Summary (카테고리별 요약 - Detail 시트와 COUNTIFS 연동)
- Sheet 3: Detail (개별 테스트 케이스 결과 + GT + Pass 여부)
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("openpyxl이 설치되어 있지 않습니다. pip install openpyxl 실행 필요")
    raise

# 스타일 정의 (참고 엑셀 스타일 반영)
HEADER_FILL = PatternFill(start_color="D9E2EC", end_color="D9E2EC", fill_type="solid")
HEADER_FONT = Font(bold=True, size=11)
TITLE_FONT = Font(bold=True, size=12)
PASS_FILL = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
FAIL_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# 에러 타입 → 한국어 설명 매핑
ERROR_TYPE_DESCRIPTIONS = {
    # AST 파싱 관련
    "ast_decoder:decoder_failed": "응답 파싱 실패 - 모델 응답을 함수 호출 형태로 변환할 수 없음",
    
    # 함수명 관련
    "simple_function_checker:wrong_func_name": "함수명 오류 - 호출한 함수명이 Ground Truth와 다름",
    "simple_function_checker:wrong_number_of_functions": "함수 개수 오류 - 호출한 함수 개수가 예상과 다름",
    
    # 파라미터 관련
    "simple_function_checker:missing_required": "필수 파라미터 누락 - required 파라미터가 포함되지 않음",
    "simple_function_checker:unexpected_param": "불필요한 파라미터 - 정의되지 않은 파라미터가 포함됨",
    "simple_function_checker:wrong_param_name": "파라미터명 오류 - 파라미터명이 예상과 다름",
    
    # 타입 관련
    "type_error:simple": "타입 오류 - 파라미터 타입이 예상과 다름 (예: 정수를 문자열로 반환)",
    "type_error:dict": "딕셔너리 타입 오류 - 딕셔너리 파라미터의 구조가 잘못됨",
    "type_error:list": "리스트 타입 오류 - 리스트 파라미터의 타입이 잘못됨",
    "type_error:tuple": "튜플 타입 오류 - 튜플 파라미터의 타입이 잘못됨",
    
    # 값 관련
    "value_error:string": "문자열 값 오류 - 문자열 값이 예상 범위에 없음",
    "value_error:integer": "정수 값 오류 - 정수 값이 예상 범위에 없음",
    "value_error:float": "실수 값 오류 - 실수 값이 예상 범위에 없음",
    "value_error:boolean": "불리언 값 오류 - True/False 값이 예상과 다름",
    "value_error:dict": "딕셔너리 값 오류 - 딕셔너리 값이 예상과 다름",
    "value_error:list": "리스트 값 오류 - 리스트 값이 예상과 다름",
    "value_error:enum": "열거형 값 오류 - 허용된 값 목록에 없음",
    
    # 병렬 함수 호출 관련
    "parallel_function_checker_no_order:wrong_count": "병렬 호출 개수 오류 - 호출한 함수 개수가 예상과 다름",
    "parallel_function_checker_no_order:cannot_find_match": "병렬 호출 매칭 실패 - 기대하는 함수 호출을 찾을 수 없음 (함수명/파라미터 불일치)",
    "parallel_function_checker_enforce_order:wrong_count": "병렬 호출 개수 오류 (순서 검사) - 호출한 함수 개수가 예상과 다름",
    
    # 다중 함수 호출 관련
    "multiple_function_checker:wrong_count": "다중 호출 개수 오류 - 호출한 함수 개수가 예상과 다름",
    
    # 기타
    "no_function_call": "함수 호출 없음 - 모델이 함수를 호출하지 않음",
    "irrelevance:no_function_call": "정상 (함수 호출 안 함) - 불필요한 함수 호출을 올바르게 거부함",
    "relevance:no_function_call": "함수 호출 누락 - 필요한 함수를 호출하지 않음",
}

def get_error_description_kr(error_type: str) -> str:
    """에러 타입에 대한 한국어 설명 반환"""
    if not error_type:
        return ""
    
    # 정확히 일치하는 경우
    if error_type in ERROR_TYPE_DESCRIPTIONS:
        return ERROR_TYPE_DESCRIPTIONS[error_type]
    
    # 부분 일치 검색 (예: "type_error:simple" -> "type_error")
    for key, desc in ERROR_TYPE_DESCRIPTIONS.items():
        if error_type.startswith(key.split(":")[0] + ":"):
            return desc
    
    # 기본값
    return f"기타 오류 - {error_type}"


# BFCL 카테고리 그룹 매핑
CATEGORY_GROUPS = {
    "simple_python": ("Non-Live", "Simple"),
    "simple_java": ("Non-Live", "Simple"),
    "simple_javascript": ("Non-Live", "Simple"),
    "multiple": ("Non-Live", "Multiple"),
    "parallel": ("Non-Live", "Parallel"),
    "parallel_multiple": ("Non-Live", "Parallel Multiple"),
    "irrelevance": ("Non-Live", "Irrelevance"),
    "live_simple": ("Live", "Simple"),
    "live_multiple": ("Live", "Multiple"),
    "live_parallel": ("Live", "Parallel"),
    "live_parallel_multiple": ("Live", "Parallel Multiple"),
    "live_irrelevance": ("Live", "Irrelevance"),
    "live_relevance": ("Live", "Relevance"),
    "multi_turn_base": ("Multi-Turn", "Base"),
    "multi_turn_miss_func": ("Multi-Turn", "Miss Function"),
    "multi_turn_miss_param": ("Multi-Turn", "Miss Parameter"),
    "multi_turn_long_context": ("Multi-Turn", "Long Context"),
    "memory_kv": ("Agentic", "Memory KV"),
    "memory_vector": ("Agentic", "Memory Vector"),
    "memory_rec_sum": ("Agentic", "Memory RecSum"),
    "web_search_base": ("Agentic", "Web Search"),
    "web_search_no_snippet": ("Agentic", "Web Search No Snippet"),
}


def load_bfcl_dataset(category: str) -> tuple[dict, dict]:
    """BFCL 데이터셋에서 prompt와 ground truth 로드"""
    try:
        from bfcl_eval.utils import load_dataset_entry, load_ground_truth_entry
        
        prompts = load_dataset_entry(category, include_prereq=False, include_language_specific_hint=False)
        ground_truths = load_ground_truth_entry(category)
        
        # ID로 인덱싱
        prompt_by_id = {}
        for p in prompts:
            entry_id = p.get("id", "")
            # 질문 추출: question[0][0]["content"]
            question = ""
            if "question" in p and p["question"]:
                if isinstance(p["question"][0], list) and p["question"][0]:
                    question = p["question"][0][0].get("content", "")
                elif isinstance(p["question"][0], dict):
                    question = p["question"][0].get("content", "")
            prompt_by_id[entry_id] = question
        
        gt_by_id = {}
        for g in ground_truths:
            entry_id = g.get("id", "")
            gt_by_id[entry_id] = g.get("ground_truth", [])
        
        return prompt_by_id, gt_by_id
    except Exception as e:
        print(f"Warning: Failed to load BFCL dataset for {category}: {e}")
        return {}, {}


class BFCLExcelReporter:
    """BFCL 평가 결과 엑셀 보고서 생성기"""

    def __init__(self, model_name: str, result_dir: Path, score_dir: Path):
        self.model_name = model_name
        self.result_dir = result_dir
        self.score_dir = score_dir
        self.wb = Workbook()
        self.detail_data = []  # 상세 결과 (score 파일에서 로드)
        self.categories_found = set()  # 발견된 카테고리 목록

    def load_data(self) -> None:
        """score 및 result 파일에서 데이터 로드"""
        # 1. Score 파일에서 실패한 항목 로드
        for subdir in ["non_live", "live", "multi_turn", "agentic"]:
            subdir_path = self.score_dir / subdir
            if not subdir_path.exists():
                continue
            
            for score_file in subdir_path.glob("*_score.json"):
                category = self._extract_category(score_file.name)
                self._load_score_file(score_file, category, subdir)
        
        # 2. Result 파일에서 모든 항목 로드 (score에 없는 항목은 PASS)
        self._load_result_files()

    def _extract_category(self, filename: str) -> str:
        """파일명에서 카테고리 추출: BFCL_v4_simple_python_score.json -> simple_python"""
        name = filename.replace("_score.json", "").replace("_result.json", "")
        if name.startswith("BFCL_v"):
            parts = name.split("_", 2)
            if len(parts) > 2:
                return parts[2]
        return name

    def _load_result_files(self) -> None:
        """Result 파일에서 모든 테스트 케이스 로드 (score에 없는 항목은 PASS)"""
        # 이미 로드된 ID 목록
        loaded_ids = {entry["id"] for entry in self.detail_data}
        
        for subdir in ["non_live", "live", "multi_turn", "agentic"]:
            subdir_path = self.result_dir / subdir
            if not subdir_path.exists():
                continue
            
            for result_file in subdir_path.glob("*_result.json"):
                category = self._extract_category(result_file.name)
                self._load_result_file(result_file, category, loaded_ids)
        
        # 모든 데이터에 대해 BFCL 데이터셋에서 질문과 GT 보강
        self._enrich_with_bfcl_dataset()

    def _enrich_with_bfcl_dataset(self) -> None:
        """BFCL 데이터셋에서 실제 질문과 Ground Truth 가져오기"""
        # 카테고리별로 데이터셋 로드
        dataset_cache = {}
        
        for entry in self.detail_data:
            category = entry["category"]
            entry_id = entry["id"]
            
            # 캐시에 없으면 로드
            if category not in dataset_cache:
                prompt_by_id, gt_by_id = load_bfcl_dataset(category)
                dataset_cache[category] = (prompt_by_id, gt_by_id)
            
            prompt_by_id, gt_by_id = dataset_cache[category]
            
            # 실제 질문 업데이트
            if entry_id in prompt_by_id:
                entry["request"] = prompt_by_id[entry_id]
            else:
                entry["request"] = ""
            
            # Ground Truth 업데이트
            if entry_id in gt_by_id and not entry.get("expected"):
                gt = gt_by_id[entry_id]
                entry["expected"] = self._format_ground_truth(gt)

    def _format_ground_truth(self, gt: list) -> str:
        """Ground Truth 포맷팅"""
        if not gt:
            return ""
        try:
            # 함수 호출 형태로 변환
            result_parts = []
            for item in gt:
                if isinstance(item, dict):
                    for func_name, params in item.items():
                        # params에서 첫 번째 값 추출 (리스트 형태)
                        clean_params = {}
                        for k, v in params.items():
                            if isinstance(v, list) and v:
                                clean_params[k] = v[0]
                            else:
                                clean_params[k] = v
                        result_parts.append(f"{func_name}({clean_params})")
            return "; ".join(result_parts)[:300]
        except:
            return json.dumps(gt, ensure_ascii=False)[:300]

    def _load_result_file(self, filepath: Path, category: str, loaded_ids: set) -> None:
        """Result 파일 로드 - score에 없는 항목은 PASS로 표시"""
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line.strip())
                    entry_id = entry.get("id", "")
                    
                    # 이미 score 파일에서 로드된 항목은 건너뜀
                    if entry_id in loaded_ids:
                        continue
                    
                    self.categories_found.add(category)
                    
                    # Score 파일에 없으면 PASS (실패한 항목만 score에 기록됨)
                    self.detail_data.append({
                        "id": entry_id,
                        "category": category,
                        "group": CATEGORY_GROUPS.get(category, ("Unknown", "Unknown"))[0],
                        "type": CATEGORY_GROUPS.get(category, ("Unknown", "Unknown"))[1],
                        "valid": True,
                        "result": "PASS",
                        "request": "",  # 나중에 _enrich_with_bfcl_dataset에서 채움
                        "query": entry_id,
                        "expected": "",  # 나중에 _enrich_with_bfcl_dataset에서 채움
                        "actual": self._format_actual_from_result(entry),
                        "error": [],
                        "error_type": "",
                    })
                except json.JSONDecodeError:
                    continue

    def _format_actual_from_result(self, entry: dict) -> str:
        """Result 파일에서 모델 응답 포맷팅 - 파싱된 함수 호출 형식으로 변환"""
        result = entry.get("result", "")
        return self._format_model_response(result)
    
    def _format_model_response(self, result) -> str:
        """모델 응답을 함수 호출 형식으로 포맷팅"""
        if isinstance(result, list):
            # 이미 파싱된 형태: [{"func_name": {"param": value}}, ...]
            try:
                parts = []
                for item in result:
                    if isinstance(item, dict):
                        for func_name, params in item.items():
                            if isinstance(params, str):
                                # JSON 문자열인 경우 파싱
                                try:
                                    params = json.loads(params)
                                except:
                                    pass
                            if isinstance(params, dict):
                                parts.append(f"{func_name}({params})")
                            else:
                                parts.append(f"{func_name}({params})")
                return "; ".join(parts)[:300] if parts else str(result)[:300]
            except:
                return str(result)[:300]
        elif isinstance(result, str):
            # 문자열인 경우 파싱 시도
            parsed = self._try_parse_tool_calls(result)
            if parsed:
                return self._format_model_response(parsed)
            return result[:300]
        elif isinstance(result, dict):
            try:
                return json.dumps(result, ensure_ascii=False)[:300]
            except:
                return str(result)[:300]
        return str(result)[:300]
    
    def _try_parse_tool_calls(self, text: str) -> list:
        """텍스트에서 tool calls 파싱 시도"""
        import re
        text = text.strip()
        
        # [TOOL_CALLS] 태그 제거
        if text.startswith("[TOOL_CALLS]"):
            text = text[len("[TOOL_CALLS]"):].strip()
        if text.startswith("[TOOL_CALLS"):
            text = re.sub(r'^\[TOOL_CALLS\]?', '', text)
        
        # JSON 배열 파싱 시도
        try:
            if text.startswith("["):
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    result = []
                    for item in parsed:
                        if isinstance(item, dict):
                            if "name" in item and "arguments" in item:
                                func_name = item["name"]
                                args = item["arguments"]
                                if isinstance(args, str):
                                    args = json.loads(args)
                                result.append({func_name: args})
                            elif len(item) == 1:
                                result.append(item)
                    if result:
                        return result
        except:
            pass
        
        # func_name{...} 형식 파싱
        pattern = r'([a-zA-Z_][a-zA-Z0-9_\.]*)\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
        matches = re.findall(pattern, text)
        if matches:
            result = []
            for func_name, json_str in matches:
                try:
                    params = json.loads(json_str.replace("'", '"'))
                    result.append({func_name: params})
                except:
                    continue
            if result:
                return result
        
        return None

    def _load_score_file(self, filepath: Path, category: str, subdir: str) -> None:
        """score 파일 로드 - 첫 줄은 요약, 나머지는 개별 결과"""
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        if not lines:
            return
        
        self.categories_found.add(category)
        
        # 나머지: 개별 결과
        for line in lines[1:]:
            if not line.strip():
                continue
            try:
                entry = json.loads(line.strip())
                entry_id = entry.get("id", "")
                request_text = self._extract_request(entry)  # 실제 질문
                self.detail_data.append({
                    "id": entry_id,
                    "category": category,
                    "group": CATEGORY_GROUPS.get(category, ("Unknown", "Unknown"))[0],
                    "type": CATEGORY_GROUPS.get(category, ("Unknown", "Unknown"))[1],
                    "valid": entry.get("valid", False),
                    "result": "PASS" if entry.get("valid", False) else "FAIL",
                    "query": entry_id,  # ID
                    "request": request_text,  # 실제 질문 (score 파일의 prompt.question에서)
                    "expected": self._format_expected(entry),
                    "actual": self._format_actual(entry),
                    "error": entry.get("error", []),
                    "error_type": entry.get("error_type", ""),
                })
            except json.JSONDecodeError:
                continue

    def _extract_request(self, entry: dict) -> str:
        """실제 질문 추출 (score 파일의 prompt.question에서)"""
        prompt = entry.get("prompt", {})
        question = prompt.get("question", [])
        if question and isinstance(question, list) and len(question) > 0:
            if isinstance(question[0], list) and len(question[0]) > 0:
                first_msg = question[0][0]
                if isinstance(first_msg, dict):
                    return first_msg.get("content", "")[:300]
            elif isinstance(question[0], dict):
                return question[0].get("content", "")[:300]
        return ""

    def _format_expected(self, entry: dict) -> str:
        """Ground Truth 포맷팅"""
        possible_answer = entry.get("possible_answer", [])
        if possible_answer:
            try:
                return json.dumps(possible_answer[0], ensure_ascii=False)[:200]
            except:
                return str(possible_answer)[:200]
        return ""

    def _format_actual(self, entry: dict) -> str:
        """모델 응답 포맷팅 - 파싱된 함수 호출 형식으로 변환"""
        raw = entry.get("model_result_raw", "")
        return self._format_model_response(raw)

    def create_evaluation_criteria_sheet(self) -> None:
        """Sheet 1: 평가 기준"""
        ws = self.wb.active
        ws.title = "Evaluation Criteria"
        
        # 1. 평가 개요
        ws.cell(row=2, column=2, value="1. 평가 개요").font = TITLE_FONT
        
        criteria = [
            ("벤치마크", "Berkeley Function Calling Leaderboard (BFCL V4)"),
            ("평가 모델", self.model_name),
            ("평가 방식", "AST Matching (Abstract Syntax Tree 기반 함수 호출 검증)"),
            ("평가 일시", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ]
        row = 3
        for key, value in criteria:
            ws.cell(row=row, column=2, value=key).font = Font(bold=True)
            ws.cell(row=row, column=3, value=value)
            row += 1
        
        # 2. AST 평가 방식 설명
        row += 1
        ws.cell(row=row, column=2, value="2. AST 평가 방식").font = TITLE_FONT
        row += 1
        
        ast_desc = [
            ("1) 함수 파싱", "모델 응답을 AST로 파싱하여 함수명과 파라미터 추출"),
            ("2) 함수명 검증", "추출된 함수명이 Ground Truth와 일치하는지 확인"),
            ("3) 파라미터 검증", "각 파라미터의 키와 값이 예상 범위 내에 있는지 확인"),
            ("4) 타입 검증", "파라미터 타입이 함수 스키마와 일치하는지 확인"),
        ]
        for key, value in ast_desc:
            ws.cell(row=row, column=2, value=key).font = Font(bold=True)
            ws.cell(row=row, column=3, value=value)
            row += 1
        
        # 3. Pass 조건
        row += 1
        ws.cell(row=row, column=2, value="3. Pass 조건").font = TITLE_FONT
        row += 1
        
        pass_criteria = [
            ("함수명 일치", "모델이 호출한 함수명이 Ground Truth와 정확히 일치"),
            ("필수 파라미터", "모든 required 파라미터가 포함되어야 함"),
            ("파라미터 값", "각 파라미터 값이 possible_answer 범위 내에 있어야 함"),
            ("타입 일치", "파라미터 타입이 함수 스키마와 일치해야 함"),
        ]
        for key, value in pass_criteria:
            ws.cell(row=row, column=2, value=key).font = Font(bold=True)
            ws.cell(row=row, column=3, value=value)
            row += 1
        
        # 4. Fail 조건 (오류 유형)
        row += 1
        ws.cell(row=row, column=2, value="4. Fail 조건 (오류 유형)").font = TITLE_FONT
        row += 1
        
        fail_criteria = [
            ("ast_decoder:decoder_failed", "모델 응답을 AST로 파싱할 수 없음 (잘못된 형식)"),
            ("simple_function_checker:wrong_func_name", "호출한 함수명이 Ground Truth와 다름"),
            ("simple_function_checker:missing_required", "필수 파라미터가 누락됨"),
            ("simple_function_checker:unexpected_param", "예상치 못한 파라미터가 포함됨"),
            ("type_error:simple", "파라미터 타입이 예상과 다름"),
            ("value_error:string", "문자열 값이 예상 범위에 없음"),
        ]
        for key, value in fail_criteria:
            ws.cell(row=row, column=2, value=key).font = Font(bold=True, color="C53030")
            ws.cell(row=row, column=3, value=value)
            row += 1
        
        # 5. 참고 링크
        row += 1
        ws.cell(row=row, column=2, value="5. 참고").font = TITLE_FONT
        row += 1
        ws.cell(row=row, column=2, value="공식 문서")
        ws.cell(row=row, column=3, value="https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html")
        
        # 열 너비 조정
        ws.column_dimensions["B"].width = 30
        ws.column_dimensions["C"].width = 70

    def create_detail_sheet(self) -> None:
        """Sheet 3: 상세 결과 (GT, 모델 응답, Pass 여부) - Summary보다 먼저 생성"""
        ws = self.wb.create_sheet("Detail")
        
        # 헤더 - Request (실제 질문) 컬럼 및 한국어 설명 컬럼 추가
        headers = ["#", "Result", "Category", "Type", "Query", "Request", "Expected (GT)", "Actual (Model)", "Error Type", "실패 원인 (한국어)"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center")
            cell.border = THIN_BORDER
        
        # 데이터
        row = 2
        for idx, entry in enumerate(sorted(self.detail_data, key=lambda x: (x["category"], x["id"])), 1):
            ws.cell(row=row, column=1, value=idx).border = THIN_BORDER
            
            result_cell = ws.cell(row=row, column=2, value=entry["result"])
            result_cell.border = THIN_BORDER
            result_cell.alignment = Alignment(horizontal="center")
            if entry["result"] == "PASS":
                result_cell.fill = PASS_FILL
            else:
                result_cell.fill = FAIL_FILL
            
            ws.cell(row=row, column=3, value=entry["category"]).border = THIN_BORDER
            ws.cell(row=row, column=4, value=entry["type"]).border = THIN_BORDER
            ws.cell(row=row, column=5, value=entry["query"]).border = THIN_BORDER
            ws.cell(row=row, column=6, value=entry.get("request", "")).border = THIN_BORDER  # Request (실제 질문)
            ws.cell(row=row, column=7, value=entry["expected"]).border = THIN_BORDER  # Expected (GT)
            ws.cell(row=row, column=8, value=entry["actual"]).border = THIN_BORDER
            ws.cell(row=row, column=9, value=entry.get("error_type", "")).border = THIN_BORDER
            
            # 한국어 실패 원인 설명
            error_type = entry.get("error_type", "")
            error_desc_kr = get_error_description_kr(error_type) if error_type else ""
            error_desc_cell = ws.cell(row=row, column=10, value=error_desc_kr)
            error_desc_cell.border = THIN_BORDER
            if error_type:
                error_desc_cell.fill = FAIL_FILL  # 실패한 경우 빨간 배경
            
            row += 1
        
        # 열 너비 조정
        ws.column_dimensions["A"].width = 5
        ws.column_dimensions["B"].width = 8
        ws.column_dimensions["C"].width = 20
        ws.column_dimensions["D"].width = 12
        ws.column_dimensions["E"].width = 18
        ws.column_dimensions["F"].width = 55  # Request (실제 질문)
        ws.column_dimensions["G"].width = 45  # Expected (GT)
        ws.column_dimensions["H"].width = 50  # Actual (Model)
        ws.column_dimensions["I"].width = 25  # Error Type
        ws.column_dimensions["J"].width = 50  # 실패 원인 (한국어)

    def create_summary_sheet(self) -> None:
        """Sheet 2: 요약 (BFCL 공식 Score 형식 - Detail 시트 연동)"""
        ws = self.wb.create_sheet("Summary", 1)  # 두 번째 위치에 삽입
        
        # 모델명
        ws.cell(row=1, column=1, value="Model").font = Font(bold=True)
        ws.cell(row=1, column=2, value=self.model_name)
        
        # 헤더 - BFCL 공식 형식
        headers = ["Category", "Type", "Total", "Correct", "Incorrect", "Accuracy"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col, value=header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center")
            cell.border = THIN_BORDER
        
        # 데이터 (Detail 시트 참조 수식 사용)
        row = 4
        data_start_row = row
        sorted_categories = sorted(self.categories_found)
        num_categories = len(sorted_categories)
        
        for category in sorted_categories:
            group_info = CATEGORY_GROUPS.get(category, ("Unknown", "Unknown"))
            
            ws.cell(row=row, column=1, value=category).border = THIN_BORDER
            ws.cell(row=row, column=2, value=group_info[1]).border = THIN_BORDER
            
            # Total: Detail 시트에서 해당 카테고리 개수 (COUNTIF)
            total_formula = f'=COUNTIF(Detail!C:C,A{row})'
            ws.cell(row=row, column=3, value=total_formula).border = THIN_BORDER
            
            # Correct (Pass): Detail 시트에서 해당 카테고리이면서 PASS인 개수 (COUNTIFS)
            pass_formula = f'=COUNTIFS(Detail!C:C,A{row},Detail!B:B,"PASS")'
            ws.cell(row=row, column=4, value=pass_formula).border = THIN_BORDER
            
            # Incorrect (Fail): Detail 시트에서 해당 카테고리이면서 FAIL인 개수 (COUNTIFS)
            fail_formula = f'=COUNTIFS(Detail!C:C,A{row},Detail!B:B,"FAIL")'
            ws.cell(row=row, column=5, value=fail_formula).border = THIN_BORDER
            
            # Accuracy 수식 (BFCL: correct / total)
            acc_cell = ws.cell(row=row, column=6, value=f"=IF(C{row}=0,0,D{row}/C{row})")
            acc_cell.number_format = "0.00%"
            acc_cell.border = THIN_BORDER
            
            row += 1
        
        data_end_row = row - 1
        
        # TOTAL 행 (합계)
        ws.cell(row=row, column=1, value="").border = THIN_BORDER
        total_cell = ws.cell(row=row, column=2, value="TOTAL")
        total_cell.font = Font(bold=True)
        total_cell.border = THIN_BORDER
        
        ws.cell(row=row, column=3, value=f"=SUM(C{data_start_row}:C{data_end_row})").border = THIN_BORDER
        ws.cell(row=row, column=3).font = Font(bold=True)
        
        ws.cell(row=row, column=4, value=f"=SUM(D{data_start_row}:D{data_end_row})").border = THIN_BORDER
        ws.cell(row=row, column=4).font = Font(bold=True)
        
        ws.cell(row=row, column=5, value=f"=SUM(E{data_start_row}:E{data_end_row})").border = THIN_BORDER
        ws.cell(row=row, column=5).font = Font(bold=True)
        
        # Weighted Accuracy (전체 Correct / 전체 Total)
        weighted_acc_cell = ws.cell(row=row, column=6, value=f"=IF(C{row}=0,0,D{row}/C{row})")
        weighted_acc_cell.number_format = "0.00%"
        weighted_acc_cell.font = Font(bold=True)
        weighted_acc_cell.border = THIN_BORDER
        
        row += 1
        
        # Overall Accuracy 행 (BFCL 공식: unweighted average of category accuracies)
        ws.cell(row=row, column=1, value="").border = THIN_BORDER
        overall_cell = ws.cell(row=row, column=2, value="Overall Acc")
        overall_cell.font = Font(bold=True, color="0000FF")
        overall_cell.border = THIN_BORDER
        
        ws.cell(row=row, column=3, value="(BFCL)").border = THIN_BORDER
        ws.cell(row=row, column=4, value="").border = THIN_BORDER
        ws.cell(row=row, column=5, value="").border = THIN_BORDER
        
        # Overall Accuracy = AVERAGE of each category's accuracy (unweighted)
        # BFCL 공식: "Overall Accuracy is the unweighted average of all the sub-categories"
        overall_acc_formula = f"=AVERAGE(F{data_start_row}:F{data_end_row})"
        overall_acc_cell = ws.cell(row=row, column=6, value=overall_acc_formula)
        overall_acc_cell.number_format = "0.00%"
        overall_acc_cell.font = Font(bold=True, color="0000FF")
        overall_acc_cell.border = THIN_BORDER
        overall_acc_cell.fill = PatternFill(start_color="E6F3FF", end_color="E6F3FF", fill_type="solid")
        
        # 열 너비 조정
        ws.column_dimensions["A"].width = 25
        ws.column_dimensions["B"].width = 20
        ws.column_dimensions["C"].width = 10
        ws.column_dimensions["D"].width = 10
        ws.column_dimensions["E"].width = 10
        ws.column_dimensions["F"].width = 12

    def save(self, output_path: Optional[Path] = None) -> Path:
        """엑셀 파일 저장"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self.model_name.replace("/", "_").replace("\\", "_")
            output_path = self.score_dir / f"{safe_name}_eval_report_{timestamp}.xlsx"
        
        self.wb.save(output_path)
        return output_path

    def generate_report(self) -> Path:
        """전체 보고서 생성"""
        self.load_data()
        self.create_evaluation_criteria_sheet()
        self.create_detail_sheet()  # Detail 먼저 생성 (Summary에서 참조)
        self.create_summary_sheet()
        return self.save()


def generate_excel_report(model_name: str, result_dir: str, score_dir: str) -> str:
    """외부 호출용 함수"""
    reporter = BFCLExcelReporter(
        model_name=model_name,
        result_dir=Path(result_dir),
        score_dir=Path(score_dir),
    )
    return str(reporter.generate_report())


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="BFCL 평가 결과 엑셀 보고서 생성")
    parser.add_argument("--model", required=True, help="모델명")
    parser.add_argument("--result-dir", required=True, help="결과 디렉토리")
    parser.add_argument("--score-dir", required=True, help="점수 디렉토리")
    parser.add_argument("--output", help="출력 파일 경로 (선택)")
    
    args = parser.parse_args()
    
    output = generate_excel_report(args.model, args.result_dir, args.score_dir)
    print(f"보고서 생성 완료: {output}")
