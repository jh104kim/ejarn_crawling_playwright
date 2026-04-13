"""
환경 변수 기반 설정. .env 로드 후 사용.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트 기준 .env 탐색
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _bool(s: str) -> bool:
    if not s:
        return False
    return s.strip().lower() in ("1", "true", "yes", "on")


# 수집 대상
EJARN_LIST_URL = os.getenv("EJARN_LIST_URL", "https://www.ejarn.com/category/eJarn_news")
EJARN_MAX_ARTICLES = int(os.getenv("EJARN_MAX_ARTICLES", "10"))
EJARN_REQUEST_TIMEOUT = int(os.getenv("EJARN_REQUEST_TIMEOUT", "15"))
EJARN_VERIFY_SSL = _bool(os.getenv("EJARN_VERIFY_SSL", "true"))

# Publication > Jarn Regular (series/index/1)
JARN_REGULAR_URL = os.getenv("JARN_REGULAR_URL", "https://www.ejarn.com/series/index/1")

# 구독(로그인) 시 본문 수집 — .env에 설정 시 로그인 후 기사 상세 요청
EJARN_LOGIN_EMAIL = os.getenv("EJARN_LOGIN_EMAIL", "")
EJARN_LOGIN_PASSWORD = os.getenv("EJARN_LOGIN_PASSWORD", "")

# 선택: Playwright (본문 JS 렌더링 시)
EJARN_USE_PLAYWRIGHT = _bool(os.getenv("EJARN_USE_PLAYWRIGHT", "true"))

# 선택: LLM
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EJARN_USE_LLM_SUMMARY = _bool(os.getenv("EJARN_USE_LLM_SUMMARY", "false"))
EJARN_USE_LLM_CLASSIFY = _bool(os.getenv("EJARN_USE_LLM_CLASSIFY", "false"))

# 일괄 수집(배치): 기준일 이후만 (YYYY-MM-DD 권장)
EJARN_SINCE_DATE = os.getenv("EJARN_SINCE_DATE", "").strip()
# result 하위 폴더 (예: 2604 → result/2604/)
EJARN_RESULT_SUBDIR = os.getenv("EJARN_RESULT_SUBDIR", "").strip()
# 목록에서 스크롤로 모을 최대 기사 링크 수 (섹션/토픽당 상한)
EJARN_MAX_LIST_ARTICLES = int(os.getenv("EJARN_MAX_LIST_ARTICLES", "400"))
# Jarn 시리즈: 인덱스에서 가져올 최대 토픽 수
EJARN_MAX_TOPICS = int(os.getenv("EJARN_MAX_TOPICS", "200"))
# 배치: 섹션당 최종 저장 기사 수 상한 (since 필터 통과 후)
EJARN_BATCH_SECTION_MAX = int(os.getenv("EJARN_BATCH_SECTION_MAX", "10"))

# HTTP 헤더
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
