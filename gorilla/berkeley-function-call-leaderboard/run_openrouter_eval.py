#!/usr/bin/env python3
"""
OpenRouter Model Evaluation Script for BFCL

This script runs the BFCL evaluation for 5 models via OpenRouter API:
- meta-llama/llama-3.3-70b-instruct
- mistralai/mistral-small-3.2-24b-instruct  
- qwen/qwen3-32b
- qwen/qwen3-14b
- qwen/qwen3-next-80b-a3b-instruct

Usage:
    python run_openrouter_eval.py [--test-mode] [--full-eval]

Options:
    --test-mode: Run with only 1 sample per category (quick test)
    --full-eval: Run full evaluation on all categories
    Default: Run 1 sample per category for quick verification

Results are saved in:
    - ./result/{model_name}/ - Model responses
    - ./score/ - Evaluation scores
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check for API key
if not os.getenv("OPENROUTER_API_KEY"):
    print("Error: OPENROUTER_API_KEY environment variable is not set.")
    print("Please set it in your .env file or environment.")
    sys.exit(1)

# Model configurations
OPENROUTER_MODELS = [
    "openrouter/llama-3.3-70b-instruct-FC",
    "openrouter/mistral-small-3.2-24b-instruct-FC",
    "openrouter/qwen3-32b-FC",
    "openrouter/qwen3-14b-FC",
    "openrouter/qwen3-next-80b-a3b-instruct-FC",
]

# Test categories for quick test (1 per category type)
TEST_CATEGORIES = [
    "simple",      # Single function call (Python)
    "multiple",    # Multiple function selection
    "parallel",    # Parallel function calls
]

# All categories for full evaluation
ALL_CATEGORIES = [
    "simple",
    "multiple", 
    "parallel",
    "live_simple",
    "live_multiple",
    "live_parallel",
    "multi_turn_base",
    "multi_turn_miss_func",
    "multi_turn_miss_param",
    "multi_turn_long_context",
]


def run_generation(model: str, categories: list[str], temperature: float = 0.0):
    """Run LLM response generation for a model."""
    print(f"\n{'='*60}")
    print(f"Generating responses for: {model}")
    print(f"Categories: {', '.join(categories)}")
    print(f"Temperature: {temperature}")
    print(f"{'='*60}\n")
    
    cmd = [
        sys.executable, "-m", "bfcl_eval",
        "generate",
        "--model", model,
        "--test-category", ",".join(categories),
        "--temperature", str(temperature),
        "--num-threads", "1",  # Single thread for rate limiting
    ]
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    return result.returncode == 0


def run_evaluation(model: str, categories: list[str]):
    """Run evaluation on generated responses."""
    print(f"\n{'='*60}")
    print(f"Evaluating: {model}")
    print(f"Categories: {', '.join(categories)}")
    print(f"{'='*60}\n")
    
    cmd = [
        sys.executable, "-m", "bfcl_eval",
        "evaluate",
        "--model", model,
        "--test-category", ",".join(categories),
    ]
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    return result.returncode == 0


def show_scores():
    """Display evaluation scores."""
    print(f"\n{'='*60}")
    print("Evaluation Scores")
    print(f"{'='*60}\n")
    
    cmd = [sys.executable, "-m", "bfcl_eval", "scores"]
    subprocess.run(cmd, cwd=Path(__file__).parent)


def show_results():
    """Display available results."""
    print(f"\n{'='*60}")
    print("Available Results")
    print(f"{'='*60}\n")
    
    cmd = [sys.executable, "-m", "bfcl_eval", "results"]
    subprocess.run(cmd, cwd=Path(__file__).parent)


def main():
    parser = argparse.ArgumentParser(
        description="Run BFCL evaluation for OpenRouter models"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run quick test with minimal categories"
    )
    parser.add_argument(
        "--full-eval",
        action="store_true", 
        help="Run full evaluation on all categories"
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=OPENROUTER_MODELS + ["all"],
        default="all",
        help="Specific model to evaluate (default: all)"
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Only generate responses, skip evaluation"
    )
    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help="Only run evaluation on existing responses"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature for generation (default: 0.0)"
    )
    
    args = parser.parse_args()
    
    # Determine categories to run
    if args.full_eval:
        categories = ALL_CATEGORIES
    else:
        categories = TEST_CATEGORIES
    
    # Determine models to run
    if args.model == "all":
        models = OPENROUTER_MODELS
    else:
        models = [args.model]
    
    print("=" * 60)
    print("BFCL OpenRouter Evaluation")
    print("=" * 60)
    print(f"Models: {len(models)}")
    print(f"Categories: {', '.join(categories)}")
    print(f"Temperature: {args.temperature}")
    print(f"Delay: 1 second between API calls")
    print("=" * 60)
    
    # Run generation
    if not args.evaluate_only:
        for model in models:
            success = run_generation(model, categories, args.temperature)
            if not success:
                print(f"Warning: Generation failed for {model}")
    
    # Run evaluation
    if not args.generate_only:
        for model in models:
            success = run_evaluation(model, categories)
            if not success:
                print(f"Warning: Evaluation failed for {model}")
    
    # Show results
    print("\n")
    show_results()
    
    # Show scores if evaluation was run
    if not args.generate_only:
        show_scores()
    
    print("\n" + "=" * 60)
    print("Evaluation Complete!")
    print("=" * 60)
    print("\nResults are saved in:")
    print(f"  - Model responses: ./result/")
    print(f"  - Evaluation scores: ./score/")
    print("\nResult format: JSON Lines (.json)")
    print("Each line contains: id, result, input_token_count, output_token_count, latency, inference_log")


if __name__ == "__main__":
    main()
