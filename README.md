# MCP-LLM-BM-V2

OpenRouter API를 통한 LLM Function Calling 성능 평가 프로젝트  
**BFCL (Berkeley Function Calling Leaderboard) V4** 벤치마크 기반

---

## 목차

1. [BFCL이란?](#bfcl이란)
2. [평가 의도 및 철학](#평가-의도-및-철학)
3. [평가 카테고리](#평가-카테고리)
4. [평가 지표](#평가-지표)
5. [지원 모델](#지원-모델)
6. [모델별 이슈 및 특성](#모델별-이슈-및-특성)
7. [설치 및 환경 설정](#설치-및-환경-설정)
8. [사용법 (CLI)](#사용법-cli)
9. [보고서 구조](#보고서-구조)
10. [디렉토리 구조](#디렉토리-구조)
11. [참고 자료](#참고-자료)

---

## 🚀 최근 업데이트 (V2.1)

- **평가 범위 확대**: `simple_python`, `multiple`, `parallel` 전체 완주 및 `parallel_multiple` 모델별 100개 샘플 추가.
- **엑셀 보고서 고도화**: 모든 핵심 지표(Accuracy 등)를 하드코딩 대신 **엑셀 수식 기반**으로 변경하여 데이터 정합성 확보.
- **상세 분석 컬럼**: `상세` 시트에 파라미터명, 기대 타입, 실제 타입, 실제 값 등 오류 원인 파악을 위한 힌트 컬럼 추가.
- **CLI 옵션 강화**: `--append`(누적 실행), `--sample-size`(샘플링), `--num-threads`(동시성 제어) 옵션 추가.

---

## BFCL이란?

**Berkeley Function Calling Leaderboard (BFCL)**는 UC Berkeley에서 개발한 LLM Function Calling 능력 평가 벤치마크입니다.

### 주요 특징

- **표준 벤치마크**: Function Calling 평가의 사실상 표준 (de facto standard)
- **다양한 시나리오**: 단일/다중/병렬 함수 호출, 다국어(Python/Java/JS) 지원
- **실제 세계 반영**: 실제 개발 환경에서 사용되는 다양한 함수 패턴 포함
- **AST 기반 평가**: Abstract Syntax Tree를 활용한 정확한 구문 분석

### 버전 히스토리

| 버전 | 출시일 | 주요 특징 |
|------|--------|-----------|
| V1 | 2024.02 | AST 평가 방식 도입 |
| V2 | 2024.05 | 실시간(Live) 데이터 추가 |
| V3 | 2024.09 | Multi-Turn 대화 지원 |
| V4 | 2024.12 | Agentic 평가 추가 |

---

## 평가 의도 및 철학

### BFCL이 테스트하는 것

1. **올바른 함수 선택**: 여러 함수 중 적절한 함수를 선택하는 능력
2. **올바른 파라미터 전달**: 필수/선택 파라미터를 정확하게 전달하는 능력
3. **올바른 타입 처리**: 정수, 문자열, 불리언 등 타입을 정확하게 다루는 능력
4. **함수 호출 판단**: 함수 호출이 필요한지/불필요한지 판단하는 능력

### 의도적으로 포함된 어려움

```python
# 실제 Python 코딩 패턴 반영
import math
math.factorial(5)        # 모듈.함수 형태
calculate_area(10, 5)    # 일반 함수 형태
```

- **함수명 다양성**: `math.factorial`, `spotify.play` 등 다양한 네이밍 패턴
- **API 호환성 문제**: `.`이 포함된 함수명은 OpenAI API에서 지원되지 않음 (`^[a-zA-Z0-9_-]+$` 규칙)
- **타입 처리**: 모델이 숫자를 문자열로 반환하는 경우도 평가에 반영

> **중요**: 이 프로젝트는 BFCL의 원래 의도를 존중하여, 모델의 타입 처리 능력도 평가에 반영합니다. (타입 자동 변환 없음)

---

## 평가 카테고리

### Non-Live (AST 평가)

| 카테고리 | 설명 | 데이터 수 |
|----------|------|-----------|
| **Simple** | 단일 함수, 단일 호출 | 400개 (Python) + 100개 (Java) + 50개 (JS) |
| **Multiple** | 다중 함수 중 단일 호출 선택 | 200개 |
| **Parallel** | 단일 함수, 다중 병렬 호출 | 200개 |
| **Parallel Multiple** | 다중 함수, 다중 병렬 호출 | 200개 |

### 카테고리별 상세 설명

#### Simple (단순 함수 호출)
```
사용자: "삼각형의 넓이를 구해줘. 밑변 10, 높이 5"
기대: calculate_triangle_area(base=10, height=5)
```
- 가장 기본적인 형태
- 하나의 함수만 제공, 하나의 호출만 필요

#### Multiple (다중 함수 선택)
```
사용자: "5의 팩토리얼을 계산해줘"
제공 함수: [math.factorial, math.sqrt, math.pow, ...]
기대: math.factorial(number=5)
```
- 2~4개의 함수 중 적절한 것 선택
- 함수 선택 능력 평가

#### Parallel (병렬 함수 호출)
```
사용자: "5의 팩토리얼과 10의 팩토리얼을 동시에 계산해줘"
기대: [math.factorial(number=5), math.factorial(number=10)]
```
- 하나의 요청에 여러 번 호출 필요
- 순서 무관하게 평가 (no_order)

---

## 평가 지표

### AST (Abstract Syntax Tree) 평가

모델 응답을 구문 분석하여 Ground Truth와 비교

```
모델 응답: {"math.factorial": {"number": 5}}
Ground Truth: {"math.factorial": {"number": [5]}}
→ 일치 여부 확인
```

### 주요 지표

| 지표 | 설명 |
|------|------|
| **Accuracy** | 정답률 (Correct / Total) |
| **Overall Acc** | 카테고리별 Accuracy의 비가중 평균 (BFCL 공식 기준) |
| **Weighted Acc** | 전체 정답 수 / 전체 테스트 수 (Σcorrect / Σtotal) |

### 에러 유형

| 에러 타입 | 한국어 설명 |
|-----------|-------------|
| `type_error:simple` | 타입 오류 - 파라미터 타입이 예상과 다름 (예: 정수를 문자열로 반환) |
| `simple_function_checker:wrong_func_name` | 함수명 오류 - 호출한 함수명이 Ground Truth와 다름 |
| `simple_function_checker:missing_required` | 필수 파라미터 누락 |
| `parallel_function_checker_no_order:cannot_find_match` | 병렬 호출 매칭 실패 |
| `ast_decoder:decoder_failed` | 응답 파싱 실패 |

---

## 지원 모델

| 모델 | OpenRouter ID | 파라미터 |
|------|---------------|----------|
| Llama 3.3 70B | `openrouter/llama-3.3-70b-instruct-FC` | 70B |
| Mistral Small 3.2 | `openrouter/mistral-small-3.2-24b-instruct-FC` | 24B |
| Qwen3 32B | `openrouter/qwen3-32b-FC` | 32B |
| Qwen3 14B | `openrouter/qwen3-14b-FC` | 14B |
| Qwen3-next 80B | `openrouter/qwen3-next-80b-a3b-instruct-FC` | 80B |

---

## 모델별 이슈 및 특성

### Llama 3.3 70B

**주요 이슈: 타입 처리 문제**

```json
// Llama 응답 (문제)
{"base": "10", "height": "5"}  // 문자열

// 기대값
{"base": 10, "height": 5}      // 정수
```

- **원인**: Llama는 JSON 응답 시 숫자를 문자열로 반환하는 경향
- **결과**: `simple_python` 카테고리에서 `type_error:simple` 발생
- **BFCL 의도**: 이는 모델의 실제 능력이며, 평가에 반영되어야 함
- **참고**: BFCL 공식 핸들러도 타입 변환을 하지 않음

### Mistral Small 3.2 24B

**특징: 텍스트 기반 Tool Call**

```
// Mistral 응답 형식
[TOOL_CALLS]calculate_area{"base": 10, "height": 5}
```

- **처리**: `_parse_mistral_tool_calls_text()` 메서드로 파싱
- **결과**: 대체로 안정적인 성능

### Qwen3 시리즈 (14B, 32B, 80B)

**특징: 안정적인 타입 처리**

```json
// Qwen 응답 (정상)
{"number": 5}  // 정수로 올바르게 반환
```

- **장점**: 타입을 정확하게 처리
- **결과**: 전반적으로 높은 정확도

### 함수명 변환 이슈 (모든 모델 공통)

**문제**: OpenAI API는 `.`이 포함된 함수명을 지원하지 않음

```
원본: math.factorial
API 전송: math_factorial  (. → _ 변환)
모델 응답: math_factorial
```

**해결**: `underscore_to_dot` 설정에 따라 처리
- `True`: 평가 시 `math_factorial`로 비교
- `False`: 평가 시 `math.factorial`로 복원 후 비교

---

## 설치 및 환경 설정

### 1. 저장소 클론

```bash
git clone <repository-url>
cd mcp-llm-bm-v2
```

### 2. 패키지 설치

```bash
cd gorilla/berkeley-function-call-leaderboard
pip install -e .
pip install openpyxl  # 엑셀 보고서 생성용
```

### 3. 환경 변수 설정

`gorilla/berkeley-function-call-leaderboard/` 디렉토리에 `.env` 파일 생성 (gitignore 처리됨):

```env
OPENROUTER_API_KEY=your_api_key_here
```

> 주의: `.env`는 절대 커밋하지 않습니다. (이 저장소는 `.gitignore`로 차단)

---

## 사용법 (CLI)

### 기본 명령어

```bash
cd gorilla/berkeley-function-call-leaderboard
```

### 퀵 테스트 (권장)

각 카테고리 2개씩, 빠른 검증용:

```bash
# 전체 5개 모델
python run_eval.py --quick

# 특정 모델만
python run_eval.py --quick --models "openrouter/qwen3-14b-FC"

# 여러 모델 지정
python run_eval.py --quick --models "openrouter/qwen3-14b-FC,openrouter/llama-3.3-70b-instruct-FC"
```

### 전체 테스트

전체 데이터셋 평가:

```bash
python run_eval.py --full
```

### 옵션

| 옵션 | 설명 |
|------|------|
| `--quick` | 퀵 테스트 (각 카테고리 2개씩) |
| `--full` | 전체 테스트 |
| `--models "모델1,모델2"` | 특정 모델만 테스트 |
| `--categories "cat1,cat2"` | 특정 카테고리만 테스트 |
| `--num-threads N` | 생성 단계 동시성(threads). OpenRouter 속도/레이트리밋에 맞춰 조절 |
| `--append` | 기존 `result/score`를 삭제하지 않고 누적 실행 |
| `--sample-size N` | 카테고리별 N개만 샘플로 실행(동일 ID로 모델 간 비교). `--append`와 함께 사용 권장 |
| `--sample-seed N` | 샘플링 시드(재현성) |
| `--report-only` | 보고서만 재생성 (기존 결과 유지) |
| `--skip-generate` | 생성 단계 건너뛰기 |
| `--skip-evaluate` | 평가 단계 건너뛰기 |

### 예시

```bash
# Qwen 모델들만 simple_python 테스트
python run_eval.py --quick \
    --models "openrouter/qwen3-14b-FC,openrouter/qwen3-32b-FC" \
    --categories "simple_python"

# parallel_multiple를 각 모델별 100개만 샘플로 추가 실행(누적)
python run_eval.py --append \
    --categories "parallel_multiple" \
    --sample-size 100 \
    --num-threads 4

# 기존 결과로 보고서만 재생성
python run_eval.py --report-only
```

---

## 보고서 구조

### 폴더 구조

```
gorilla/berkeley-function-call-leaderboard/reports/
├── openrouter_qwen3-14b-FC/
│   └── openrouter_qwen3-14b-FC_eval_report.xlsx
├── openrouter_llama-3.3-70b-instruct-FC/
│   └── openrouter_llama-3.3-70b-instruct-FC_eval_report.xlsx
└── summary/
    └── all_models_summary.xlsx  ← 전체 취합(모델 비교)
```

### 보고서 재생성(평가 재실행 없이)

이미 생성된 `result/`, `score/`를 그대로 두고 엑셀만 다시 만들고 싶다면:

```bash
cd gorilla/berkeley-function-call-leaderboard
python regenerate_all_reports.py
```

또는 CLI에서:

```bash
cd gorilla/berkeley-function-call-leaderboard
python run_eval.py --report-only
```

### 개별 보고서(모델별) 시트

#### `요약`
- 핵심 지표(Overall/Weighted Accuracy, Total, Failures)
- 카테고리별 정확도
- 주요 실패 원인(상위 5)
- **수치는 `상세` 시트 기반 엑셀 수식으로 계산**

#### `상세` (PASS/FAIL 모두 포함)
| 컬럼 | 설명 |
|------|------|
| 결과 | PASS / FAIL |
| 카테고리 | 테스트 카테고리 |
| ID | 테스트 케이스 ID |
| 질문 | 실제 요청(Request) |
| 정답(GT) | Ground Truth |
| 모델 응답 | 모델 응답(Actual) |
| Error Type | 에러 유형 |
| 원인(요약) | 한국어 요약(에러 타입 기반) |
| 오류 상세(원문) | score 파일의 error 원문 |
| 파라미터 | (가능한 경우) 관련 파라미터명 |
| 기대 타입 / 실제 타입 / 실제 값 | (가능한 경우) 타입/값 관련 힌트 |

### 통합 보고서(전체 모델 비교) 시트

#### `요약`
- 모델별 핵심 지표 비교(엑셀 수식 기반)

#### `카테고리 매트릭스`
- 카테고리별 모델 정확도 비교

#### `상세` (PASS/FAIL 모두 포함)
- 개별 `상세`와 동일한 형태 + `모델` 컬럼이 추가됩니다.

### 이번 실행 기준 (V2.1 결과물)

- **Non-Live 전체(완주)**: `simple_python(400)`, `multiple(200)`, `parallel(200)` × 모델 5개
- **추가 샘플**: `parallel_multiple`은 **모델별 100개 샘플**로 실행 (앞 100개 ID 고정)
- **통합 상세 규모**: 총 4,500개 행 (\( 800 \times 5 + 100 \times 5 \))

---

## 디렉토리 구조

```
mcp-llm-bm-v2/
├── README.md                    # [문서] 프로젝트 통합 가이드
├── .env                         # [설정] OpenRouter API 키 (gitignore)
├── .gitignore                   # [설정] 불필요 파일 제외 규칙
└── gorilla/
    └── berkeley-function-call-leaderboard/
        ├── run_eval.py          # [핵심] 평가/채점/리포트 통합 실행 스크립트
        ├── excel_reporter.py    # [엔진] 엑셀 리포트 생성 로직
        ├── test_case_ids_to_generate.json  # [데이터] 샘플링/퀵 테스트용 ID 정의
        ├── bfcl_eval/           # [모듈] BFCL 원본 평가 프레임워크
        ├── reports/             # [출력] 생성된 엑셀 보고서 (gitignore)
        ├── result/              # [출력] 모델 응답 원본 (gitignore)
        └── score/               # [출력] AST 채점 결과 (gitignore)
```

---

## 참고 자료

### 공식 문서

- [BFCL 리더보드](https://gorilla.cs.berkeley.edu/leaderboard.html)
- [BFCL V1 블로그](https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html)
- [BFCL V3 Multi-Turn 블로그](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html)
- [BFCL GitHub](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard)

### 데이터셋

- [HuggingFace Dataset](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard)

### 논문

```bibtex
@inproceedings{patil2025bfcl,
  title={The Berkeley Function Calling Leaderboard (BFCL): From Tool Use to Agentic Evaluation of Large Language Models},
  author={Patil, Shishir G. and Mao, Huanzhi and Cheng-Jie Ji, Charlie and Yan, Fanjia and Suresh, Vishnu and Stoica, Ion and E. Gonzalez, Joseph},
  booktitle={Forty-second International Conference on Machine Learning},
  year={2025}
}
```

---

## 라이선스

이 프로젝트는 BFCL의 원본 코드를 기반으로 하며, 원본 라이선스를 따릅니다.
