# 경매·공매 능동형 AI 에이전트

> 매일 경매·공매 후보를 알아서 수집·분석·등급화하고, 시세차익 큰 매물과 오늘 확인할 일을 4개 채널(Telegram/Slack/Discord/Email)로 먼저 알려주는 지능형 보조 프로그램. 24개 에이전트 / 19개 대시보드 탭 / 138 pytest 통과 / mock-first 로 실제 API 키 없이 즉시 동작.

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
# 0) 환경 진단 (가장 먼저 실행 권장)
python scripts/doctor.py

# 1) DB 초기화
python main.py --init-only

# 2) mock 데이터 100건 생성 (DB 깨끗이 시작하려면 --reset)
python scripts/generate_mock_data.py --count 100 --seed 42 --reset

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

# 9) 외부 API 헬스체크
python scripts/check_apis.py

# 10) 매물 PDF 리포트 다운로드
python scripts/export_report.py --item-id 63
```

### 트러블슈팅

| 증상 | 해결 |
|---|---|
| `pip install` 실패 | Python 3.9+ 확인, `python -m pip install --upgrade pip` |
| `ModuleNotFoundError` | `python scripts/doctor.py` 로 어느 패키지 빠졌는지 확인 |
| DB 파일이 잠겨 있음 | 다른 streamlit/python 프로세스 종료 후 재시도 |
| GitHub raw 에서 파일이 한 줄로 보임 | GitHub raw 디스플레이 한계 - 실제 파일은 정상. clone 받아서 확인 |
| Streamlit Cloud 재시작 후 데이터 사라짐 | ephemeral fs 한계. 자동 mock 시드로 복구 또는 Turso 연결 권장 |
| `streamlit` 콘솔에 한글 깨짐 | 콘솔 코드페이지 (Windows: `chcp 65001`) - 브라우저는 정상 |

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

## 외부 영구 DB (Turso, 선택)

Streamlit Cloud 의 파일시스템은 ephemeral 이라 앱 재시작 시 SQLite DB 가 초기화됩니다. 자동 부트스트랩이 mock 데이터를 다시 시드하지만 **사용자 설정 / 워치리스트 / 알림 로그 / 백테스트 기록 / 튜닝 결과** 같은 영구 데이터는 사라집니다. 이를 해결하려면 Turso (libSQL Cloud) 를 사용하세요.

### Turso 사용 (무료 티어)

1. https://turso.tech 가입 → 데이터베이스 생성 → URL 과 auth token 복사
2. 의존성 설치:
   ```bash
   pip install libsql-experimental
   ```
3. `.env` 또는 Streamlit secrets:
   ```
   TURSO_DATABASE_URL=libsql://your-db-name.turso.io
   TURSO_AUTH_TOKEN=eyJhbGc...
   ```
4. 헬스체크: `python scripts/check_apis.py`
5. 다음 실행부터 자동으로 Turso 연결. 키 미설정 또는 `libsql-experimental` 미설치 시 SQLite fallback (안전).

### SQLite 백업/복원 (간단 대안)

Turso 없이도 SQLite 파일을 주기적으로 백업/복원 가능:

```bash
# 백업 (gzip 압축)
python scripts/backup_db.py
# data/exports/db_backup_YYYYMMDD_HHMMSS.db.gz 생성

# 복원
python scripts/restore_db.py --src data/exports/db_backup_xxx.db.gz --force
```

GitHub Actions 같은 CI에서 매일 백업 후 artifact 로 보관하거나, Streamlit Cloud 사이드바에 다운로드 버튼을 추가하는 방법도 가능합니다.

### 백엔드 자동 분기 동작

| 환경 | 활성 backend | 비고 |
|---|:---:|---|
| `TURSO_*` 미설정 | SQLite | 기본, 빠른 로컬 |
| `TURSO_*` 설정 + libsql 설치 | **Turso** | 클라우드 영구 |
| `TURSO_*` 설정 + libsql 미설치 | SQLite | 경고 후 fallback |
| Turso 연결 실패 | SQLite | 경고 후 fallback |

`core.db_backend.get_backend_name()` 으로 현재 활성 backend 확인 가능. 헬스체크 (`scripts/check_apis.py`) 의 `turso` 항목에서도 확인.

## 실제 API 전환 방법 (단계별)

mock-first 모드는 데모/개발용입니다. 실제 매물·시세 데이터로 운영하려면 다음 단계를 따라가세요.

### 1) 키 발급 (모두 무료, Claude만 유료)

| 항목 | 변수 | 발급처 |
|---|---|---|
| 국토부 실거래가 | `PUBLIC_DATA_SERVICE_KEY` | https://www.data.go.kr (무료, 즉시 발급) |
| 온비드 공매 | `PUBLIC_DATA_SERVICE_KEY` 공용 또는 `ONBID_API_KEY` | https://www.data.go.kr |
| 텔레그램 봇 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | https://t.me/BotFather (무료) |
| Claude API | `ANTHROPIC_API_KEY` + `USE_AI=true` | https://console.anthropic.com (유료) |

### 2) `.env` 또는 Streamlit secrets 에 키 입력

```bash
USE_MOCK_APIS=false
PUBLIC_DATA_SERVICE_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
USE_AI=true
ANTHROPIC_API_KEY=...
```

### 3) 헬스체크

```bash
python scripts/check_apis.py
```

각 API 의 인증/연결 상태를 콘솔에 표시합니다 (마스킹된 키 + 응답 샘플 카운트).

### 4) 실 매물 데이터 적재

```bash
python scripts/populate_real_data.py --count 100 --reset
```

내부적으로 `USE_MOCK_APIS=false` + `PUBLIC_DATA_SERVICE_KEY` 가 있을 때만 실 API를 호출합니다. 키가 없으면 자동으로 mock 으로 fallback (안전 동작).

### 5) 파이프라인 실행

```bash
python scripts/run_daily_pipeline.py --mock --count 100 --top 5
```

- `--mock` 플래그는 mock 데이터 _생성_ 옵션이고, **시세 매칭은 `USE_MOCK_APIS` 값을 따릅니다**.
- 실 API 모드에서 `price_matcher.fetch_trades()` 가 자동으로 `real_molit_api` 호출.
- 실 API 호출 실패하거나 매칭 결과 0건이면 자동 mock fallback (운영 안정성).

### 6) 자동 스위치 동작 요약

| 상태 | 시세 매칭 | 공매 수집 | Claude | 텔레그램 |
|---|:---:|:---:|:---:|:---:|
| `USE_MOCK_APIS=true` | mock | mock | mock | mock(콘솔) |
| `USE_MOCK_APIS=false` + 키 있음 | **real** | **real** | real (USE_AI=true 시) | **real** |
| `USE_MOCK_APIS=false` + 키 없음 | mock fallback | mock fallback | mock | mock(콘솔) |
| real 호출 실패 | mock fallback | (예외 로그) | mock | (예외 로그) |

### 7) 어댑터 모듈 구조

| 인터페이스 | mock 구현 | real 구현 |
|---|---|---|
| `fetch_trades(addr, type, area)` | `modules/valuation/mock_molit_api.py` | `modules/valuation/real_molit_api.py` |
| `list_public_sale_items(count)` | `modules/public_sale/mock_onbid_api.py` | `modules/public_sale/real_onbid_api.py` |
| `list_auction_items(count)` | `modules/auction/mock_auction_api.py` | `modules/auction/crawler.py` (Playwright, 별도 설치 필요) |
| `call_claude(prompt)` | `core/mock_api.py` | `core/ai_client.py` (anthropic SDK) |
| `send_message(text)` | `core/mock_api.py` | `modules/alerts/telegram.py` (requests) |

새 데이터 소스 추가는 동일 시그니처로 mock + real 한 쌍을 만들고 어댑터 진입점만 분기하면 됩니다.

### 8) 법원경매 크롤링 (선택)

`modules/auction/crawler.py` 는 Playwright 기반이라 별도 설치 필요:

```bash
pip install playwright>=1.44
playwright install chromium
```

#### selector 헬스체크

법원경매 사이트(courtauction.go.kr)는 selector 가 자주 바뀌므로 실 크롤링 전에 헬스체크 권장:

```bash
python scripts/check_court_auction.py
```

`SELECTORS` dict 의 각 key 가 사이트에 살아 있는지 1회 검증하고 깨진 selector 를 콘솔에 표시합니다 (예: `[FAIL] result_table = table.Ltbl_list`).

#### selector 업데이트 워크플로

1. `python scripts/check_court_auction.py` 실행 → FAIL 표시 확인
2. 브라우저로 https://www.courtauction.go.kr 접속
3. F12 개발자 도구 → Elements 패널에서 해당 요소 우클릭 → **Copy selector**
4. `modules/auction/crawler.py` 의 `SELECTORS` dict 해당 key 수정 (한 곳만 바꾸면 됨)
5. `python scripts/check_court_auction.py` 로 재검증
6. OK 면 git commit

#### 실 크롤링 실행

```bash
python scripts/populate_real_data.py --count 50 --include-auction
```

`--include-auction` 플래그가 있을 때만 법원경매 크롤링이 실행됩니다 (기본은 온비드만). Playwright 미설치 / 사이트 selector 깨짐 / 네트워크 실패 시 빈 결과 + 로그 경고로 안전 fallback (운영 무중단).

#### 어댑터

| 인터페이스 | mock | real |
|---|---|---|
| `list_auction_items(count)` | `modules/auction/mock_auction_api.py` | `modules/auction/real_auction_api.py` (crawler 호출) |
| `validate_site_selectors()` | (해당 없음) | `modules/auction/crawler.py` |

mock 과 real 어댑터의 함수 시그니처가 동일하므로 호출자 코드는 변경 없이 데이터 소스만 바뀝니다.

## 주의사항 — 권리분석 표현 원칙

> 본 프로젝트의 권리분석 기능은 **법률 판단이 아니라 위험요소 체크리스트와 추가 확인사항을 제공**하는 보조 도구입니다.

- "안전합니다", "입찰해도 됩니다", "보장됩니다", "수익 확정" 같은 **단정 표현을 사용하지 않습니다**.
- 모든 추천 결과는 "**검토 후보 / 주의 필요 / 추가 확인 필요 / 현재 자료 기준**" 표현으로 제시됩니다.
- 등급 X 는 거품/음수 차익으로 자동 제외 — 입찰 추천 아님 (참고용 분류).

## Public Repo 주의사항

저장소가 public 으로 공개되었거나 향후 공개할 계획이 있다면 다음 사항을 반드시 확인하세요.

- `.env` 파일이 git 에 올라가지 않는지 확인 (`.gitignore` 에 포함됨)
- API 키가 코드/README/예제에 직접 적혀 있지 않은지 확인 (`.env.example` 만 커밋)
- `data/*.db`, `logs/*.log`, `data/exports/*.json|csv|md|pdf|db.gz` 가 ignore 되는지 확인
- `.streamlit/secrets.toml` 도 ignore (예시는 `.streamlit/secrets.toml.example` 만 커밋)
- `git log --all -p -S "sk-"` 로 토큰 패턴이 과거 커밋에 남아있지 않은지 검사 권장

이미 push 한 이후라면:
- 키 즉시 폐기 후 재발급
- private 으로 visibility 변경 (Settings → Danger Zone)

## 면책

- 본 프로그램은 개인 학습·개발용 MVP 입니다.
- 추천 결과는 **현재 자료 기준 참고용**이며, 투자 판단과 법률 판단은 사용자가 별도로 검토해야 합니다.
- 실제 입찰 전 매각물건명세서, 등기부등본, 현장조사, 전문가 검토를 반드시 병행하세요.
