"""
eJARN 최신 기사 수집기 CLI.
사용법:
  python main.py [--max N] [--output path.json] [--no-verify]   # 파이프라인
  python main.py --agent [--max N] [--output path.json]          # LangChain 에이전트 (Tool 호출)
  python main.py --publication-jarn-regular [-o publication_jarn_regular.json]  # Publication > Jarn Regular February 5건
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import (
    EJARN_LIST_URL,
    EJARN_MAX_ARTICLES,
    EJARN_LOGIN_EMAIL,
    EJARN_LOGIN_PASSWORD,
)


MENU_URLS = {
    "1": ("Publication > Jarn Regular", "https://www.ejarn.com/series/index/1"),
    "2": ("Publication > Jarn Special", "https://www.ejarn.com/series/index/2"),
    "3": ("eJarn News", "https://www.ejarn.com/category/eJarn_news_index"),
    "4": ("Cover Story", "https://www.ejarn.com/category/cover_story_index"),
    "5": ("Event > Exhibition", "https://www.ejarn.com/category/exhibition_index"),
    "6": ("Report", "https://www.ejarn.com/category/report_index"),
    "7": ("Special Issue", "https://www.ejarn.com/category/special_issue_index"),
    "8": ("Regular Issue", "https://www.ejarn.com/category/regular_issue_index"),
}

OUTPUT_BASENAME_BY_URL = {
    "https://www.ejarn.com/series/index/1": "Jarn_Regular",
    "https://www.ejarn.com/series/index/2": "Jarn_Special",
    "https://www.ejarn.com/category/eJarn_news_index": "eJarn_News",
    "https://www.ejarn.com/category/cover_story_index": "Cover_Story",
    "https://www.ejarn.com/category/exhibition_index": "Event_Exhibition",
    "https://www.ejarn.com/category/report_index": "Report",
    "https://www.ejarn.com/category/special_issue_index": "Special_Issue",
    "https://www.ejarn.com/category/regular_issue_index": "Regular_Issue",
}

RESULT_DIR = Path(__file__).resolve().parent / "result"


def _default_output_path(list_url: str, publication_jarn_regular: bool = False) -> str:
    """출력 파일 기본명: <선택이름>_YYMM.json (예: eJarn_News_2603.json)."""
    yymm = datetime.now().strftime("%y%m")
    if publication_jarn_regular:
        base = "Jarn_Regular"
    else:
        base = OUTPUT_BASENAME_BY_URL.get(list_url.strip(), "eJarn_Result")
    return f"{base}_{yymm}.json"


def _resolve_output_path(output_name: str) -> Path:
    """모든 결과 파일을 프로젝트 내 result 폴더에 저장한다."""
    name = Path(output_name).name if output_name else "eJarn_Result.json"
    if not name.lower().endswith(".json"):
        name += ".json"
    return RESULT_DIR / name


def _select_list_url_interactive() -> str:
    """실행 시작 시 수집 대상 페이지를 사용자에게 선택받는다."""
    print("\n뉴스 정리하고 싶은 항목을 선택해주세요.")
    print("1. Publication > Jarn Regular")
    print("2. Publication > Jarn Special")
    print("3. eJarn News")
    print("4. Cover Story")
    print("5. Event > Exhibition")
    print("6. Report")
    print("7. Special Issue")
    print("8. Regular Issue")

    while True:
        choice = input("번호만 입력하세요 (1-8): ").strip()
        selected = MENU_URLS.get(choice)
        if selected:
            label, url = selected
            print(f"선택됨: {label} -> {url}")
            return url
        print("잘못된 입력입니다. 숫자 1~8 중 하나만 입력해주세요.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="eJARN 최신 기사 수집 후 Pydantic 구조로 정규화"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=EJARN_MAX_ARTICLES,
        help="수집 기사 수 상한 (기본: 설정값)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="",
        help="결과 저장 경로 (JSON). 비우면 선택 항목명_YYMM.json 자동 생성",
    )
    parser.add_argument("--no-verify", action="store_true", help="SSL 검증 비활성화")
    parser.add_argument(
        "--list-url",
        type=str,
        default="",
        help="목록 페이지 URL (지정 시 메뉴 선택 생략)",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="LangChain 에이전트로 실행 (System/Human/AI/Tool 흐름)",
    )
    parser.add_argument(
        "--publication-jarn-regular",
        action="store_true",
        help="Publication > Jarn Regular > February 섹션의 article-list.clm-feature 기사 5건 수집",
    )
    args = parser.parse_args()

    # main.py 실행 시 항상 HITL + env 로그인 정보 사용 강제
    email = (EJARN_LOGIN_EMAIL or "").strip()
    password = (EJARN_LOGIN_PASSWORD or "").strip()
    if args.agent:
        print(
            "수집 실패: --agent 모드는 HITL 로그인 강제 정책과 호환되지 않습니다. --agent 없이 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not email or not password:
        print(
            "수집 실패: .env의 EJARN_LOGIN_EMAIL / EJARN_LOGIN_PASSWORD가 필요합니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 실행 초기 메뉴 선택 (list-url를 직접 준 경우는 생략)
    selected_list_url = args.list_url.strip() if args.list_url else ""
    if not selected_list_url and not args.publication_jarn_regular:
        selected_list_url = _select_list_url_interactive()
    if not selected_list_url:
        selected_list_url = EJARN_LIST_URL

    try:
        if args.publication_jarn_regular:
            from src.pipeline import run_publication_jarn_regular

            collection = run_publication_jarn_regular(
                max_articles=5, require_hitl_login=True
            )
            output_path = args.output or _default_output_path(
                selected_list_url,
                publication_jarn_regular=True,
            )
        else:
            from src.pipeline import (
                run_pipeline,
                run_jarn_regular_balanced,
                run_jarn_special_balanced,
            )

            if selected_list_url == "https://www.ejarn.com/series/index/1":
                collection = run_jarn_regular_balanced(
                    max_topics=9,
                    require_hitl_login=True,
                )
            elif selected_list_url == "https://www.ejarn.com/series/index/2":
                collection = run_jarn_special_balanced(
                    max_topics=9,
                    require_hitl_login=True,
                )
            else:
                collection = run_pipeline(
                    list_url=selected_list_url,
                    max_articles=args.max,
                    verify_ssl=False if args.no_verify else None,
                    require_hitl_login=True,
                )
            output_path = args.output or _default_output_path(selected_list_url)
    except Exception as e:
        print(f"수집 실패: {e}", file=sys.stderr)
        sys.exit(1)

    # Pydantic 모델을 JSON 직렬화 (HttpUrl 등 처리)
    out = collection.model_dump(mode="json")

    if output_path:
        path = _resolve_output_path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"저장: {path} ({len(collection.items)}건)", file=sys.stderr)
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
