# 🦍 MCP-LLM-BM-V2
> **OpenRouter API 기반 LLM Function Calling 성능 평가 프레임워크**  
> *BFCL (Berkeley Function Calling Leaderboard) V4 기반*

---

## 📋 프로젝트 개요

| 항목 | 상세 내용 |
| :--- | :--- |
| **목적** | OpenRouter 주요 LLM들의 Function Calling(FC) 성능 정밀 측정 |
| **기반 벤치마크** | UC Berkeley BFCL V4 (Abstract Syntax Tree 기반 정밀 채점) |
| **평가 대상** | Llama 3.3, Mistral Small 3.2, Qwen3 시리즈 (14B, 32B, 80B) |
| **주요 특징** | **싱글턴(Single-turn)** 중심의 정밀 FC 능력 검증 |

---

## 🎯 평가 프레임워크 (BFCL V4)

### 1. 평가 카테고리 및 턴(Turn) 방식
본 프로젝트는 모델의 순수 함수 호출 정확도를 측정하기 위해 **싱글턴(Single-turn)** 방식을 채택하고 있습니다.

| 카테고리 | 방식 (Turn) | 유형 | 상세 설명 | 데이터 수 |
| :--- | :---: | :--- | :--- | :--- |
| **Simple** | 싱글턴 | 단일 호출 | 단일 함수에 대해 1회 호출 수행 (Python/Java/JS) | 550개 |
| **Multiple** | 싱글턴 | 함수 선택 | 여러 후보 함수 중 최적의 함수 1개를 선택하여 호출 | 200개 |
| **Parallel** | 싱글턴 | 병렬 호출 | 동일한 함수를 서로 다른 파라미터로 여러 번 동시 호출 | 200개 |
| **Parallel Multiple** | **복합 싱글턴** | 복합 병렬 | **한 번의 요청**으로 서로 다른 여러 함수를 동시에 호출 | 200개 |

### 2. 싱글턴(우리가 한 것) vs 멀티턴(지원 예정)
| 구분 | 싱글턴 (Single-turn) | 멀티턴 (Multi-turn) |
| :--- | :--- | :--- |
| **대화 구조** | `질문 1회` ➔ `응답 1회` | `질문/응답 반복` (다이얼로그) |
| **상태 유지** | 필요 없음 (Zero-shot) | **필수** (이전 대화 맥락 기억) |
| **평가 목적** | 순수 함수 호출 및 파라미터 정확도 | 대화 흐름에 따른 에이전트(Agent) 추론 능력 |
| **현재 상태** | **완주 (V2.1)** | 데이터셋 지원 (추후 평가 가능) |

### 3. 핵심 평가 지표 (Metrics)
| 지표명 | 계산 로직 (Logic) | 비고 |
| :--- | :--- | :--- |
| **Accuracy** | `Correct / Total` | 개별 카테고리의 순수 정답률 |
| **Overall Acc** | `AVERAGE(Cat_Acc_1, Cat_Acc_2, ...)` | 카테고리별 정답률의 **비가중 평균** (BFCL 공식) |
| **Weighted Acc** | `ΣCorrect / ΣTotal` | 전체 테스트 케이스 대비 전체 정답 수의 비율 |

---

## 🤖 모델별 특성 및 주요 이슈

| 모델명 | FC 성능 | 주요 강점 | 관찰된 이슈 (Critical) |
| :--- | :---: | :--- | :--- |
| **Qwen3-Next-80B** | 🥇 최상 | 압도적 정확도, 매우 빠른 응답(1s) | 없음 (가장 안정적) |
| **Qwen3-14B** | 🥈 우수 | 80B급 성능 유지, 최고의 가성비 | 없음 |
| **Mistral-Small-24B** | 🥉 보통 | 무난한 성능, 텍스트 기반 호출 지원 | 병렬 호출 시 매칭 실패 간헐적 발생 |
| **Qwen3-32B** | ⚠️ 주의 | 한국어 대화 품질 우수 | 14B보다 낮은 FC 성능, 긴 지연시간(25s) |
| **Llama-3.3-70B** | ❌ 부적합 | 일반 대화 및 지시 이행 능력 상급 | **타입 오류**: 숫자를 문자열로 반환하여 실패 다수 |

---

## 🛠️ 설치 및 환경 설정

### 1. 의존성 설치
```bash
# 저장소 클론 및 이동
git clone <repository-url>
cd mcp-llm-bm-v2/gorilla/berkeley-function-call-leaderboard

# 패키지 및 리포트 엔진 설치
pip install -e .
pip install openpyxl
```

### 2. API 키 설정
`.env` 파일을 아래 경로에 생성합니다. (`.gitignore`에 의해 보호됨)
- **경로**: `gorilla/berkeley-function-call-leaderboard/.env`

```env
OPENROUTER_API_KEY=your_api_key_here
```

---

## 🚀 CLI 사용 가이드

### 1. 실행 모드 (Basic)
| 명령 | 설명 | 비고 |
| :--- | :--- | :--- |
| `python run_eval.py --quick` | 퀵 테스트 (카테고리별 2개) | 빠른 로직 검증용 |
| `python run_eval.py --full` | 전체 테스트 수행 | Non-Live 전체 완주 |
| `python run_eval.py --report-only` | 리포트만 재생성 | 기존 결과(score) 기반 |

### 2. 고급 옵션 (Advanced)
| 옵션 | 설명 | 예시 |
| :--- | :--- | :--- |
| `--models` | 특정 모델만 지정 | `--models "openrouter/qwen3-14b-FC"` |
| `--categories` | 특정 카테고리만 지정 | `--categories "simple_python,multiple"` |
| `--sample-size` | 카테고리별 샘플링 실행 | `--sample-size 100` |
| `--append` | 기존 결과에 누적 실행 | `--append --categories "parallel_multiple"` |
| `--num-threads` | 동시성(Thread) 제어 | `--num-threads 4` (속도 향상) |

---

## 📂 시스템 구조 (Architecture)

### 1. 디렉토리 트리
```text
mcp-llm-bm-v2/
├── 📄 README.md           # 프로젝트 통합 가이드
├── ⚙️ .env                # OpenRouter API 키 (보안)
└── 📂 gorilla/
    └── 📂 berkeley-function-call-leaderboard/
        ├── 🐍 run_eval.py       # [핵심] 평가/채점/리포트 통합 실행기
        ├── 🐍 excel_reporter.py # [엔진] 수식 기반 엑셀 생성 모듈
        ├── 📂 bfcl_eval/        # BFCL 원본 프레임워크 모듈
        ├── 📂 reports/          # 최종 엑셀 보고서 (결과물)
        ├── 📂 result/           # 모델 응답 원본 (JSONL)
        └── 📂 score/            # AST 채점 결과 (JSON)
```

### 2. 보고서(Excel) 시트 구성
| 시트명 | 주요 내용 | 특징 |
| :--- | :--- | :--- |
| **요약** | 핵심 KPI, 랭킹, 실패 원인 Top 5 | **100% 엑셀 수식**으로 실시간 연동 |
| **카테고리 매트릭스** | 모델 × 카테고리별 정확도 비교 | 최고/최저점 자동 강조 스타일 적용 |
| **상세** | 모든 테스트 케이스의 입출력 및 오답 근거 | 파라미터명, 기대/실제 타입 등 분석 힌트 포함 |

---

## 🔗 참고 자료
- [BFCL 공식 리더보드](https://gorilla.cs.berkeley.edu/leaderboard.html)
- [Gorilla 프로젝트 GitHub](https://github.com/ShishirPatil/gorilla)
- [OpenRouter API 문서](https://openrouter.ai/docs)
