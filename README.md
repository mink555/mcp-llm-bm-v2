# MCP-LLM-BM-V2

BFCL (Berkeley Function Calling Leaderboard)을 활용한 LLM Function Calling 성능 평가 프로젝트

## 개요

OpenRouter API를 통해 다양한 LLM 모델의 Function Calling 성능을 BFCL 벤치마크로 평가합니다.

## 지원 모델

| 모델 | OpenRouter ID |
|------|---------------|
| Mistral Small 3.2 24B | `openrouter/mistral-small-3.2-24b-instruct-FC` |
| Qwen3 14B | `openrouter/qwen3-14b-FC` |
| Qwen3 32B | `openrouter/qwen3-32b-FC` |
| Llama 3.3 70B | `openrouter/llama-3.3-70b-instruct-FC` |

## 설치

```bash
cd gorilla/berkeley-function-call-leaderboard
pip install -e .
```

## 환경 설정

`.env` 파일 생성:

```env
OPENROUTER_API_KEY=your_api_key_here
```

## 사용법

### 1. 모델 응답 생성

```bash
cd gorilla/berkeley-function-call-leaderboard

# 전체 카테고리 실행
python -m bfcl_eval generate \
    --model openrouter/mistral-small-3.2-24b-instruct-FC \
    --test-category all \
    --temperature 0 \
    --num-threads 1

# 특정 카테고리만 실행
python -m bfcl_eval generate \
    --model openrouter/mistral-small-3.2-24b-instruct-FC \
    --test-category simple_python \
    --temperature 0
```

### 2. 평가 실행

```bash
python -m bfcl_eval evaluate \
    --model openrouter/mistral-small-3.2-24b-instruct-FC \
    --test-category simple_python
```

### 3. 엑셀 보고서 생성

```python
from excel_reporter import BFCLExcelReporter
from pathlib import Path

reporter = BFCLExcelReporter(
    model_name='openrouter/mistral-small-3.2-24b-instruct-FC',
    result_dir=Path('result/openrouter_mistral-small-3.2-24b-instruct-FC'),
    score_dir=Path('score/openrouter_mistral-small-3.2-24b-instruct-FC'),
)
report_path = reporter.generate_report()
print(f'보고서 생성: {report_path}')
```

## 평가 카테고리

| 카테고리 | 설명 |
|----------|------|
| `simple_python` | 단일 함수 호출 (Python) |
| `multiple_python` | 다중 함수 호출 (Python) |
| `parallel_python` | 병렬 함수 호출 (Python) |
| `simple_java` | 단일 함수 호출 (Java) |
| `simple_javascript` | 단일 함수 호출 (JavaScript) |
| `relevance` | 관련성 판단 |
| `irrelevance` | 비관련성 판단 |
| `live_*` | 실시간 API 테스트 |
| `multi_turn_*` | 멀티턴 대화 |

## 엑셀 보고서 구조

### Sheet 1: Evaluation Criteria
- AST 평가 방식 설명
- Pass/Fail 조건

### Sheet 2: Summary (BFCL 공식 Score 형식)

| 컬럼 | 설명 |
|------|------|
| Category | 테스트 카테고리 |
| Type | 테스트 유형 |
| Total | 전체 테스트 수 |
| Correct | 정답 수 |
| Incorrect | 오답 수 |
| Accuracy | 정확도 (Correct / Total) |

**Special Rows:**
- **TOTAL**: 전체 합계 및 Weighted Accuracy
- **Overall Acc (BFCL)**: Unweighted Average = AVERAGE(각 카테고리 Accuracy)
  - [BFCL 공식](https://gorilla.cs.berkeley.edu/leaderboard.html): "Overall Accuracy is the unweighted average of all the sub-categories"

### Sheet 3: Detail
| 컬럼 | 설명 |
|------|------|
| # | 순번 |
| Result | PASS / FAIL |
| Category | 테스트 카테고리 |
| Type | 테스트 유형 |
| Query | 테스트 ID |
| Request | 실제 질문 내용 |
| Expected (GT) | Ground Truth |
| Actual (Model) | 모델 응답 (파싱된 함수 호출 형식) |
| Error Type | 오류 유형 (FAIL인 경우) |

## 디렉토리 구조

```
mcp-llm-bm-v2/
├── gorilla/
│   └── berkeley-function-call-leaderboard/
│       ├── bfcl_eval/
│       │   ├── model_handler/
│       │   │   └── api_inference/
│       │   │       └── openrouter.py    # OpenRouter 핸들러
│       │   └── eval_checker/
│       │       └── ast_eval/
│       │           └── ast_checker.py   # AST 평가 로직
│       ├── excel_reporter.py            # 엑셀 보고서 생성
│       ├── result/                      # 모델 응답 결과
│       │   └── {model_name}/
│       │       └── non_live/
│       │           └── BFCL_v4_{category}_result.json
│       └── score/                       # 평가 결과
│           └── {model_name}/
│               └── non_live/
│                   └── BFCL_v4_{category}_score.json
└── README.md
```

## 주요 수정 사항

### OpenRouter Handler (`openrouter.py`)

Mistral 모델의 특수 응답 형식 지원:

```python
# Mistral 모델 응답 형식
"[TOOL_CALLScalculate_triangle_area{\"base\": 10, \"height\": 5}"

# 파싱 후
[{"calculate_triangle_area": {"base": 10, "height": 5}}]
```

`_parse_mistral_tool_calls_text()` 메서드로 다음 형식 파싱:
- `[TOOL_CALLS...]` 형식
- `func_name{...}` 형식
- 표준 JSON 배열 형식

## 참고 자료

- [BFCL v1 Blog](https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html)
- [BFCL v2 Live](https://gorilla.cs.berkeley.edu/blogs/12_bfcl_v2_live.html)
- [BFCL v3 Multi-Turn](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html)
- [BFCL GitHub](https://github.com/gorilla-llm/gorilla/tree/main/berkeley-function-call-leaderboard)
- [BFCL Dataset (HuggingFace)](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard)
