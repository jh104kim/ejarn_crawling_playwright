"""
파이프라인: 목록 수집 -> 상세 수집 -> 요약/분류 -> ArticleCollection 생성.
구조상 AI가 Tool을 호출하는 흐름을 순차 실행으로 구현. 확장 시 LLM 에이전트로 교체 가능.
"""
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.schemas import ArticleCollection, ArticleItem
from src.config import (
    EJARN_LIST_URL,
    EJARN_MAX_ARTICLES,
    EJARN_LOGIN_EMAIL,
    EJARN_LOGIN_PASSWORD,
)
from src.tools.fetcher import (
    fetch_article_list,
    fetch_article_detail,
    fetch_articles_with_login,
    fetch_jarn_regular_february_articles,
    fetch_jarn_regular_topic_latest,
    fetch_jarn_special_topic_latest,
    execute_batch_fetch_on_logged_in_page,
    FetchedArticleRow,
    ListEntry,
    _apply_stealth,
    _login_with_playwright,
    _make_browser_context,
)
from src.tools.summarizer import summarize_text
from src.tools.classifier import (
    classify_application,
    classify_category,
    classify_company,
    classify_comp,
    classify_market_segment,
    classify_product_type,
    classify_refrigerant,
    classify_technology,
)


def _date_to_iso(date_str: str) -> str:
    """YYYY.MM.DD -> YYYY-MM-DD."""
    if not date_str:
        return ""
    s = date_str.strip().replace(".", "-")
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    return date_str


def run_pipeline(
    list_url: str = EJARN_LIST_URL,
    max_articles: int = EJARN_MAX_ARTICLES,
    source_label: str = "eJARN",
    verify_ssl: Optional[bool] = None,
    require_hitl_login: bool = False,
) -> ArticleCollection:
    """
    eJARN 최신 기사를 수집해 ArticleCollection으로 반환한다.

    Parameters
    ----------
    list_url : str
        기사 목록 URL.
    max_articles : int
        수집할 기사 수 상한.
    source_label : str
        source 필드 값.
    verify_ssl : bool, optional
        None이면 설정값 사용.

    Returns
    -------
    ArticleCollection
        source, collected_at, items.
    """
    if verify_ssl is not None:
        import src.config as cfg
        cfg.EJARN_VERIFY_SSL = verify_ssl

    email = (EJARN_LOGIN_EMAIL or "").strip()
    password = (EJARN_LOGIN_PASSWORD or "").strip()
    if require_hitl_login and (not email or not password):
        raise ValueError("HITL 로그인 강제 모드입니다. .env의 EJARN_LOGIN_EMAIL / EJARN_LOGIN_PASSWORD를 설정하세요.")

    collected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    items: list[ArticleItem] = []

    # 로그인 자격증명이 있으면 Playwright + HITL 세션으로 수집
    use_login = bool(email and password)

    if use_login:
        import sys
        print("[pipeline] 로그인 모드로 수집 시작 (Playwright)...", file=sys.stderr)
        entries, details_list = fetch_articles_with_login(
            list_url=list_url,
            max_items=max_articles,
            login_email=email,
            login_password=password,
            enable_hitl=True,
        )
        pairs = list(zip(entries, details_list))
    else:
        entries = fetch_article_list(list_url=list_url, max_items=max_articles)
        pairs = [(e, None) for e in entries]

    for entry, pre_detail in pairs:
        try:
            if pre_detail is not None:
                detail = pre_detail
            else:
                detail = fetch_article_detail(entry.link)

            topic = detail.topic or entry.title
            date_iso = _date_to_iso(detail.date_str or entry.date_str)
            body = detail.body

            # Tool: 요약 (본문이 없으면 제목으로 대체 — JS 렌더링 페이지 대응)
            summary = summarize_text(body) if body else topic[:500]

            # Tool: 분류
            company = classify_company(topic, body)
            related_comp = classify_comp(topic, body)
            product_type = classify_product_type(topic, body)
            market_segment = classify_market_segment(topic, body)
            refrigerant = classify_refrigerant(topic, body)
            application = classify_application(topic, body)
            technology = classify_technology(topic, body)
            category = classify_category(topic, body)

            item = ArticleItem(
                date=date_iso or collected_at[:10],
                topic=topic,
                summary=summary,
                link=entry.link,
                company=company,
                related_comp=related_comp,
                product_type=product_type,
                market_segment=market_segment,
                refrigerant=refrigerant,
                application=application,
                technology=technology,
                category=category,
            )
            items.append(item)
        except Exception as e:
            import warnings
            warnings.warn(f"Skip article {entry.link}: {e}", UserWarning)
            continue

    return ArticleCollection(source=source_label, collected_at=collected_at, items=items)


def run_publication_jarn_regular(
    max_articles: int = 5,
    source_label: str = "eJARN (Publication Jarn Regular)",
    login_email: str = "",
    login_password: str = "",
    require_hitl_login: bool = False,
) -> ArticleCollection:
    """
    Publication > Jarn Regular 페이지에서 February 섹션의
    div.article-list.clm-feature 기사 max_articles건을 수집해
    기존과 동일한 ArticleCollection 스키마로 반환한다.
    구독 본문 수집 시 login_email/login_password를 사용한다.
    """
    collected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    items: list[ArticleItem] = []

    email = login_email or EJARN_LOGIN_EMAIL
    password = login_password or EJARN_LOGIN_PASSWORD
    if require_hitl_login and (not (email or "").strip() or not (password or "").strip()):
        raise ValueError("HITL 로그인 강제 모드입니다. .env의 EJARN_LOGIN_EMAIL / EJARN_LOGIN_PASSWORD를 설정하세요.")
    entries, details_list = fetch_jarn_regular_february_articles(
        max_articles=max_articles,
        login_email=email,
        login_password=password,
        enable_hitl=True,
    )

    for entry, detail in zip(entries, details_list):
        try:
            topic = detail.topic or entry.title
            date_iso = _date_to_iso(detail.date_str or entry.date_str)
            body = detail.body

            summary = summarize_text(body) if body else topic[:500]
            company = classify_company(topic, body)
            related_comp = classify_comp(topic, body)
            product_type = classify_product_type(topic, body)
            market_segment = classify_market_segment(topic, body)
            refrigerant = classify_refrigerant(topic, body)
            application = classify_application(topic, body)
            technology = classify_technology(topic, body)
            category = classify_category(topic, body)

            item = ArticleItem(
                date=date_iso or collected_at[:10],
                topic=topic,
                summary=summary,
                link=entry.link,
                company=company,
                related_comp=related_comp,
                product_type=product_type,
                market_segment=market_segment,
                refrigerant=refrigerant,
                application=application,
                technology=technology,
                category=category,
            )
            items.append(item)
        except Exception as e:
            import warnings
            warnings.warn(f"Skip article {entry.link}: {e}", UserWarning)
            continue

    return ArticleCollection(source=source_label, collected_at=collected_at, items=items)


def run_jarn_special_balanced(
    max_topics: int = 9,
    source_label: str = "eJARN (Publication Jarn Special)",
    login_email: str = "",
    login_password: str = "",
    require_hitl_login: bool = False,
) -> ArticleCollection:
    """
    Jarn Special(index/2) 처리 전용:
    - 토픽 링크 최대 max_topics개 수집
    - 토픽별 최신 기사 1건만 상세 파싱
    - 나머지 기사 제목은 related_titles에 보관
    - URL 기준 dedupe
    """
    collected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    items: list[ArticleItem] = []

    email = login_email or EJARN_LOGIN_EMAIL
    password = login_password or EJARN_LOGIN_PASSWORD
    if require_hitl_login and (not (email or "").strip() or not (password or "").strip()):
        raise ValueError("HITL 로그인 강제 모드입니다. .env의 EJARN_LOGIN_EMAIL / EJARN_LOGIN_PASSWORD를 설정하세요.")

    bundles = fetch_jarn_special_topic_latest(
        max_topics=max_topics,
        login_email=email,
        login_password=password,
        enable_hitl=True,
    )

    for bundle in bundles:
        try:
            if not bundle.latest_entry or not bundle.latest_detail:
                continue

            topic = bundle.latest_detail.topic or bundle.latest_entry.title
            date_iso = _date_to_iso(bundle.latest_detail.date_str or bundle.latest_entry.date_str)
            body = bundle.latest_detail.body

            summary = summarize_text(body) if body else topic[:500]
            company = classify_company(topic, body)
            related_comp = classify_comp(topic, body)
            product_type = classify_product_type(topic, body)
            market_segment = classify_market_segment(topic, body)
            refrigerant = classify_refrigerant(topic, body)
            application = classify_application(topic, body)
            technology = classify_technology(topic, body)
            category = classify_category(topic, body)

            item = ArticleItem(
                date=date_iso or collected_at[:10],
                topic=topic,
                summary=summary,
                link=bundle.latest_entry.link,
                source_topic=bundle.topic_name,
                source_topic_url=bundle.topic_url,
                related_titles=bundle.other_titles,
                company=company,
                related_comp=related_comp,
                product_type=product_type,
                market_segment=market_segment,
                refrigerant=refrigerant,
                application=application,
                technology=technology,
                category=category,
            )
            items.append(item)
        except Exception as e:
            import warnings
            warnings.warn(f"Skip special topic {bundle.topic_name}: {e}", UserWarning)
            continue

    return ArticleCollection(source=source_label, collected_at=collected_at, items=items)


def run_jarn_regular_balanced(
    max_topics: int = 9,
    source_label: str = "eJARN (Publication Jarn Regular Balanced)",
    login_email: str = "",
    login_password: str = "",
    require_hitl_login: bool = False,
) -> ArticleCollection:
    """
    Jarn Regular(index/1) 처리 전용:
    - 토픽 링크 최대 max_topics개 수집
    - 토픽별 최신 기사 1건만 상세 파싱
    - 나머지 기사 제목은 related_titles에 보관
    - URL 기준 dedupe
    """
    collected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    items: list[ArticleItem] = []

    email = login_email or EJARN_LOGIN_EMAIL
    password = login_password or EJARN_LOGIN_PASSWORD
    if require_hitl_login and (not (email or "").strip() or not (password or "").strip()):
        raise ValueError("HITL 로그인 강제 모드입니다. .env의 EJARN_LOGIN_EMAIL / EJARN_LOGIN_PASSWORD를 설정하세요.")

    bundles = fetch_jarn_regular_topic_latest(
        max_topics=max_topics,
        login_email=email,
        login_password=password,
        enable_hitl=True,
    )

    for bundle in bundles:
        try:
            if not bundle.latest_entry or not bundle.latest_detail:
                continue

            topic = bundle.latest_detail.topic or bundle.latest_entry.title
            date_iso = _date_to_iso(bundle.latest_detail.date_str or bundle.latest_entry.date_str)
            body = bundle.latest_detail.body

            summary = summarize_text(body) if body else topic[:500]
            company = classify_company(topic, body)
            related_comp = classify_comp(topic, body)
            product_type = classify_product_type(topic, body)
            market_segment = classify_market_segment(topic, body)
            refrigerant = classify_refrigerant(topic, body)
            application = classify_application(topic, body)
            technology = classify_technology(topic, body)
            category = classify_category(topic, body)

            item = ArticleItem(
                date=date_iso or collected_at[:10],
                topic=topic,
                summary=summary,
                link=bundle.latest_entry.link,
                source_topic=bundle.topic_name,
                source_topic_url=bundle.topic_url,
                related_titles=bundle.other_titles,
                company=company,
                related_comp=related_comp,
                product_type=product_type,
                market_segment=market_segment,
                refrigerant=refrigerant,
                application=application,
                technology=technology,
                category=category,
            )
            items.append(item)
        except Exception as e:
            import warnings
            warnings.warn(f"Skip regular topic {bundle.topic_name}: {e}", UserWarning)
            continue

    return ArticleCollection(source=source_label, collected_at=collected_at, items=items)


def build_collection_from_fetched_rows(
    rows: List[FetchedArticleRow],
    source_label: str,
) -> ArticleCollection:
    """배치 수집 행(FetchedArticleRow)을 ArticleCollection으로 변환."""
    collected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    items: list[ArticleItem] = []
    for row in rows:
        try:
            entry = row.entry
            detail = row.detail
            topic = detail.topic or entry.title
            date_iso = _date_to_iso(detail.date_str or entry.date_str)
            body = detail.body
            summary = summarize_text(body) if body else topic[:500]
            company = classify_company(topic, body)
            related_comp = classify_comp(topic, body)
            product_type = classify_product_type(topic, body)
            market_segment = classify_market_segment(topic, body)
            refrigerant = classify_refrigerant(topic, body)
            application = classify_application(topic, body)
            technology = classify_technology(topic, body)
            category = classify_category(topic, body)
            item = ArticleItem(
                date=date_iso or collected_at[:10],
                topic=topic,
                summary=summary,
                link=entry.link,
                source_topic=row.source_topic or "",
                source_topic_url=row.source_topic_url or "",
                related_titles=list(row.related_titles or []),
                company=company,
                related_comp=related_comp,
                product_type=product_type,
                market_segment=market_segment,
                refrigerant=refrigerant,
                application=application,
                technology=technology,
                category=category,
            )
            items.append(item)
        except Exception as e:
            import warnings

            warnings.warn(f"Skip row {row.entry.link}: {e}", UserWarning)
    return ArticleCollection(source=source_label, collected_at=collected_at, items=items)


def run_batch_pipeline_since_login(
    specs: List[Tuple[str, str, str]],
    since: date,
    max_list_articles: int,
    max_topics: int,
    max_section_articles: int,
    login_email: str,
    login_password: str,
) -> Dict[str, ArticleCollection]:
    """
    Playwright 1회(HITL 로그인) 후 specs 순서대로 섹션 수집.

    specs: (list_url, mode, basename), mode는 'jarn_series' | 'category'
    max_section_articles: 섹션당 since 이후 최대 저장 건수.
    """
    import sys
    from playwright.sync_api import sync_playwright

    email = (login_email or "").strip()
    password = (login_password or "").strip()
    if not email or not password:
        raise ValueError("배치 수집에는 .env의 EJARN_LOGIN_EMAIL / EJARN_LOGIN_PASSWORD가 필요합니다.")

    raw: Dict[str, List[FetchedArticleRow]] = {}
    with sync_playwright() as p:
        browser, context = _make_browser_context(
            p,
            headless=False,
            use_chrome_channel=True,
        )
        try:
            page = context.new_page()
            _apply_stealth(page)
            print("[batch] Chrome에서 HITL 로그인을 완료한 뒤 진행합니다.", file=sys.stderr)
            _login_with_playwright(page, email, password, enable_hitl=True)
            raw = execute_batch_fetch_on_logged_in_page(
                page,
                list(specs),
                since,
                max_list_articles,
                max_topics,
                max_section_articles,
            )
        finally:
            try:
                browser.close()
            except Exception:
                pass

    out: Dict[str, ArticleCollection] = {}
    for basename, rows in raw.items():
        out[basename] = build_collection_from_fetched_rows(rows, f"eJARN ({basename})")
    return out
