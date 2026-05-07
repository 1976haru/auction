# 경매·공매 능동형 AI 에이전트

> 사용자가 직접 검색하지 않아도 매일 경매·공매 후보를 수집·분석·추천해 주는 개인용 보조 프로그램.

## 현재 상태

**MVP / Mock-first 모드**입니다. 실제 API 키가 없어도 전체 플로우(수집 → 분석 → 추천 → 브리핑 → 액션 → 변화감지 → 시뮬레이션)가 끝까지 돌아갑니다.

- 법원경매, 온비드 공매, 국토부 실거래가, Claude API, 텔레그램 API는 **키가 없으면 자동으로 mock 응답**으로 대체됩니다.
- 실제 API 연동은 인터페이스 자리만 마련되어 있고, 현재 기본 동작은 mock 입니다.

## 주요 기능

- 자연어 검색 (예: "시세차익 큰 물건 5개", "요즘 괜찮은 거 있어?")
- 의도 이해 (애매한 표현 처리)
- 위험 키워드 분석 + 위험 등급 (high / medium / low)
- 위험 키워드별 추가 확인사항(체크리스트) 자동 생성
- 실거래가 매칭 + 시세 신뢰도 산정
- 신뢰도 종합 산정 (시세 / 권리 / 문서 / 주소)
- 예상 시세차익 / ROI / 부대비용 / 입찰가 시뮬레이션 (보수/기준/공격)
- 사용자 선호 학습 (관심물건/피드백 기반)
- 추천 점수화 + 등급 (A/B/C/D/X)
- 일일 브리핑 + 오늘 할 일(액션 아이템) 자동 생성
- 변화 감지 (최저가/유찰/입찰기일/문서 공개)
- 결과 시뮬레이션 (mock 매도가 기반 가상 성과)
- 물건별 Q&A
- Streamlit 대시보드 13개 탭

## 지능형 에이전트 구성

```
agents/
- natural_language_agent.py     # 자연어 -> 검색조건
- intent_understanding_agent.py # 애매한 의도 보정
- price_analysis_agent.py       # 시세 매칭 + 신뢰도
- legal_risk_agent.py           # 권리 위험 분석
- risk_checklist_agent.py       # 키워드별 체크리스트
- confidence_agent.py           # 신뢰도 종합
- preference_learning_agent.py  # 사용자 선호 학습
- recommendation_agent.py       # 추천 점수화 + 등급
- bidding_agent.py              # 입찰가 추천
- daily_briefing_agent.py       # 오늘의 브리핑
- action_planner_agent.py       # 오늘 할 일
- change_detection_agent.py     # 변화 감지
- outcome_simulation_agent.py   # 결과 시뮬레이션
- item_qa_agent.py              # 물건 Q&A
- reasoning_report_agent.py     # 추천 근거 텍스트
- report_agent.py               # 종합 리포트
- daily_recommendation_agent.py # 일일 추천 + 알림
- agent_orchestrator.py         # 전체 오케스트레이션
```

## 프로젝트 구조

```
auction-agent/
├── core/                # config, database, logger, ai_client, mock_api, utils, alerts
├── agents/              # 17개 에이전트
├── modules/
│   ├── auction/         # 법원경매 (실제 크롤러 + mock api)
│   ├── public_sale/     # 온비드 공매 (실제 + mock)
│   ├── valuation/       # 실거래가 (mock + price_matcher)
│   ├── documents/       # 문서 mock 생성
│   ├── risk/            # 위험 키워드 사전
│   ├── alerts/          # 텔레그램 (mock 콘솔 출력)
│   ├── keyword_analyzer.py  # 하위 호환 shim
│   └── profit_calculator.py # 수익/입찰가 계산
├── dashboard/           # Streamlit 13탭
├── scripts/             # generate_mock_data, run_daily_pipeline, run_stress_test, export_results
├── tests/               # pytest
├── data/
│   ├── fixtures/
│   └── exports/         # JSON / CSV / Markdown 결과
├── logs/
├── .github/workflows/   # CI
├── main.py
├── .env.example
└── requirements.txt
```

## 설치

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env       # macOS/Linux
copy .env.example .env     # Windows
```

`.env` 는 기본값(`USE_MOCK_APIS=true`)으로 두면 키 없이도 동작합니다.

## 실행 방법

### 초보자용 명령어 모음

```bash
# 1) DB 초기화
python main.py --init-only

# 2) mock 데이터 100건 생성
python scripts/generate_mock_data.py --count 100 --seed 42

# 3) 일일 파이프라인 실행 (mock-first)
python scripts/run_daily_pipeline.py --mock --count 100 --top 5

# 4) CLI 추천 한 번
python main.py recommend "시세차익 큰 물건 5개 찾아줘"

# 5) 대시보드 실행
streamlit run dashboard/app.py

# 6) 테스트 실행
pytest tests/ -v

# 7) 빠른 스트레스 테스트
python scripts/run_stress_test.py --count 1000 --queries 20

# 8) 결과 내보내기
python scripts/export_results.py --target all
```

### 핵심 사용 시나리오

```text
사용자가 프로그램 실행 → mock 데이터 자동 생성/수집 → 시세 매칭 → 위험 분석 →
신뢰도 산정 → 추천 점수화/등급 → 오늘 우선 볼 5건 + 오늘 할 일 출력
```

## GitHub 업로드 전 체크리스트

- [ ] `.env` 파일이 git에 올라가지 않는지 확인 (`.gitignore` 반영됨)
- [ ] `data/*.db`, `logs/*.log`, `data/exports/*` 가 ignore 되는지 확인
- [ ] API 키가 코드/README/예제에 직접 적혀 있지 않은지 확인
- [ ] `pytest tests/` 가 모두 통과하는지 확인
- [ ] `python scripts/run_daily_pipeline.py --mock --count 50 --top 5` 가 정상 종료되는지 확인

## Streamlit Cloud 배포 (무료)

이 저장소는 [Streamlit Community Cloud](https://share.streamlit.io) 에 그대로 배포 가능합니다. private 저장소 + secrets 도 무료 티어에서 지원됩니다.

### 1. 사전 준비
- GitHub 계정 (private repo OK)
- Streamlit Community Cloud 계정 (https://share.streamlit.io 에서 GitHub 로그인)

### 2. 배포 단계
1. https://share.streamlit.io → **New app**
2. 다음과 같이 설정:
   - **Repository**: `1976haru/auction` (또는 본인 저장소)
   - **Branch**: `main`
   - **Main file path**: `dashboard/app.py`
   - **Python version**: 3.11 (`runtime.txt` 자동 인식)
3. **Deploy** 클릭 → 1~2분 후 https://<app-name>.streamlit.app 에서 접근 가능

### 3. Secrets 설정 (선택 — mock 모드면 불필요)
앱 페이지 우상단 ⋮ → **Settings** → **Secrets** 메뉴에 다음 내용 붙여넣기:

```toml
USE_MOCK_APIS = "true"   # 키 없으면 그대로 두면 모든 데모 동작이 mock으로
USE_AI = "false"
ANTHROPIC_API_KEY = ""
PUBLIC_DATA_SERVICE_KEY = ""
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
```

전체 키 목록은 `.streamlit/secrets.toml.example` 참고. Streamlit Cloud 의 secret 은 자동으로 `os.environ` 에 복사됩니다 (`dashboard/bootstrap.py`).

### 4. 자동 부트스트랩
첫 실행 시 DB 가 비어 있으면 mock 데이터 80건 + 분석 + 추천이 자동 생성되어 사이드바에 "자동 시드 완료" 안내가 표시됩니다. 방문자가 즉시 모든 탭을 둘러볼 수 있습니다.

### 5. 운영 모드 전환
- secrets 에서 `USE_MOCK_APIS = "false"` + 실제 API 키 입력 → 다음 재시작부터 실 API 호출
- 자동 시드는 mock 모드에서만 의미 있으며, 실제 API 모드에서는 GitHub Actions daily.yml 의 cron 또는 수동 파이프라인으로 데이터 채움

### 6. 제약사항
- Streamlit Cloud 의 파일시스템은 ephemeral — 앱 sleep/restart 시 SQLite DB 가 초기화될 수 있음 (자동 시드로 복구)
- 외부 API key 는 secrets 으로 관리 (절대 코드에 하드코딩 금지)
- 무료 티어는 동시 1 visitor + 1 GB 메모리 제한

## 실제 API 전환 방법

`.env` 에서 다음 항목을 실제 키로 채우고 `USE_MOCK_APIS=false` 로 변경:

| 항목 | 변수 | 발급처 |
|---|---|---|
| Claude API | `ANTHROPIC_API_KEY`, `USE_AI=true` | Anthropic Console (유료) |
| 국토부 실거래가 | `PUBLIC_DATA_SERVICE_KEY` | 공공데이터포털 (무료) |
| 온비드 공매 | `PUBLIC_DATA_SERVICE_KEY` 또는 `ONBID_API_KEY` | 공공데이터포털 |
| 텔레그램 봇 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | BotFather (무료) |

실제 API 연동은 다음 모듈의 인터페이스 자리에 구현하면 됩니다.

- `modules/auction/crawler.py` (Playwright 크롤링)
- `modules/public_sale/onbid_client.py` (REST 호출)
- `modules/price/molit_api.py` (XML 파싱)

mock 모듈은 `modules/.../mock_*.py` 로 분리되어 있어 인터페이스만 동일하게 맞추면 됩니다.

## 주의사항

> 본 프로젝트의 권리분석 기능은 **법률 판단이 아니라 위험요소 체크리스트와 추가 확인사항을 제공**하는 보조 도구입니다.

- "안전합니다", "입찰해도 됩니다", "보장됩니다" 같은 단정 표현을 사용하지 않습니다.
- 모든 추천은 "검토 후보 / 주의 필요 / 추가 확인 필요" 표현으로 제시됩니다.

## 면책

- 본 프로그램은 개인 학습·개발용 MVP 입니다.
- 추천 결과는 참고용이며, 투자 판단과 법률 판단은 사용자가 별도로 검토해야 합니다.
- 실제 입찰 전 매각물건명세서, 등기부등본, 현장조사, 전문가 검토를 반드시 병행하세요.
