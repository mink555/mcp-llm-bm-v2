#!/usr/bin/env python3
"""
BFCL 통합 평가 스크립트 v2

기능:
- 모델별 result/score 폴더 구조 자동 생성
- 카테고리별 평가 실행
- 완료 후 엑셀 보고서 자동 생성

사용법:
    # 전체 평가 (모든 카테고리)
    python run_bfcl_eval_v2.py --model openrouter/mistral-small-3.2-24b-instruct-FC

    # 퀵 테스트 (카테고리당 1개)
    python run_bfcl_eval_v2.py --model openrouter/mistral-small-3.2-24b-instruct-FC --quick-test

    # 특정 카테고리만
    python run_bfcl_eval_v2.py --model openrouter/mistral-small-3.2-24b-instruct-FC --categories simple_python,multiple

    # 엑셀 보고서만 생성 (이미 평가 완료된 경우)
    python run_bfcl_eval_v2.py --model openrouter/mistral-small-3.2-24b-instruct-FC --report-only
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent

# BFCL 카테고리 정의
ALL_CATEGORIES = {
    "non_live": [
        "simple_python",
        "simple_java", 
        "simple_javascript",
        "multiple",
        "parallel",
        "parallel_multiple",
        "irrelevance",
    ],
    "live": [
        "live_simple",
        "live_multiple",
        "live_parallel",
        "live_parallel_multiple",
        "live_irrelevance",
        "live_relevance",
    ],
    "multi_turn": [
        "multi_turn_base",
        "multi_turn_miss_func",
        "multi_turn_miss_param",
        "multi_turn_long_context",
    ],
    "agentic": [
        "memory_kv",
        "memory_vector",
        "memory_rec_sum",
        "web_search_base",
        "web_search_no_snippet",
    ],
}

# 퀵 테스트용 대표 카테고리 (각 그룹당 1개씩)
QUICK_TEST_CATEGORIES = [
    "simple_python",      # Non-Live 대표
    "live_simple",        # Live 대표
    "multi_turn_base",    # Multi-Turn 대표
    # Agentic 카테고리는 특수한 설정이 필요하므로 기본 퀵 테스트에서는 제외
]

# OpenRouter 모델 매핑
OPENROUTER_MODELS = {
    "openrouter/llama-3.3-70b-instruct-FC": "meta-llama/llama-3.3-70b-instruct",
    "openrouter/mistral-small-3.2-24b-instruct-FC": "mistralai/mistral-small-3.2-24b-instruct",
    "openrouter/qwen3-32b-FC": "qwen/qwen3-32b",
    "openrouter/qwen3-14b-FC": "qwen/qwen3-14b",
    "openrouter/qwen3-next-80b-a3b-instruct-FC": "qwen/qwen3-next-80b-a3b-instruct",
}


def get_model_folder_name(model_name: str) -> str:
    """모델명을 폴더명으로 변환"""
    # 슬래시를 언더스코어로, 특수문자 제거
    folder_name = model_name.replace("/", "_").replace("\\", "_").replace(":", "_")
    return folder_name


def ensure_model_directories(model_name: str) -> tuple[Path, Path]:
    """모델별 result/score 디렉토리 구조 생성"""
    folder_name = get_model_folder_name(model_name)
    
    result_base = PROJECT_ROOT / "result" / folder_name
    score_base = PROJECT_ROOT / "score" / folder_name
    
    # 하위 디렉토리 생성
    subdirs = ["non_live", "live", "multi_turn", "agentic"]
    for subdir in subdirs:
        (result_base / subdir).mkdir(parents=True, exist_ok=True)
        (score_base / subdir).mkdir(parents=True, exist_ok=True)
    
    return result_base, score_base


def create_test_ids_file(categories: list[str], entries_per_category: int = 1) -> Path:
    """테스트 ID 파일 생성 (카테고리당 지정된 수의 엔트리)"""
    test_ids = {}
    
    for category in categories:
        # 카테고리별 ID 생성 (예: simple_python_0, simple_python_1, ...)
        ids = [f"{category}_{i}" for i in range(entries_per_category)]
        test_ids[category] = ids
    
    output_path = PROJECT_ROOT / "test_case_ids_to_generate.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(test_ids, f, indent=2)
    
    return output_path


def run_bfcl_generate(
    model: str,
    categories: list[str],
    temperature: float = 0.0,
    num_threads: int = 1,
    run_ids: bool = False,
) -> bool:
    """BFCL generate 명령 실행"""
    cmd = [
        sys.executable, "-m", "bfcl_eval",
        "generate",
        "--model", model,
        "--test-category", ",".join(categories),
        "--temperature", str(temperature),
        "--num-threads", str(num_threads),
    ]
    
    if run_ids:
        cmd.append("--run-ids")  # 플래그만 추가 (파일 경로는 자동 참조)
    
    print(f"\n{'='*60}")
    print(f"[GENERATE] 모델: {model}")
    print(f"[GENERATE] 카테고리: {', '.join(categories)}")
    print(f"[GENERATE] 명령: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode == 0


def run_bfcl_evaluate(model: str, categories: list[str], partial_eval: bool = False) -> bool:
    """BFCL evaluate 명령 실행"""
    cmd = [
        sys.executable, "-m", "bfcl_eval",
        "evaluate",
        "--model", model,
        "--test-category", ",".join(categories),
    ]
    
    if partial_eval:
        cmd.append("--partial-eval")
    
    print(f"\n{'='*60}")
    print(f"[EVALUATE] 모델: {model}")
    print(f"[EVALUATE] 카테고리: {', '.join(categories)}")
    print(f"[EVALUATE] 명령: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode == 0


def generate_excel_report(model_name: str) -> Optional[str]:
    """엑셀 보고서 생성"""
    try:
        from excel_reporter import BFCLExcelReporter
        
        folder_name = get_model_folder_name(model_name)
        result_dir = PROJECT_ROOT / "result" / folder_name
        score_dir = PROJECT_ROOT / "score" / folder_name
        
        reporter = BFCLExcelReporter(
            model_name=model_name,
            result_dir=result_dir,
            score_dir=score_dir,
        )
        
        output_path = reporter.generate_report()
        print(f"\n[REPORT] 엑셀 보고서 생성 완료: {output_path}")
        return str(output_path)
        
    except ImportError as e:
        print(f"\n[WARNING] 엑셀 보고서 생성 실패 - openpyxl 설치 필요: {e}")
        return None
    except Exception as e:
        print(f"\n[ERROR] 엑셀 보고서 생성 중 오류: {e}")
        return None


def print_summary(model_name: str):
    """평가 결과 요약 출력"""
    folder_name = get_model_folder_name(model_name)
    score_base = PROJECT_ROOT / "score" / folder_name
    
    print(f"\n{'='*60}")
    print(f"평가 결과 요약: {model_name}")
    print(f"{'='*60}")
    
    total_correct = 0
    total_count = 0
    
    for subdir in ["non_live", "live", "multi_turn", "agentic"]:
        subdir_path = score_base / subdir
        if subdir_path.exists():
            print(f"\n[{subdir.upper()}]")
            for score_file in sorted(subdir_path.glob("*_score.json")):
                try:
                    with open(score_file, "r") as f:
                        content = f.read().strip()
                        # JSON Lines 형식 처리 (첫 번째 줄만 읽기)
                        first_line = content.split('\n')[0]
                        score = json.loads(first_line)
                except (json.JSONDecodeError, IndexError) as e:
                    print(f"    [!] {score_file.name}: 파일 읽기 오류")
                    continue
                
                category = score_file.name.replace("_score.json", "").split("_", 2)[-1]
                accuracy = score.get("accuracy", 0) * 100
                correct = score.get("correct_count", 0)
                total = score.get("total_count", 0)
                
                total_correct += correct
                total_count += total
                
                status = "✓" if accuracy >= 80 else "△" if accuracy >= 50 else "✗"
                print(f"  {status} {category}: {accuracy:.2f}% ({correct}/{total})")
    
    if total_count > 0:
        overall_accuracy = (total_correct / total_count) * 100
        print(f"\n{'='*60}")
        print(f"전체 정확도: {overall_accuracy:.2f}% ({total_correct}/{total_count})")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="BFCL 통합 평가 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 전체 평가
  python run_bfcl_eval_v2.py --model openrouter/mistral-small-3.2-24b-instruct-FC
  
  # 퀵 테스트 (카테고리당 1개씩)
  python run_bfcl_eval_v2.py --model openrouter/mistral-small-3.2-24b-instruct-FC --quick-test
  
  # 퀵 테스트 (카테고리당 5개씩)
  python run_bfcl_eval_v2.py --model openrouter/mistral-small-3.2-24b-instruct-FC --quick-test --entries 5
  
  # 특정 카테고리만
  python run_bfcl_eval_v2.py --model openrouter/mistral-small-3.2-24b-instruct-FC --categories simple_python,multiple
  
  # 엑셀 보고서만 생성
  python run_bfcl_eval_v2.py --model openrouter/mistral-small-3.2-24b-instruct-FC --report-only
        """
    )
    
    parser.add_argument(
        "--model", 
        required=True,
        help="평가할 모델명 (예: openrouter/mistral-small-3.2-24b-instruct-FC)"
    )
    parser.add_argument(
        "--quick-test",
        action="store_true",
        help="퀵 테스트 모드 (카테고리당 지정된 수의 샘플만 평가)"
    )
    parser.add_argument(
        "--entries",
        type=int,
        default=1,
        help="퀵 테스트 시 카테고리당 엔트리 수 (기본값: 1)"
    )
    parser.add_argument(
        "--categories",
        type=str,
        help="평가할 카테고리 (쉼표 구분, 예: simple_python,multiple)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="생성 온도 (기본값: 0.0)"
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="응답 생성만 수행 (평가 건너뜀)"
    )
    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help="평가만 수행 (이미 생성된 응답 사용)"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="엑셀 보고서만 생성"
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="엑셀 보고서 생성 건너뜀"
    )
    
    args = parser.parse_args()
    
    # API 키 확인
    if not os.getenv("OPENROUTER_API_KEY"):
        print("[ERROR] OPENROUTER_API_KEY 환경변수가 설정되지 않았습니다.")
        print("  .env 파일에 OPENROUTER_API_KEY=your_api_key 추가 필요")
        sys.exit(1)
    
    # 보고서만 생성
    if args.report_only:
        generate_excel_report(args.model)
        print_summary(args.model)
        return
    
    # 카테고리 결정
    if args.categories:
        categories = args.categories.split(",")
    elif args.quick_test:
        categories = QUICK_TEST_CATEGORIES
    else:
        # 모든 카테고리
        categories = []
        for cat_list in ALL_CATEGORIES.values():
            categories.extend(cat_list)
    
    # 폴더 구조 생성
    result_dir, score_dir = ensure_model_directories(args.model)
    print(f"\n[INFO] 결과 디렉토리: {result_dir}")
    print(f"[INFO] 점수 디렉토리: {score_dir}")
    
    # 퀵 테스트인 경우 테스트 ID 파일 생성
    use_run_ids = args.quick_test
    if use_run_ids:
        test_ids_file = create_test_ids_file(categories, args.entries)
        print(f"[INFO] 테스트 ID 파일 생성: {test_ids_file}")
        print(f"[INFO] 카테고리당 {args.entries}개 샘플 평가")
    
    # 생성 실행
    if not args.evaluate_only:
        success = run_bfcl_generate(
            model=args.model,
            categories=categories,
            temperature=args.temperature,
            num_threads=1,
            run_ids=use_run_ids,
        )
        if not success:
            print("[WARNING] 일부 생성 작업이 실패했을 수 있습니다.")
    
    # 평가 실행
    if not args.generate_only:
        success = run_bfcl_evaluate(
            model=args.model,
            categories=categories,
            partial_eval=use_run_ids,  # 퀵 테스트 시 partial-eval 사용
        )
        if not success:
            print("[WARNING] 일부 평가 작업이 실패했을 수 있습니다.")
    
    # 결과 요약
    print_summary(args.model)
    
    # 엑셀 보고서 생성
    if not args.no_report and not args.generate_only:
        generate_excel_report(args.model)
    
    print("\n[DONE] 평가 완료!")
    print(f"  결과 위치: {result_dir}")
    print(f"  점수 위치: {score_dir}")


if __name__ == "__main__":
    main()
