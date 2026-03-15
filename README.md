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
- 수집 기록은 `.ejarn_history.json`으로 저장되며, 앱 재시작 후에도 프로젝트 폴더의 기존 JSON 결과를 자동 스캔해 히스토리에 표시합니다.

## 요구사항

- Python 3.10+
- Playwright 설치 및 브라우저 설치

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## 환경 변수 (.env)

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

## 참고

- `main.py`는 운영 기준으로 HITL 로그인 강제 정책을 사용합니다.
- 따라서 비로그인/비대화형 자동 실행을 원하면 별도 실행 스크립트에서 `run_pipeline`을 직접 호출하도록 분리하는 방식을 권장합니다.
