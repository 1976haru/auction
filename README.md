# 경매·공매 능동형 AI 에이전트

[![CI](https://github.com/1976haru/auction/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/1976haru/auction/actions/workflows/ci.yml)
[![Daily](https://github.com/1976haru/auction/actions/workflows/daily.yml/badge.svg)](https://github.com/1976haru/auction/actions/workflows/daily.yml)
[![Pages](https://img.shields.io/badge/GitHub%20Pages-live-1f77b4)](https://1976haru.github.io/auction/)

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

# 7-2) 대규모 스트레스 테스트 (장시간 - 1시간 내외)
python scripts/run_stress_test.py --count 5000 --queries 50

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

### 스트레스 테스트 벤치마크

본 저장소에서 실측한 mock-first end-to-end 성능 (단일 머신 / Python 3.14 / 로컬 SQLite 기준):

| 시나리오 | 총 소요 | 생성 | 시세 | 위험 | 신뢰 | 쿼리 (avg/회) |
|---|---:|---:|---:|---:|---:|---:|
| `--count 500 --queries 5` | **46.72s** | 7.69s | 4.52s | 7.45s | 6.80s | 4.04s |
| `--count 5000 --queries 50` | **3437.35s (≈ 57분)** | 90.38s | 51.01s | 106.88s | 98.14s | 61.82s |

- 5000-건 환경에서는 추천 쿼리 phase 가 전체의 **89.9%** 를 차지 (item lookup 횟수가 N×3 으로 누적)
- 결과는 `stress_test_results` 테이블 + `data/exports/stress_test_report.json` 으로 저장됨
- 운영 단계에서 추천 응답 시간이 중요해지면 `_enrich()` 의 row-by-row lookup 을 batch JOIN 으로 묶거나 분석 결과를 in-memory 캐시 하는 최적화가 의미 있음

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

## GitHub Pages 정적 대시보드 (탐색형 UI · PWA)

서버 없이 GitHub URL 만으로 데스크탑·스마트폰 모두 확인 가능한 **탐색형(검색·필터·차트·AI) 정적 데모**입니다. Streamlit 앱과 별개로 동시에 운영하며, PWA 로 홈 화면 추가 시 standalone 앱처럼 동작합니다.

**최종 접속 주소**: https://1976haru.github.io/auction/

> 외부 라이브러리 0 (모든 차트·sparkline·시뮬레이터·인쇄가 순수 SVG/CSS/JS). 라이브 외부 API 호출 없음 (mock JSON 만 fetch). 사용자 데이터는 자기 폰 localStorage 에만 저장.

### 화면 미리보기 (자동 캡처)

스크린샷은 `.github/workflows/screenshot.yml` 가 변경된 파일을 감지할 때마다 Playwright/Chromium 으로 자동 갱신합니다.

| 데스크탑 (라이트, 전체 페이지) | 모바일 (라이트, 전체 페이지) |
|---|---|
| ![Desktop light](docs/screenshots/desktop-light.png) | ![Mobile light](docs/screenshots/mobile-light.png) |

| 데스크탑 다크 (뷰포트) | 매물 상세 모달 (뷰포트) |
|---|---|
| ![Desktop dark](docs/screenshots/desktop-dark.png) | ![Detail modal](docs/screenshots/detail-modal.png) |

### 정적 대시보드 기능

**검색 · 탐색**
- **통합검색**: 주소 / 사건번호 / 물건명 / 키워드를 한 칸에서 검색 (디바운스 즉시 갱신)
- **최근 검색어**: 검색바 포커스 시 localStorage 최근 8개 자동 노출 + 개별/전체 삭제
- **빠른 메뉴 칩**: 전체 / ★ 내 관심 / 📝 메모 / 🆕 변화 / 경매 / 공매 / 아파트 / 오피스텔 / 빌라 / 상가 / 토지 / 고수익 / 저위험 / 입찰임박 / 고위험
- **필터 프리셋 (1클릭)**: ⭐ 추천 후보 / 🚀 고수익 저위험 / ⏰ 임박 후보 / 🏠 서울 아파트 / 🥇 A등급만
- **상세 필터**: 지역, 물건종류, 경매·공매, 최저가 범위, 유찰횟수, 입찰기일(D-N), 위험도, 추천등급
- **정렬**: 추천점수, 시세차익, 수익률, 입찰기일 임박, 최저가, 위험 낮은순
- **AI 에이전트 검색**: 자연어 한 줄을 rule-based 로 해석해 즉시 재정렬·재필터 (외부 API 호출 없음)
- **URL 동기화**: 검색·필터·정렬·뷰 상태를 querystring 에 반영 → 폰↔PC 공유, 새로고침해도 그대로

**매물 카드 / 상세**
- **카드 ↔ 테이블 전환** + **30개 페이지네이션** (더 보기)
- **임박 배지** (D-3 빨강 / D-7 주황) + **변화 감지 배지** (🆕 신규 / ⬇ 인하 / 📅 기일 / 🔄 유찰 / ⚠ 상태)
- **상세 모달**: 기본정보, 시세분석, **시세 트렌드 sparkline (12개월)**, 예상 입찰가, **입찰가 시뮬레이터 (슬라이더, 차익·ROI·취득세·금융비 즉시 계산)**, 위험 분석, 추가 확인사항, 다음 액션, **추천 점수 분해 (5개 항목 가로 막대)**, AI 한줄 판단, **최근 변화 7일**, **내 메모**

**브리핑 / 차트**
- **오늘의 브리핑 / 추천 TOP 5 / 오늘 할 일 / 위험 요약 / 신뢰도 요약**
- **분석 차트** (외부 라이브러리 0): 등급별 평균 차익 막대 + 지역별 위험 분포 스택 — 현재 필터 결과 기준 자동 갱신

**개인화 (localStorage, 자기 폰에만 저장)**
- **★ 관심 매물**: 카드/모달에서 토글, "★ 내 관심" 칩으로 모아 보기
- **📝 매물 메모**: 자동 저장 (입력 600ms 디바운스 + blur), 카드에 📝 배지, "📝 메모" 칩으로 필터
- **⇆ 비교 트레이**: 카드 길게 누름 또는 ⇆ 토글로 2~5개 담기 → 가로 스크롤 비교 모달 (▲ 최고 / ▼ 최저 자동 마킹) → 🖨 인쇄/PDF 도 가능
- **데이터 백업 (⚙ 설정)**: 관심·메모·비교·검색어·테마를 한 JSON 파일로 다운로드 / 덮어쓰기·병합 복원 / 전체 지우기

**공유 · 내보내기**
- **🔗 매물 공유**: 시스템 공유 시트 (카톡/메시지/AirDrop 등) + `#item-N` 해시 딥링크 — 받은 사람이 링크 열면 바로 그 매물 모달
- **🔗 결과 공유**: 현재 필터·정렬이 적용된 URL + 한 줄 요약을 시스템 공유 시트로
- **CSV / JSON 다운로드**: 현재 필터된 결과를 23개 컬럼(엑셀 한글 OK) / 메타 포함 JSON 으로
- **🖨 매물 PDF / 비교 PDF**: 모달만 풀페이지로 인쇄 → "PDF로 저장"

**시스템**
- **다크 모드**: `prefers-color-scheme` 자동 + 🌙/☀️ 명시 토글 + localStorage 영구 저장 + 모바일 상단바 색 동기화
- **PWA**: 홈 화면 추가, 오프라인 캐시 (앱 셸 cache-first + mock JSON stale-while-revalidate), 새 버전 토스트 알림
- **키보드 단축키 (PC)**: `/` 검색 / `?` 도움말 / `r` 초기화 / `t` 테마 / `1`·`2` 카드/테이블 / `c` 비교 / `g` 등급 순환 / `Esc` 닫기. ⌨ 버튼은 모바일에서도 도움말 모달로 진입 가능
- **반응형**: PC 카드 2~4열 + 풀폭 테이블, 모바일 1열 + 가로 스크롤 칩 + 풀폭 모달, hover 효과는 `@media (hover: hover)` 가드, 탭 지연 제거 + 스크롤 중 우발 탭 차단 + 길게 누름 비교

### 1) 한 번만 설정
GitHub 저장소에서:
1. **Settings** → **Pages**
2. **Build and deployment** → **Source**: `Deploy from a branch`
3. **Branch**: `main` / **Folder**: `/docs`
4. **Save** → 1~2분 후 위 URL 에서 접속 가능

(Actions 워크플로 없이 branch `/docs` 방식이면 충분합니다.)

### 2) 정적 데이터 갱신
```
python scripts/export_static_dashboard.py
```
- 기존 SQLite DB 가 있으면 → DB 에서 추출 (모든 매물에 추천점수·등급·시세·위험·체크리스트·추가확인사항·신뢰도·예상차익 포함)
- DB 가 비어 있으면 → mock 파이프라인을 한 번 돌려서 시드 후 추출
- 그래도 실패하면 → 자체 hard-coded 100건 샘플 fallback
- 결과: `docs/data/mock_dashboard.json` 갱신 (검색·필터·상세보기에 필요한 모든 필드 포함)

push 후 GitHub Pages 가 자동 재배포됩니다.

### 3) 로컬 미리보기
```
python -m http.server 8000 -d docs
```
→ 브라우저: `http://localhost:8000`

확인할 것: index.html / styles.css / app.js / data/mock_dashboard.json 로딩, 통합검색, 빠른 메뉴, 필터, 카드/테이블 전환, 상세 모달, AI 에이전트 검색, 모바일 폭에서 깨지지 않음, PC 폭에서 너무 좁지 않음.

### 4) 스마트폰 확인
- 가장 쉬운 방법: 위 GitHub Pages URL 을 폰 브라우저에서 열기
- 로컬 미리보기일 때: PC 와 같은 Wi-Fi 에서 폰 브라우저로 `http://<PC_IP>:8000` (예: `http://192.168.0.5:8000`)

정적 대시보드는 `docs/styles.css` 의 `@media (max-width: 1024px) / 640px` 분기로 자동 전환됩니다 (검색바 sticky, 카드 1열, 칩 가로 스크롤, 모달 전체폭).

### Streamlit 풀버전과의 차이

| 영역 | GitHub Pages 정적 (`docs/`) | Streamlit 풀버전 (`dashboard/app.py`) |
|---|---|---|
| 접근 | 가입·서버 없이 URL 한 줄, PWA 설치 가능 | Streamlit Cloud 배포 또는 로컬 실행 |
| 데이터 | 빌드 시점 mock JSON (~200KB) | 라이브 SQLite DB (자동 시드) |
| 검색·필터·정렬 | ✅ (URL 동기화) | ✅ (통합검색 탭) |
| 카드 / 테이블 전환 | ✅ + 30개 페이지네이션 | 데이터프레임 |
| 매물 상세 모달 | ✅ + 시세 sparkline + 시뮬레이터 | ✅ + plotly 차트 |
| 차트 | 등급 차익 / 지역 위험 (SVG) | plotly 풀세트 (트렌드·산점도·시계열) |
| 즐겨찾기·메모 | localStorage (개인) | DB 워치리스트 (운영) |
| 비교 | 트레이 + 모달 + PDF | 비교 탭 (5건 한도) |
| 백테스트·자동 튜닝 | ❌ | ✅ |
| 알림 발송 | ❌ (수신만 PWA) | Telegram·Slack·Discord·Email |
| PDF / 인쇄 | 브라우저 print (모달 단위) | reportlab PDF |
| 다크 모드 | ✅ (자동 + 토글) | ❌ |
| 공유 | Web Share API + 해시 딥링크 | URL 복사 |

### 면책
- 표시된 모든 매물은 **mock 데이터**이며 실제 거래 대상이 아닙니다.
- 실제 법원경매·온비드·국토부 API 호출, 실제 입찰, 실제 금전거래, 실제 외부 전송은 **하지 않습니다**.
- 권리분석 결과는 **참고용 위험 체크리스트와 추가 확인사항**으로만 제공되며, 법률·투자 판단을 단정하지 않습니다.
- 실제 입찰 전에는 등기부등본·전입세대열람·현장조사·전문가 자문이 필요합니다.

## 변경 이력 (정적 대시보드)

GitHub Pages 정적 대시보드의 누적 개선을 묶음 단위로 정리합니다. 모든 기능은 외부 라이브러리 0, 외부 API 호출 0, 사용자 데이터는 자기 폰 localStorage 에만 저장됩니다.

### Phase A — 출시 + 기본 UX (`af5d50c` ~ `3af4b16`)
- 정적 대시보드 초기 출시 (`docs/index.html` + `app.js` + `styles.css` + `mock_dashboard.json`)
- 모바일 카드 탭 반응성 수정 (호버 stuck 방지 + 탭 지연 제거 + 우발 탭 차단)
- URL state 동기화: 검색·필터·정렬·뷰가 querystring 에 반영, 새로고침/공유해도 복원
- ☆ 관심 매물(localStorage) + "★ 내 관심" 칩
- 위험 키워드 → 매물 필터 연결 (위험 요약의 칩 클릭 시 그 키워드 보유 매물만)
- 임박 D-3 빨강 / D-7 주황 배지 + 결과 헤더 정렬 메타 칩
- 결과 CSV / JSON 다운로드 (UTF-8 BOM, 23개 컬럼, 메타 포함)

### Phase B — 시각화 + PWA + 비교 (`0ee0081` ~ `08fbd5c`)
- **B6 미니 차트** — 등급별 평균 차익 + 지역별 위험 분포 (순수 SVG)
- **B9 PWA** — manifest + service worker + 설치 버튼, 앱 셸 cache-first / mock JSON stale-while-revalidate, 오프라인·새 버전 토스트
- **B8 다크 모드** — `prefers-color-scheme` 자동 + 🌙 토글, FOUC 방지 인라인 스크립트, `theme-color` 메타 동기화
- **B5 비교 트레이** — 카드 길게 누름·⇆ 토글로 2~5건 담기, 가로 스크롤 비교 모달, ▲ 최고 / ▼ 최저 자동 마킹

### Phase C — 운영 안정성 (`fa5cd6a` ~ `ace2a95`)
- **CI 파이프라인 보강** — push/PR 마다 `pytest` + `export_static_dashboard.py` JSON 검증, daily cron 이 변경된 JSON 을 자동 커밋·푸시 (`[skip ci]`)
- README 상단 CI / Daily / Pages 배지
- **C11 변화 감지 배지** — 매물별 `change_events`(7일) + 데모 합성 태그(🆕 신규 / ⬇ 인하 / 📅 기일 / 🔄 유찰 / ⚠ 상태) + "🆕 변화" 칩 + 모달 "최근 변화" 섹션

### Phase D — PC / 키보드 (`068dbd2` ~ `2ae4df3`)
- **D14 키보드 단축키** — `/` 검색 / `?` 도움말 / `r` 초기화 / `t` 테마 / `1`·`2` 카드·테이블 / `c` 비교 / `g` 등급 순환 / `Esc` 닫기
- 검색바 ⌨ 도움말 버튼 (모바일에서도 노출)

### Phase E — 매물 상세 강화 (`95d76d9` ~ `2d32fad`)
- **E18 시세 트렌드 sparkline** — 12개월 라인 + 감정가/최저가/추정시세 점선 기준선 + hover 툴팁
- **E17 매물 인쇄/PDF** — 모달만 풀페이지로 인쇄, 다크 모드여도 흰 배경 검은 글자, `@page` 14mm
- **E16 추천 점수 분해** — 차익(35) / 수익률(25) / 위험(20) / 신뢰도(10) / 임박(10) 가로 막대 + 합계

### Phase F — 공유 · 검색 · 페이지 (`9304d1a` ~ `158f1b9`)
- **F21 매물 공유** — Web Share API + clipboard 폴백 + `#item-N` 해시 딥링크
- **F22 비교 모달 PDF** — best/worst 셀 색 유지, 가로 스크롤 비활성
- **F26 필터 프리셋** — ⭐ 추천 후보 / 🚀 고수익 저위험 / ⏰ 임박 / 🏠 서울 아파트 / 🥇 A등급
- **F25 페이지네이션** — 30개 + "더 보기 (+30 / N건 남음)"
- **F24 최근 검색어** — 검색바 포커스 시 localStorage 최근 8개 (개별/전체 삭제)
- **F27 Undo 토스트** — 필터 초기화/프리셋 적용 직후 "되돌리기"

### Phase G — 개인화 (`7780b1e` ~ `e9965f6`)
- **G29 입찰가 시뮬레이터** — 슬라이더로 입찰가 ↔ 차익/ROI/총비용 실시간 계산 (취득세·금융비 포함)
- **G28 매물 메모** — textarea 자동 저장(600ms 디바운스 + blur), 카드 📝 배지, "📝 메모" 칩
- **G30 결과 공유** — 현재 필터·정렬 URL + 한 줄 요약을 시스템 공유 시트로
- **G31 결과 헤더 sticky** — 검색바 아래에 자동 고정 (ResizeObserver 기반 동적 offset)

### Phase H — 백업·접근성·문서 (`1307078` ~ `42ee20b`)
- **H35 데이터 백업/복원** — ⚙ 설정 모달, JSON 다운로드/덮어쓰기·병합 복원, 통계 카드, 전체 지우기
- **H36 매물 본 이력** — 모달 열 때 자동 기록(최대 20건), "👁 최근 본" 칩
- **H33 즐겨찾기 자동 우선** — 기본 보기에서 ★ 매물을 어떤 정렬에서도 맨 위로 안정 정렬
- **H38 Lighthouse 보강** — Open Graph + Twitter card + canonical, `:focus-visible`, `prefers-reduced-motion`, `<noscript>` 안내
- **H37 README 기능 매트릭스** + Streamlit 풀버전과 비교 표
- **H39 RSS 피드** — `docs/feed.xml` 자동 생성 (점수 desc top 50, `#item-N` 해시 딥링크) + index `<link rel="alternate">`
- **H41 인앱 About** — ℹ 버튼 + 4개 섹션 도움말 (이 앱은 / 어떻게 쓰나 / 데이터·보안 / 면책)
- **H44 README changelog** — 정적 대시보드 누적 작업을 Phase 단위로 정리
- **H45 스크린샷 자동 캡처** — `.github/workflows/screenshot.yml` + `scripts/capture_screenshots.py` (Playwright/Chromium) → 4컷 자동 갱신, README 임베드, `[skip ci]` 자동 커밋
- **H46 풀페이지 도움말** — `docs/help.html` (10개 섹션 + 목차 + FAQ + 단축키 표), JS 의존성 0, 검색엔진 색인용
- **H47 sitemap + robots** — `docs/sitemap.xml` (2 URL) + `docs/robots.txt` (Allow + Sitemap 절대 URL)

### Phase I — 개인화·맞춤 추천 (`39bdc3f` ~ `d8a7c65`)
- **I49 사용자 피드백 추천** — ★(3) + 📝(3) + 👁(1) 시그널에서 선호 지역·종류·가격대 추출, 시그널 ≥ 3 일 때 "✨ 맞춤 추천" 카드 5장 자동 노출. 매칭 사유 라벨 (선호 지역/종류/비슷한 가격대)
- **I48 비슷한 매물** — 매물 상세 모달 안에 같은 지역/종류/가격대 매물 3건 미니 카드, 카드 탭 시 같은 모달 안에서 매끄러운 체이닝 내비게이션
- **I50 입찰가-차익 곡선** — G29 시뮬레이터에 SVG 곡선 추가 (30포인트, 0선 + 양/음 영역 음영, 손익분기점 자동 계산, 현재 입찰가 마커 색이 양수=초록 / 음수=빨강)
- **I47 매물 클러스터링** — 주소를 region+gu+dong 으로 파싱, 같은 위치 2건 이상 매물 top 5 카드 (등급 분포·평균 점수·평균 차익·고위험 경고). 카드 탭 시 그 동만 필터링 + 되돌리기 토스트

### Phase J — 모달·메모 UX (`398fc26` ~ `a5d9e3e`)
- **J52 매물 모달 좌우 네비** — 모달 헤더에 ‹ › 버튼 + ArrowLeft/Right 키. 현재 필터 결과 순서대로 다음/이전 매물로 즉시 전환, 본문 자동 맨 위, URL 해시 갱신, 'N/M' 위치 표시
- **J53 메모 검색** — ⚙ 설정 모달에 '📝 내 메모 모아보기' 섹션 — 모든 메모 리스트(제목+스니펫+상대시간) + 매물 제목·메모 본문 가로지르기 검색 + 항목 탭으로 그 매물 상세 모달 이동

### Phase K — PC 고급 사용성 (`ffc3ec3` ~ `c8f54bc`)
- **K71 카드 키보드 네비** — j/↓ 다음 카드, k/↑ 이전 카드, Enter 상세 모달 열기. 포커스된 카드 파란 outline + 자동 스크롤. 검색 입력/모달 열림/테이블 보기 시 무시
- **K73 카드 다중 선택** — ☑ 토글 모드. 카드 탭 = 선택 토글, 하단 액션 바: ★ 일괄 등록·해제 (toggle 시맨틱) / ⇆ 비교 트레이에 추가 (5건 한도 안내) / 📥 CSV (선택만) / 모두 해제 / 종료. 선택 모드 중 비교 트레이는 자동 숨김

### 누적 사용자 데이터 키
| 키 | 내용 | 백업 포함 |
|---|---|---|
| `auction:favorites:v1` | ★ 관심 매물 ID 셋 | ✅ |
| `auction:notes:v1` | 매물별 메모 (text + updatedAt) | ✅ |
| `auction:compare:v1` | 비교 트레이 ID 리스트 (~5) | ✅ |
| `auction:searches:v1` | 최근 검색어 (~8) | ✅ |
| `auction:viewed:v1` | 본 이력 (~20, ts) | ✅ |
| `auction:theme:v1` | 라이트/다크 명시 선택 | ✅ |

## 브라우저 / 스마트폰 접속 방법 (Streamlit 풀버전)

### PC 웹브라우저
- 로컬: `streamlit run dashboard/app.py` → 자동으로 `http://localhost:8501` 열림
- 0.0.0.0 바인딩 (Replit / Codespaces / Docker):
  ```
  streamlit run dashboard/app.py --server.address=0.0.0.0 --server.port=8080
  ```
  → `http://localhost:8080` 접속
- Streamlit Cloud: 위 배포 단계 완료 후 `https://<app-name>.streamlit.app`

### 스마트폰
1. **Streamlit Cloud / Replit 사용 시 (가장 쉬움)**
   - 위 방법으로 배포 후 받은 URL 을 그대로 스마트폰 브라우저에서 열기
   - 좌측 상단 햄버거 아이콘 → "메뉴" 라디오로 13개 탭 전환
   - 사이드바의 "컴팩트 모드 (모바일)" 토글을 켜면 카드/표가 세로로 좁게 정렬되어 가독성 향상
2. **로컬 PC 에서 같은 Wi-Fi 의 폰으로 보기**
   - PC 에서 `streamlit run dashboard/app.py --server.address=0.0.0.0 --server.port=8080`
   - PC 의 로컬 IP 확인 (Windows: `ipconfig`, macOS/Linux: `ifconfig` 또는 `ip a`)
   - 폰 브라우저에서 `http://<PC_IP>:8080` (예: `http://192.168.0.5:8080`)
   - 방화벽이 8080 포트를 막고 있으면 인바운드 허용 필요
3. **모바일 표시 팁**
   - 사이드바의 컴팩트 모드는 다중 컬럼을 1~2열로 줄여 줍니다
   - 표가 너무 넓으면 좌우 스크롤로 확인 (CSS 로 자동 처리)
   - 탭/버튼 터치 영역은 최소 42px 로 확대됨

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
