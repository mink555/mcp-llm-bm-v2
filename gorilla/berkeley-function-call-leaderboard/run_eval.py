#!/usr/bin/env python3
"""
BFCL 평가 자동화 스크립트

사용법:
    # 퀵 테스트 (각 카테고리 2개씩)
    python run_eval.py --quick
    
    # 특정 모델만 퀵 테스트
    python run_eval.py --quick --models openrouter/qwen3-14b-FC
    
    # 전체 테스트
    python run_eval.py --full
    
    # 특정 카테고리만
    python run_eval.py --quick --categories simple_python,multiple

결과물:
    reports/
    ├── {model_name}/
    │   └── {model_name}_eval_report.xlsx
    └── summary/
        └── all_models_summary.xlsx
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 지원 모델 목록
SUPPORTED_MODELS = [
    "openrouter/llama-3.3-70b-instruct-FC",
    "openrouter/mistral-small-3.2-24b-instruct-FC",
    "openrouter/qwen3-32b-FC",
    "openrouter/qwen3-14b-FC",
    "openrouter/qwen3-next-80b-a3b-instruct-FC",
]

# 퀵 테스트용 ID (각 카테고리 2개씩)
QUICK_TEST_IDS = {
    "simple_python": ["simple_python_0", "simple_python_1"],
    "multiple": ["multiple_0", "multiple_1"],
    "parallel": ["parallel_0", "parallel_1"],
}

# 전체 카테고리
ALL_CATEGORIES = ["simple_python", "multiple", "parallel"]

def _write_sample_id_file(categories: list[str], sample_size: int, seed: int = 0) -> str:
    """
    bfcl_eval generate의 --run-ids 모드용 파일을 임시로 작성.
    - 카테고리별로 동일한 ID 집합을 모든 모델에 적용 (모델 비교 가능)
    - 기존 파일은 .bak 으로 백업 후, 작업 종료 시 복구 필요
    """
    from bfcl_eval.utils import load_dataset_entry
    import random

    rng = random.Random(seed)
    sample_map: dict[str, list[str]] = {}

    for cat in categories:
        entries = load_dataset_entry(cat)
        ids = [e["id"] for e in entries if "id" in e]
        # 안정적인 순서를 위해 정렬 후 샘플링
        ids = sorted(ids)
        if sample_size >= len(ids):
            picked = ids
        else:
            # 재현 가능하게 랜덤 샘플
            picked = rng.sample(ids, sample_size)
            picked = sorted(picked)
        sample_map[cat] = picked

    test_ids_file = Path("test_case_ids_to_generate.json")
    bak_path = test_ids_file.with_suffix(".json.bak")
    if test_ids_file.exists():
        bak_path.write_text(test_ids_file.read_text())
    test_ids_file.write_text(json.dumps(sample_map, indent=2))
    return str(bak_path)


def _restore_id_file(bak_path: str) -> None:
    test_ids_file = Path("test_case_ids_to_generate.json")
    bak = Path(bak_path)
    if bak.exists():
        test_ids_file.write_text(bak.read_text())
        bak.unlink()


def run_command(cmd: list, description: str = "") -> bool:
    """명령 실행"""
    if description:
        print(f"\n{'='*60}")
        print(f"📌 {description}")
        print(f"{'='*60}")
    
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def clean_directories():
    """이전 결과 정리"""
    print("\n🧹 이전 결과 정리 중...")
    for dir_name in ["result", "score"]:
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.rmtree(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
    print("✅ 정리 완료")


def setup_quick_test():
    """퀵 테스트 설정 파일 생성"""
    test_ids_file = Path("test_case_ids_to_generate.json")
    with open(test_ids_file, "w") as f:
        json.dump(QUICK_TEST_IDS, f, indent=2)
    print(f"✅ 퀵 테스트 설정 완료: {test_ids_file}")


def generate_results(model: str, categories: list, is_quick: bool) -> bool:
    """모델 응답 생성"""
    cmd = [
        sys.executable, "-m", "bfcl_eval", "generate",
        "--model", model,
        "--test-category", ",".join(categories),
        "--temperature", "0",
        "--num-threads", "1",
    ]
    
    if is_quick:
        cmd.append("--run-ids")
    
    return run_command(cmd, f"응답 생성: {model}")


def evaluate_results(models: list, categories: list) -> bool:
    """평가 실행"""
    cmd = [
        sys.executable, "-m", "bfcl_eval", "evaluate",
        "--model", ",".join(models),
        "--test-category", ",".join(categories),
        "--partial-eval",
    ]
    
    return run_command(cmd, "평가 실행")


def generate_reports(models: list):
    """엑셀 보고서 생성"""
    from excel_reporter import generate_excel_report, generate_all_models_summary
    
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    print(f"\n{'='*60}")
    print("📊 엑셀 보고서 생성")
    print(f"{'='*60}")
    
    # 모델별 보고서 생성
    model_reports = []
    
    for model in models:
        safe_name = model.replace("/", "_")
        result_dir = Path(f"result/{safe_name}")
        score_dir = Path(f"score/{safe_name}")
        
        if not result_dir.exists():
            print(f"⚠️  결과 없음: {model}")
            continue
        
        # 모델별 폴더 생성
        model_report_dir = reports_dir / safe_name
        model_report_dir.mkdir(exist_ok=True)
        
        # 보고서 생성
        try:
            report_path = generate_excel_report(
                model_name=model,
                result_dir=str(result_dir),
                score_dir=str(score_dir)
            )
            
            # 생성된 파일을 모델 폴더로 이동
            report_file = Path(report_path)
            target_path = model_report_dir / f"{safe_name}_eval_report.xlsx"
            if report_file.exists():
                shutil.move(str(report_file), str(target_path))
                print(f"✅ {model}: {target_path}")
                model_reports.append(target_path)
        except Exception as e:
            print(f"❌ 보고서 생성 실패 ({model}): {e}")
    
    # 전체 취합 보고서 생성
    if len(model_reports) > 1:
        try:
            summary_path = generate_all_models_summary(str(reports_dir))
            print(f"✅ 전체 취합: {summary_path}")
        except Exception as e:
            print(f"⚠️  취합 보고서 생성 실패: {e}")
    
    return model_reports


def print_summary(models: list):
    """결과 요약 출력"""
    print(f"\n{'='*60}")
    print("📋 평가 결과 요약")
    print(f"{'='*60}")
    
    # score 파일에서 결과 읽기
    for model in models:
        safe_name = model.replace("/", "_")
        score_dir = Path(f"score/{safe_name}/non_live")
        
        if not score_dir.exists():
            continue
        
        print(f"\n🦍 {model}")
        
        for score_file in sorted(score_dir.glob("*_score.json")):
            with open(score_file) as f:
                first_line = f.readline()
                summary = json.loads(first_line)
            
            category = score_file.name.replace("BFCL_v4_", "").replace("_score.json", "")
            accuracy = summary.get("accuracy", 0) * 100
            correct = summary.get("correct_count", 0)
            total = summary.get("total_count", 0)
            
            status = "✅" if accuracy >= 80 else "⚠️" if accuracy >= 50 else "❌"
            print(f"   {status} {category}: {accuracy:.1f}% ({correct}/{total})")


def main():
    parser = argparse.ArgumentParser(description="BFCL 평가 자동화")
    parser.add_argument("--quick", action="store_true", help="퀵 테스트 (각 카테고리 2개씩)")
    parser.add_argument("--full", action="store_true", help="전체 테스트")
    parser.add_argument("--models", type=str, help="테스트할 모델 (쉼표 구분)")
    parser.add_argument("--categories", type=str, help="테스트할 카테고리 (쉼표 구분)")
    parser.add_argument("--sample-size", type=int, default=0, help="카테고리별 샘플 개수(0이면 전체). --run-ids로 실행")
    parser.add_argument("--sample-seed", type=int, default=0, help="샘플링 시드(재현성)")
    parser.add_argument("--num-threads", type=int, default=1, help="생성 단계 동시성(threads)")
    parser.add_argument("--append", action="store_true", help="기존 result/score를 삭제하지 않고 누적 실행")
    parser.add_argument("--skip-generate", action="store_true", help="생성 단계 건너뛰기")
    parser.add_argument("--skip-evaluate", action="store_true", help="평가 단계 건너뛰기")
    parser.add_argument("--report-only", action="store_true", help="보고서만 생성")
    
    args = parser.parse_args()
    
    # 기본값:
    # - 카테고리 지정이 없으면 quick
    # - 카테고리를 지정하면 전체(또는 sample-size) 실행
    if not args.quick and not args.full:
        args.quick = (args.categories is None and args.sample_size == 0)
    
    # 모델 목록
    if args.models:
        models = [m.strip() for m in args.models.split(",")]
    else:
        models = SUPPORTED_MODELS
    
    # 카테고리 목록
    if args.categories:
        categories = [c.strip() for c in args.categories.split(",")]
    else:
        categories = ALL_CATEGORIES
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    BFCL 평가 자동화                          ║
╠══════════════════════════════════════════════════════════════╣
║  모드: {'퀵 테스트' if args.quick else '전체 테스트'}                                          ║
║  모델: {len(models)}개                                                ║
║  카테고리: {', '.join(categories):<43} ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # 1. 정리
    if not args.report_only and not args.skip_generate and not args.append:
        clean_directories()
        
        if args.quick:
            setup_quick_test()
    
    # 2. 생성
    if not args.report_only and not args.skip_generate:
        # sample-size 모드면, run-ids 파일을 임시로 교체해서 해당 ID만 생성
        bak_path = ""
        try:
            if args.sample_size and args.sample_size > 0:
                bak_path = _write_sample_id_file(categories, args.sample_size, seed=args.sample_seed)
                is_run_ids = True
            else:
                is_run_ids = args.quick

            # num-threads 반영
            def _generate(model: str) -> bool:
                cmd = [
                    sys.executable, "-m", "bfcl_eval", "generate",
                    "--model", model,
                    "--test-category", ",".join(categories),
                    "--temperature", "0",
                    "--num-threads", str(args.num_threads),
                ]
                if is_run_ids:
                    cmd.append("--run-ids")
                return run_command(cmd, f"응답 생성: {model}")

            for model in models:
                if not _generate(model):
                    print(f"❌ 생성 실패: {model}")
        finally:
            if bak_path:
                _restore_id_file(bak_path)
    
    # 3. 평가
    if not args.report_only and not args.skip_evaluate:
        if not evaluate_results(models, categories):
            print("❌ 평가 실패")
    
    # 4. 보고서 생성
    generate_reports(models)
    
    # 5. 요약 출력
    print_summary(models)
    
    print(f"\n{'='*60}")
    print("🎉 완료!")
    print(f"{'='*60}")
    print(f"📁 보고서 위치: reports/")


if __name__ == "__main__":
    main()
