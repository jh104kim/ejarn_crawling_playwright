# eJARN 기사 수집·정규화 프로젝트 (최종 운영 기준)

eJARN 기사 수집 후, 고정 JSON 스키마로 정규화하여 출력하는 Python 프로젝트입니다.

## 핵심 동작

- `main.py` 실행 시 **HITL 로그인(Chrome 창)**을 기본/강제로 사용합니다.
- 로그인 정보는 `.env`의 `EJARN_LOGIN_EMAIL`, `EJARN_LOGIN_PASSWORD`를 사용합니다.
- 사용자가 Chrome에서 hCaptcha/로그인을 완료한 뒤 터미널에 `완료`를 입력하면 수집이 진행됩니다.
- 최종 결과는 `ArticleCollection` → `items[ArticleItem]` JSON으로 저장/출력됩니다.

### Streamlit 실행 시(HITL)

- Streamlit에서는 수집이 **백그라운드 프로세스**에서 실행됩니다.
- 로그인 대기 중 현재 상태(URL/판정값/대기 시간)를 UI에 표시합니다.
- 사용자가 Chrome에서 캡차/로그인을 완료한 뒤, Streamlit의 `✅ 로그인 완료(진행)` 버튼을 누르면 다음 단계로 진행합니다.
- 수집 기록은 `.ejarn_history.json`으로 저장되며, 앱 재시작 후에도 `result/` 폴더의 JSON 결과를 자동 스캔해 히스토리에 표시합니다.
- 수집 히스토리 라벨은 JSON의 주제명이 아니라 **파일명**으로 표시됩니다.

### 결과 파일 저장 위치

- CLI(`main.py`)와 Streamlit(`streamlit_app.py`) 모두 결과 JSON을 프로젝트 내 `result/` 폴더에 저장합니다.
- 기본 파일명 규칙: `선택항목명_YYMM.json`
  - 예: `eJarn_News_2603.json`, `Event_Exhibition_2603.json`

## 요구사항

- Python 3.10+ (권장: 3.12)
- Playwright 설치 및 브라우저 설치 (또는 로컬 Chrome 사용)

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

> 네트워크 정책 등으로 `playwright install chromium` 다운로드가 실패할 수 있습니다.  
> 이 경우에도 로컬 PC에 Chrome이 설치되어 있으면, 본 프로젝트는 Playwright의 `channel="chrome"`로 실행되어 **ChromeDriver 없이** 동작합니다.

## 환경 변수 (.env)

프로젝트 시작 시 `.env.sample`을 복사해 `.env`를 만든 뒤 실제 값을 입력하세요.

```bash
copy .env.sample .env
```

필수:

```dotenv
EJARN_LOGIN_EMAIL=your@email.com
EJARN_LOGIN_PASSWORD=your_password
```

선택:

```dotenv
OPENAI_API_KEY=...
EJARN_USE_LLM_SUMMARY=true
EJARN_USE_LLM_CLASSIFY=true
EJARN_MAX_ARTICLES=10
EJARN_LIST_URL=https://www.ejarn.com/series/list/February/2026
EJARN_SINCE_DATE=2026-03-15
EJARN_RESULT_SUBDIR=2604
EJARN_MAX_LIST_ARTICLES=400
EJARN_MAX_TOPICS=200
EJARN_BATCH_SECTION_MAX=10
```

## 실행 방법

```bash
cd ejarn_collector

# 기본 실행 (HITL 로그인 강제, 기본 max 사용)
python main.py

# 2건 수집하여 파일 저장
python main.py --max 2 -o result_2.json

# 3건 수집하여 파일 저장
python main.py --max 3 -o out_3_hitl.json

# Publication Jarn Regular 모드
python main.py --publication-jarn-regular -o publication_jarn_regular.json

# Streamlit 앱 실행
streamlit run streamlit_app.py
```

### 전 섹션 일괄 수집(기준일 이후, 섹션당 N건)

HITL(사람) 로그인 1회 후 아래 8개 섹션을 순회 수집하고 `result/<subdir>/`에 저장합니다.

- Publication > Jarn Regular
- Publication > Jarn Special
- eJarn News
- Cover Story
- Event > Exhibition
- Report
- Special Issue
- Regular Issue

예시:

```bash
python main.py --batch-all-sections --since 2026-03-15 --result-subdir 2604 --batch-section-max 10
```

동작:

- `--since`: 게시일이 해당 날짜 이상(\(\ge\))인 기사만 포함
- `--batch-section-max`: 섹션당 최대 저장 건수 (기본 10)
- 결과 파일: `result/2604/<섹션명>_2604.json`

### GitHub의 index.html로 시작하는 운영 방식

프로젝트 루트의 `index.html`은 **GitHub에서 먼저 열어보고**, 그 다음 로컬 PC의 Streamlit으로 이동하는 시작 페이지로 사용할 수 있습니다.

권장 흐름:

1. GitHub Pages 또는 GitHub 저장소의 `index.html` 확인
2. PC에서 아래 명령으로 Streamlit 실행

```bash
streamlit run streamlit_app.py
```

3. `index.html`의 **로컬 Streamlit 열기** 버튼 클릭
4. 브라우저에서 `http://127.0.0.1:8501` 새 탭으로 이동

중요:

- GitHub의 `index.html`은 Python(`streamlit_app.py`)을 **직접 실행할 수 없습니다**.
- 브라우저 보안 정책상 GitHub(HTTPS) 페이지에서 로컬 Streamlit(HTTP)을 iframe/fetch로 직접 붙이는 방식은 제한될 수 있습니다.
- 따라서 현재는 **GitHub의 index.html = 실행 안내/런처**, **로컬 PC = Streamlit 실제 실행 주체**로 두는 것이 가장 안정적입니다.

### 기존 코드 수정이 필요한가?

- **핵심 수집 로직(`main.py`, `streamlit_app.py`) 수정은 필수 아님**
- 이번 목적을 위해 필요한 것은 `index.html`의 역할을 “임베드 페이지”가 아니라 “로컬 앱 실행 안내/열기 페이지”로 두는 것입니다.
- 즉, 기존 Python 기능은 그대로 유지하고 웹 진입점만 바꾸는 방식으로 운영 가능합니다.

실행 중 터미널 안내:

```text
[HITL] Chrome 창에서 hCaptcha를 해결하고 로그인 완료 후, 터미널에 '완료'를 입력하세요.
```

## 출력 JSON 스키마 (최종)

각 기사(`items[]`)는 아래 구조를 따릅니다.

```json
{
  "date": "",
  "topic": "",
  "summary": "",
  "link": "",
  "company": [],
  "related_comp": [],
  "product_type": [],
  "market_segment": [],
  "refrigerant": [],
  "application": [],
  "technology": [],
  "category": []
}
```

### 허용 값

- `related_comp`
  - `Recipro`, `Rotary`, `Scroll`

- `product_type`
  - `Compressor`, `HVAC`, `Refrigeration`, `Component`, `Solution`

- `market_segment`
  - `Residential`, `Commercial`, `Industrial`, `Infrastructure`

- `refrigerant`
  - `HFC/HFO`, `Natural`, `Low-GWP`, `Unknown`

- `application`
  - `Cooling`, `Heating`, `Refrigeration`, `Heat Recovery`, `Multi-purpose`

- `technology`
  - `Efficiency`, `Control/AI`, `Sustainability`, `Compact/Design`, `Manufacturing`

- `category`
  - `Product`, `Technology`, `Business`, `Manufacturing`, `Market`

## 데이터 품질 규칙

- `summary`는 최대 900자
- 분류 리스트는 중복 제거
- `refrigerant` 미식별 시 `Unknown`
- `application` 미식별 시 `Multi-purpose`
- `category` 미식별 시 `Market`

## 코드 위치

- 엔트리: `main.py`
- 파이프라인: `src/pipeline.py`
- 스키마: `src/schemas.py`
- 분류기: `src/tools/classifier.py`
- 수집기/HITL 로그인: `src/tools/fetcher.py`
- Streamlit UI: `streamlit_app.py`
- 프롬프트: `src/prompts.py`, `src/agent_prompts.py`

## 최근 업데이트 (2026-03-15)

- `page.content ... navigating` 오류 대응: 안전 재시도 래퍼 도입
- 요약 언어를 한국어로 고정
- 요약 길이 제한을 900자로 상향
- Streamlit에 수집 히스토리 저장/조회 추가
- 앱 시작 시 프로젝트 폴더 JSON 자동 스캔 후 히스토리 병합
- HITL 로그인 상태(UI) 실시간 표시 추가 (stage/url/판정)
- Streamlit에서 `로그인 완료(진행)` 버튼 신호 기반으로 다음 단계 진행

## 최근 업데이트 (2026-03-16)

- 모든 결과 JSON 저장 위치를 `result/` 폴더로 통일
- Streamlit 히스토리 스캔 경로를 `result/`로 변경
- Streamlit 히스토리 표시명을 JSON 파일명 기준으로 변경
- `index.html`을 GitHub에서 확인 후 로컬 Streamlit으로 이동하는 런처 페이지로 변경

## 참고

- `main.py`는 운영 기준으로 HITL 로그인 강제 정책을 사용합니다.
- 따라서 비로그인/비대화형 자동 실행을 원하면 별도 실행 스크립트에서 `run_pipeline`을 직접 호출하도록 분리하는 방식을 권장합니다.
- 본 프로젝트는 Selenium 기반이 아니며 **ChromeDriver가 필요하지 않습니다**.
