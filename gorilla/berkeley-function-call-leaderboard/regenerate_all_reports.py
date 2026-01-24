#!/usr/bin/env python3
"""
기존 결과로 모든 엑셀 보고서를 재생성하는 스크립트

사용법:
    python regenerate_all_reports.py
"""

import shutil
from pathlib import Path
from excel_reporter import generate_excel_report, generate_all_models_summary

def main():
    print("🔄 모든 엑셀 보고서 재생성 중...")
    print("=" * 60)
    
    result_base = Path("result")
    score_base = Path("score")
    reports_dir = Path("reports")
    
    # reports 디렉토리 생성
    reports_dir.mkdir(exist_ok=True)
    
    # 모든 모델 찾기
    models = []
    for model_dir in result_base.iterdir():
        if model_dir.is_dir():
            models.append(model_dir.name)
    
    if not models:
        print("❌ 결과 파일이 없습니다. 먼저 평가를 실행하세요.")
        return
    
    print(f"📊 {len(models)}개 모델의 보고서를 생성합니다.")
    print()
    
    # 각 모델별 보고서 생성
    success_count = 0
    for model_safe_name in sorted(models):
        # 모델명 복원
        model_name = model_safe_name.replace("openrouter_", "openrouter/")
        
        result_dir = result_base / model_safe_name
        score_dir = score_base / model_safe_name
        
        if not result_dir.exists() or not score_dir.exists():
            print(f"⚠️  건너뛰기: {model_name} (결과 파일 없음)")
            continue
        
        try:
            # 보고서 생성
            report_path = generate_excel_report(
                model_name=model_name,
                result_dir=str(result_dir),
                score_dir=str(score_dir)
            )
            
            # 모델별 폴더로 이동
            model_report_dir = reports_dir / model_safe_name
            model_report_dir.mkdir(exist_ok=True)
            
            report_file = Path(report_path)
            target_path = model_report_dir / f"{model_safe_name}_eval_report.xlsx"
            
            if report_file.exists():
                shutil.move(str(report_file), str(target_path))
                print(f"✅ {model_name}")
                print(f"   → {target_path}")
                success_count += 1
        except Exception as e:
            print(f"❌ 실패: {model_name}")
            print(f"   오류: {e}")
    
    print()
    print("=" * 60)
    
    # 통합 보고서 생성
    if success_count > 1:
        print("📊 통합 보고서 생성 중...")
        try:
            summary_path = generate_all_models_summary(str(reports_dir))
            print(f"✅ 통합 보고서: {summary_path}")
        except Exception as e:
            print(f"❌ 통합 보고서 생성 실패: {e}")
    
    print()
    print("=" * 60)
    print(f"🎉 완료! {success_count}/{len(models)} 모델의 보고서가 생성되었습니다.")
    print(f"📁 위치: {reports_dir.absolute()}")

if __name__ == "__main__":
    main()
