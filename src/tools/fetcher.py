"""
Tool: eJARN 기사 목록·상세 페이지 수집 및 파싱.
본문이 비어 있을 때 Playwright로 JS 렌더링 후 재추출.
CAPTCHA 감지 + 로그인 세션 유지 기능 포함.
"""
import re
import time
import random
import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from readability import Document as ReadabilityDocument

from src import config as _config


# ---------------------------------------------------------------------------
# Playwright 헬퍼
# ---------------------------------------------------------------------------

def _random_delay(min_ms: int = 500, max_ms: int = 1500) -> None:
    """봇 탐지 회피용 랜덤 딜레이."""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def _safe_page_content(page, retries: int = 6, delay_sec: float = 0.4) -> str:
    """페이지 이동 중(content 갱신 중) 예외를 재시도로 완화한다."""
    last_error = None
    for _ in range(max(1, retries)):
        try:
            return page.content()
        except Exception as e:
            last_error = e
            # 페이지 전환/렌더링 도중 content 호출 시 발생하는 일시 오류를 대기 후 재시도
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            time.sleep(delay_sec)
    raise RuntimeError(f"page.content() 재시도 실패: {last_error}")


def _is_captcha_page(html: str) -> bool:
    """reCAPTCHA / hCaptcha / Cloudflare Challenge 감지 (false positive 최소화)."""
    lower = html.lower()
    # 정확한 Cloudflare/CAPTCHA 마커만 사용
    definite_markers = (
        "g-recaptcha",
        "hcaptcha",
        "cf-challenge-form",
        "cf_clearance",
        "checking your browser",  # Cloudflare 특유 문구
        "are you a human",
        "verify you are human",
        "i am not a robot",       # reCAPTCHA 체크박스 문구
        "ddos-guard",
        "challenge-platform",
    )
    # "just a moment" + body 콘텐츠가 매우 짧으면 Cloudflare 챌린지로 판단
    if "just a moment" in lower and len(html) < 10000:
        return True
    return any(marker in lower for marker in definite_markers)


def _apply_stealth(page) -> None:
    """Playwright 페이지에 기본 stealth JS 패치 적용."""
    # webdriver 흔적 숨김
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = { runtime: {} };
    """)


def _make_browser_context(playwright_instance, headless: bool = True, use_chrome_channel: bool = False):
    """공통 브라우저 컨텍스트 생성 (스텔스 설정 포함)."""
    launch_args = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    }
    if use_chrome_channel:
        try:
            browser = playwright_instance.chromium.launch(channel="chrome", **launch_args)
        except Exception:
            browser = playwright_instance.chromium.launch(**launch_args)
    else:
        browser = playwright_instance.chromium.launch(**launch_args)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
        ignore_https_errors=not _config.EJARN_VERIFY_SSL,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    # context 레벨 stealth (모든 페이지에 자동 적용)
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = { runtime: {} };
    """)
    return browser, context


def _get_login_state(page) -> dict:
    """로그인 판정을 위한 URL/DOM/쿠키 상태를 수집한다."""
    url = page.url or ""
    lower_url = url.lower()
    on_login_url = "/auth/login" in lower_url or "login" in lower_url

    has_password_field = bool(page.query_selector("input[name='password'], input[type='password']"))
    has_logout_link = (
        bool(page.query_selector("a[href*='logout']"))
        or bool(page.query_selector("a[href*='/auth/logout']"))
    )
    has_user_menu = bool(
        page.query_selector(
            "a[href*='/mypage'], a[href*='/my'], .user-menu, .my-page, .profile, .account"
        )
    )

    has_auth_cookie = False
    try:
        cookies = page.context.cookies()
        cookie_names = [str(c.get("name", "")).lower() for c in cookies]
        has_auth_cookie = any(
            ("session" in name)
            or ("remember" in name)
            or (name in {"laravel_session", "php_session", "connect.sid"})
            for name in cookie_names
        )
    except Exception:
        pass

    has_captcha_marker = False
    try:
        state_html = _safe_page_content(page, retries=2, delay_sec=0.2)
        has_captcha_marker = _is_captcha_page(state_html)
    except Exception:
        has_captcha_marker = False

    # 로그인 성공 판정은 "강한 신호"가 있어야만 True
    # - captcha/challenge 마커가 있으면 무조건 미로그인
    # - 비로그인 URL + (logout 링크 또는 user menu) 우선
    # - 쿠키만 있는 경우는 오탐 방지를 위해 password 필드가 없어야 인정
    strong_signal = has_logout_link or has_user_menu
    cookie_signal = has_auth_cookie and (not has_password_field)
    is_logged = (not has_captcha_marker) and (not on_login_url) and (strong_signal or cookie_signal)

    return {
        "url": url,
        "on_login_url": on_login_url,
        "has_password_field": has_password_field,
        "has_logout_link": has_logout_link,
        "has_user_menu": has_user_menu,
        "has_auth_cookie": has_auth_cookie,
        "has_captcha_marker": has_captcha_marker,
        "is_logged_in": is_logged,
    }


def _emit_hitl_status(page, stage: str, message: str = "", waited_sec: int = 0) -> None:
    """Streamlit에서 읽을 수 있도록 HITL 상태를 JSON 파일에 기록한다."""
    status_path = (os.getenv("EJARN_HITL_STATUS_FILE", "") or "").strip()
    if not status_path:
        return
    try:
        state = _get_login_state(page)
        payload = {
            "stage": stage,
            "message": message,
            "waited_sec": int(waited_sec),
            "ts": time.time(),
            **state,
        }
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _is_logged_in(page) -> bool:
    """로그인 성공 여부를 URL/DOM/쿠키를 종합해 판정."""
    return bool(_get_login_state(page).get("is_logged_in"))


def _hitl_login_chrome(page, email: str, password: str) -> bool:
    """
    HITL 로그인:
    1) Chrome 창을 띄운 상태에서 사용자에게 hCaptcha 해결 요청
    2) 터미널에 '완료' 입력 시 로그인 상태 확인 후 진행
    """
    import sys
    import warnings

    try:
        page.goto("https://www.ejarn.com/auth/login", wait_until="domcontentloaded", timeout=30000)
        _random_delay(800, 1500)
        _emit_hitl_status(page, "login_page_opened", "로그인 페이지가 열렸습니다.", 0)

        # 입력 필드 자동 채움 (없어도 사용자가 수동 입력 가능)
        try:
            email_sel = (
                "input[type='email']"
                if page.query_selector("input[type='email']")
                else "input[name='email'], input[id='email']"
            )
            page.fill(email_sel, email)
        except Exception:
            pass
        try:
            page.fill("input[type='password'], input[name='password']", password)
        except Exception:
            pass

        print(
            "[HITL] Chrome 창에서 hCaptcha를 해결하고 로그인 완료 후, 터미널에 '완료'를 입력하세요.",
            file=sys.stderr,
        )

        def _proceed_after_ack(reason: str) -> bool:
            """'완료' 신호를 받으면 즉시 다음 단계로 진행한다."""
            try:
                if page.query_selector("input[name='password']"):
                    page.click("button[type='submit'], input[type='submit'], form button")
                    page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass

            waited = 0
            if _is_logged_in(page):
                _emit_hitl_status(page, "login_success", f"{reason} 후 로그인 성공 확인", waited)
            else:
                _emit_hitl_status(
                    page,
                    "login_unverified_proceed",
                    f"{reason} 신호에 따라 로그인 성공 미확인 상태지만 다음 단계로 진행합니다.",
                    waited,
                )
            print(f"[HITL] {reason}: 다음 단계로 진행합니다.", file=sys.stderr)
            return True

        def _wait_login_non_interactive(timeout_sec: int = 600) -> bool:
            print(
                f"[HITL] 비대화형 환경 감지: 로그인 완료까지 최대 {timeout_sec}초 대기합니다.",
                file=sys.stderr,
            )
            confirm_path = (os.getenv("EJARN_HITL_CONFIRM_FILE", "") or "").strip()
            require_confirm = (os.getenv("EJARN_HITL_REQUIRE_CONFIRM", "") or "").strip().lower() in (
                "1", "true", "yes", "on"
            )
            deadline = time.time() + timeout_sec
            last_submit_try = 0.0
            start_ts = time.time()
            last_emit = 0.0
            while time.time() < deadline:
                confirmed = bool(confirm_path and os.path.exists(confirm_path))

                # Streamlit 완료 버튼을 누르면 다음 단계로 진행(요청한 UX)
                if require_confirm and confirmed:
                    try:
                        if page.query_selector("input[name='password']"):
                            page.click("button[type='submit'], input[type='submit'], form button")
                            page.wait_for_load_state("domcontentloaded", timeout=4000)
                    except Exception:
                        pass

                    waited = int(time.time() - start_ts)
                    if _is_logged_in(page):
                        _emit_hitl_status(
                            page,
                            "login_success",
                            "완료 버튼 확인 후 로그인 성공이 확인되었습니다.",
                            waited,
                        )
                    else:
                        _emit_hitl_status(
                            page,
                            "login_unverified_proceed",
                            "완료 버튼이 눌려 로그인 성공 미확인 상태지만 다음 단계로 진행합니다.",
                            waited,
                        )
                    print("[HITL] 완료 버튼 확인: 다음 단계로 진행합니다.", file=sys.stderr)
                    return True

                if _is_logged_in(page):
                    if require_confirm and not confirmed:
                        now = time.time()
                        if now - last_emit >= 3:
                            last_emit = now
                            waited = int(now - start_ts)
                            _emit_hitl_status(
                                page,
                                "waiting_confirm",
                                "로그인 감지됨. Streamlit에서 '로그인 완료(진행)' 버튼을 누르세요.",
                                waited,
                            )
                        time.sleep(1)
                        continue

                    waited = int(time.time() - start_ts)
                    _emit_hitl_status(page, "login_success", "로그인 성공이 확인되었습니다.", waited)
                    print(f"[HITL] 로그인 성공 (URL: {page.url})", file=sys.stderr)
                    return True

                # 사용자가 캡차를 푼 뒤 제출만 남았을 수 있어 주기적으로 submit 재시도
                now = time.time()
                if now - last_submit_try >= 5:
                    last_submit_try = now
                    try:
                        if page.query_selector("input[name='password']"):
                            page.click("button[type='submit'], input[type='submit'], form button")
                            page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:
                        pass

                if now - last_emit >= 6:
                    last_emit = now
                    waited = int(now - start_ts)
                    _emit_hitl_status(
                        page,
                        "waiting_login",
                        (
                            "hCaptcha/로그인 완료를 기다리는 중입니다."
                            if not require_confirm or not confirmed
                            else "완료 버튼 확인됨. 로그인 성공 상태를 확인 중입니다."
                        ),
                        waited,
                    )

                time.sleep(2)

            waited = int(time.time() - start_ts)
            _emit_hitl_status(
                page,
                "timeout",
                "대기 시간 초과: 로그인 미완료",
                waited,
            )
            raise RuntimeError(
                f"HITL 로그인 대기 시간({timeout_sec}초) 초과: hCaptcha/로그인이 완료되지 않아 수집을 중단합니다."
            )

        force_non_interactive = (os.getenv("EJARN_HITL_NON_INTERACTIVE", "") or "").strip().lower() in (
            "1", "true", "yes", "on"
        )

        if force_non_interactive or (not sys.stdin or not sys.stdin.isatty()):
            # PowerShell 파이프 입력 예: "완료" | python main.py ...
            # 비대화형이지만 표준입력으로 신호가 들어오면 즉시 진행한다.
            if not force_non_interactive:
                try:
                    _emit_hitl_status(page, "await_user_input", "표준입력에서 '완료' 신호 대기 중", 0)
                    piped_ack = input("[HITL] 로그인 완료 시 '완료' 입력: ").strip()
                    if piped_ack == "완료":
                        return _proceed_after_ack("표준입력 완료")
                except EOFError:
                    pass
            return _wait_login_non_interactive(600)

        try:
            _emit_hitl_status(page, "await_user_input", "터미널에서 '완료' 입력 대기 중", 0)
            user_ack = input("[HITL] 로그인 완료 시 '완료' 입력: ").strip()
        except EOFError:
            # 일부 환경(Streamlit worker 등)에서 isatty=True 여도 input()이 EOF를 던질 수 있음
            warnings.warn("HITL 입력 스트림 EOF 감지: 비대화형 로그인 대기로 전환합니다.", UserWarning)
            return _wait_login_non_interactive(600)

        if user_ack != "완료":
            warnings.warn("HITL 완료 입력이 없어 비로그인 모드로 계속합니다.", UserWarning)
            return False

        return _proceed_after_ack("터미널 완료 입력")
    except Exception as e:
        _emit_hitl_status(page, "login_error", f"로그인 오류: {e}", 0)
        warnings.warn(f"HITL 로그인 실패: {e}", UserWarning)
        return False


def _login_with_playwright(page, email: str, password: str, enable_hitl: bool = False) -> bool:
    """
    eJARN 로그인 시도. 성공 여부 반환.
    CAPTCHA 감지 시 경고 로그 출력 후 False 반환.
    """
    import warnings
    try:
        if enable_hitl:
            logged_in = _hitl_login_chrome(page, email, password)
            if not logged_in:
                raise RuntimeError("HITL 로그인 실패/미확인으로 수집을 중단합니다.")
            return True

        # stealth 는 context 레벨에서 이미 적용됨
        page.goto("https://www.ejarn.com/auth/login", wait_until="domcontentloaded", timeout=25000)
        _random_delay(1500, 2500)

        # Cloudflare JS 챌린지 감지 (body가 매우 짧고 "just a moment" 가 있을 때만)
        html_before = _safe_page_content(page)
        if "just a moment" in html_before.lower() and len(html_before) < 10000:
            _random_delay(4000, 6000)  # Cloudflare 해소 대기
            html_before = _safe_page_content(page)
        if "checking your browser" in html_before.lower():
            warnings.warn(
                "로그인 페이지에서 Cloudflare 챌린지 감지. 비로그인으로 계속합니다.\n"
                "해결 방법: VPN/프록시 전환, 또는 headless=False 후 수동 해결.",
                UserWarning,
            )
            return False

        # 이메일 입력 — eJARN 로그인 폼은 type='text' name='email' 사용
        email_sel = (
            "input[type='email']"
            if page.query_selector("input[type='email']")
            else "input[name='email'], input[id='email']"
        )
        page.fill(email_sel, email)
        _random_delay(300, 700)

        # 비밀번호 입력
        page.fill("input[type='password'], input[name='password']", password)
        _random_delay(400, 800)

        # 제출 (reCAPTCHA/hCaptcha가 있어도 invisible v3/v2 embedded 방식은 자동 처리됨)
        page.click("button[type='submit'], input[type='submit'], form button")
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        _random_delay(1500, 2500)

        html_after = _safe_page_content(page)
        # 제출 후에도 로그인 폼이 남아 있으면 실패 (잘못된 비번 or 블로킹)
        still_on_login = bool(page.query_selector("input[name='password']"))
        if still_on_login:
            warnings.warn("로그인 실패: 폼이 여전히 표시됨 (비밀번호 오류 또는 CAPTCHA 차단).", UserWarning)
            return False

        # 로그인 성공 여부 확인
        logged_in = _is_logged_in(page)
        import sys
        print(f"[login] {'성공' if logged_in else '미확인'} (URL: {page.url})", file=sys.stderr)
        return logged_in

    except Exception as e:
        import warnings
        warnings.warn(f"로그인 실패: {e}", UserWarning)
        if enable_hitl:
            raise RuntimeError(f"HITL 로그인 실패: {e}") from e
        return False




@dataclass
class ListEntry:
    """목록 페이지에서 파싱한 기사 한 줄."""
    link: str
    date_str: str  # YYYY.MM.DD
    title: str


@dataclass
class ArticleDetail:
    """상세 페이지에서 추출한 원문 정보."""
    link: str
    date_str: str
    topic: str
    body: str


@dataclass
class FetchedArticleRow:
    """배치 수집: 목록+상세 한 건 + Jarn 토픽 메타(선택)."""
    entry: ListEntry
    detail: ArticleDetail
    source_topic: str = ""
    source_topic_url: str = ""
    related_titles: List[str] = field(default_factory=list)


@dataclass
class TopicLatestBundle:
    """Jarn Special 토픽별 최신 기사 1건 + 나머지 제목 목록."""
    topic_name: str
    topic_url: str
    latest_entry: Optional[ListEntry]
    latest_detail: Optional[ArticleDetail]
    other_titles: List[str]


def _get_html(url: str) -> str:
    """URL에서 HTML 문자열 반환. 실패 시 예외."""
    r = requests.get(
        url,
        headers=_config.DEFAULT_HEADERS,
        timeout=_config.EJARN_REQUEST_TIMEOUT,
        verify=_config.EJARN_VERIFY_SSL,
    )
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def fetch_jarn_special_topic_latest(
    max_topics: int = 9,
    login_email: str = "",
    login_password: str = "",
    enable_hitl: bool = True,
) -> List[TopicLatestBundle]:
    """
    Jarn Special(index/2)에서 토픽 링크를 추출한 뒤,
    각 토픽 페이지에서 URL 기준 dedupe로 최신 기사 1건만 상세 파싱하고,
    나머지 기사 제목은 리스트로 함께 반환한다.
    """
    import warnings
    from playwright.sync_api import sync_playwright

    index_url = "https://www.ejarn.com/series/index/2"
    bundles: List[TopicLatestBundle] = []
    seen_article_links: set[str] = set()

    def _normalize_href(href: str) -> str:
        if not href:
            return ""
        if href.startswith("http"):
            return href
        return "https://www.ejarn.com" + (href if href.startswith("/") else "/" + href)

    with sync_playwright() as p:
        browser, context = _make_browser_context(
            p,
            headless=not enable_hitl,
            use_chrome_channel=enable_hitl,
        )
        page = context.new_page()
        _apply_stealth(page)

        if login_email and login_password:
            _login_with_playwright(page, login_email, login_password, enable_hitl=enable_hitl)

        try:
            page.goto(index_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            page.goto(index_url, wait_until="commit", timeout=30000)
        _random_delay(1200, 2200)
        soup = BeautifulSoup(_safe_page_content(page), "lxml")

        topic_candidates: list[tuple[str, str]] = []
        for a in soup.select('a[href*="/series/list/"]'):
            href = _normalize_href(a.get("href") or "")
            if "/series/list/" not in href:
                continue
            title_text = re.sub(r"\s+", " ", (a.get_text() or "").strip())
            if not title_text:
                title_text = href.rstrip("/").split("/")[-2].replace("-", " ")
            if any(u == href for _, u in topic_candidates):
                continue
            topic_candidates.append((title_text, href))
            if len(topic_candidates) >= max_topics:
                break

        for topic_name, topic_url in topic_candidates:
            try:
                try:
                    page.goto(topic_url, wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    page.goto(topic_url, wait_until="commit", timeout=25000)
                _random_delay(1000, 1800)
                topic_soup = BeautifulSoup(_safe_page_content(page), "lxml")

                article_entries: List[ListEntry] = []
                for a in topic_soup.select('a[href*="/article/detail/"]'):
                    link = _normalize_href(a.get("href") or "")
                    if not link or "/article/detail/" not in link:
                        continue
                    if any(e.link == link for e in article_entries):
                        continue
                    text = re.sub(r"\s+", " ", (a.get_text() or "").strip())
                    date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
                    date_str = date_match.group(1) if date_match else ""
                    title = re.sub(r"\d{4}\.\d{2}\.\d{2}\s*", "", text).strip() or text or "(No title)"
                    article_entries.append(ListEntry(link=link, date_str=date_str, title=title))

                if not article_entries:
                    bundles.append(
                        TopicLatestBundle(
                            topic_name=topic_name,
                            topic_url=topic_url,
                            latest_entry=None,
                            latest_detail=None,
                            other_titles=[],
                        )
                    )
                    continue

                picked: Optional[ListEntry] = None
                picked_idx = -1
                for idx, entry in enumerate(article_entries):
                    if entry.link in seen_article_links:
                        continue
                    picked = entry
                    picked_idx = idx
                    seen_article_links.add(entry.link)
                    break

                if picked is None:
                    bundles.append(
                        TopicLatestBundle(
                            topic_name=topic_name,
                            topic_url=topic_url,
                            latest_entry=None,
                            latest_detail=None,
                            other_titles=[e.title for e in article_entries[:10]],
                        )
                    )
                    continue

                try:
                    page.goto(picked.link, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    page.goto(picked.link, wait_until="commit", timeout=20000)
                _random_delay(900, 1600)
                body, topic, date_str = _extract_body_topic_date(_safe_page_content(page), picked.link)
                detail = ArticleDetail(
                    link=picked.link,
                    date_str=date_str or picked.date_str,
                    topic=topic or picked.title,
                    body=body or "",
                )

                other_titles = [
                    e.title for i, e in enumerate(article_entries) if i != picked_idx and e.title
                ]

                bundles.append(
                    TopicLatestBundle(
                        topic_name=topic_name,
                        topic_url=topic_url,
                        latest_entry=picked,
                        latest_detail=detail,
                        other_titles=list(dict.fromkeys(other_titles))[:20],
                    )
                )
            except Exception as e:
                warnings.warn(f"Jarn Special topic 처리 실패 {topic_url}: {e}", UserWarning)
                bundles.append(
                    TopicLatestBundle(
                        topic_name=topic_name,
                        topic_url=topic_url,
                        latest_entry=None,
                        latest_detail=None,
                        other_titles=[],
                    )
                )

        browser.close()

    return bundles


def fetch_jarn_regular_topic_latest(
    max_topics: int = 9,
    login_email: str = "",
    login_password: str = "",
    enable_hitl: bool = True,
) -> List[TopicLatestBundle]:
    """
    Jarn Regular(index/1)에서 토픽 링크를 추출한 뒤,
    각 토픽 페이지에서 URL 기준 dedupe로 최신 기사 1건만 상세 파싱하고,
    나머지 기사 제목은 리스트로 함께 반환한다.
    """
    import warnings
    from playwright.sync_api import sync_playwright

    index_url = "https://www.ejarn.com/series/index/1"
    bundles: List[TopicLatestBundle] = []
    seen_article_links: set[str] = set()

    def _normalize_href(href: str) -> str:
        if not href:
            return ""
        if href.startswith("http"):
            return href
        return "https://www.ejarn.com" + (href if href.startswith("/") else "/" + href)

    with sync_playwright() as p:
        browser, context = _make_browser_context(
            p,
            headless=not enable_hitl,
            use_chrome_channel=enable_hitl,
        )
        page = context.new_page()
        _apply_stealth(page)

        if login_email and login_password:
            _login_with_playwright(page, login_email, login_password, enable_hitl=enable_hitl)

        try:
            page.goto(index_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            page.goto(index_url, wait_until="commit", timeout=30000)
        _random_delay(1200, 2200)
        soup = BeautifulSoup(_safe_page_content(page), "lxml")

        topic_candidates: list[tuple[str, str]] = []
        for a in soup.select('a[href*="/series/list/"]'):
            href = _normalize_href(a.get("href") or "")
            if "/series/list/" not in href:
                continue
            title_text = re.sub(r"\s+", " ", (a.get_text() or "").strip())
            if not title_text:
                title_text = href.rstrip("/").split("/")[-2].replace("-", " ")
            if any(u == href for _, u in topic_candidates):
                continue
            topic_candidates.append((title_text, href))
            if len(topic_candidates) >= max_topics:
                break

        for topic_name, topic_url in topic_candidates:
            try:
                try:
                    page.goto(topic_url, wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    page.goto(topic_url, wait_until="commit", timeout=25000)
                _random_delay(1000, 1800)
                topic_soup = BeautifulSoup(_safe_page_content(page), "lxml")

                article_entries: List[ListEntry] = []
                for a in topic_soup.select('a[href*="/article/detail/"]'):
                    link = _normalize_href(a.get("href") or "")
                    if not link or "/article/detail/" not in link:
                        continue
                    if any(e.link == link for e in article_entries):
                        continue
                    text = re.sub(r"\s+", " ", (a.get_text() or "").strip())
                    date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
                    date_str = date_match.group(1) if date_match else ""
                    title = re.sub(r"\d{4}\.\d{2}\.\d{2}\s*", "", text).strip() or text or "(No title)"
                    article_entries.append(ListEntry(link=link, date_str=date_str, title=title))

                if not article_entries:
                    bundles.append(
                        TopicLatestBundle(
                            topic_name=topic_name,
                            topic_url=topic_url,
                            latest_entry=None,
                            latest_detail=None,
                            other_titles=[],
                        )
                    )
                    continue

                picked: Optional[ListEntry] = None
                picked_idx = -1
                for idx, entry in enumerate(article_entries):
                    if entry.link in seen_article_links:
                        continue
                    picked = entry
                    picked_idx = idx
                    seen_article_links.add(entry.link)
                    break

                if picked is None:
                    bundles.append(
                        TopicLatestBundle(
                            topic_name=topic_name,
                            topic_url=topic_url,
                            latest_entry=None,
                            latest_detail=None,
                            other_titles=[e.title for e in article_entries[:10]],
                        )
                    )
                    continue

                try:
                    page.goto(picked.link, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    page.goto(picked.link, wait_until="commit", timeout=20000)
                _random_delay(900, 1600)
                body, topic, date_str = _extract_body_topic_date(_safe_page_content(page), picked.link)
                detail = ArticleDetail(
                    link=picked.link,
                    date_str=date_str or picked.date_str,
                    topic=topic or picked.title,
                    body=body or "",
                )

                other_titles = [
                    e.title for i, e in enumerate(article_entries) if i != picked_idx and e.title
                ]

                bundles.append(
                    TopicLatestBundle(
                        topic_name=topic_name,
                        topic_url=topic_url,
                        latest_entry=picked,
                        latest_detail=detail,
                        other_titles=list(dict.fromkeys(other_titles))[:20],
                    )
                )
            except Exception as e:
                warnings.warn(f"Jarn Regular topic 처리 실패 {topic_url}: {e}", UserWarning)
                bundles.append(
                    TopicLatestBundle(
                        topic_name=topic_name,
                        topic_url=topic_url,
                        latest_entry=None,
                        latest_detail=None,
                        other_titles=[],
                    )
                )

        browser.close()

    return bundles


def _get_html_playwright(url: str, timeout: float = 15000) -> str:
    """Playwright로 페이지 로드 후 HTML 반환. 실패 시 빈 문자열."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser, context = _make_browser_context(p)
            page = context.new_page()
            _apply_stealth(page)
            page.goto(url, wait_until="networkidle", timeout=timeout)
            _random_delay(500, 1000)
            html = _safe_page_content(page)
            browser.close()
            return html or ""
    except Exception:
        return ""


def fetch_articles_with_login(
    list_url: str,
    max_items: int = 10,
    login_email: str = "",
    login_password: str = "",
    enable_hitl: bool = True,
) -> tuple[List["ListEntry"], List["ArticleDetail"]]:
    """
    임의의 eJARN 목록 URL에서 로그인 세션을 유지하며 기사를 수집한다.
    CAPTCHA 감지 시 비로그인 모드로 폴백.

    Returns
    -------
    tuple[List[ListEntry], List[ArticleDetail]]
    """
    import warnings
    from playwright.sync_api import sync_playwright

    entries: List[ListEntry] = []
    details: List[ArticleDetail] = []

    with sync_playwright() as p:
        browser, context = _make_browser_context(
            p,
            headless=not enable_hitl,
            use_chrome_channel=enable_hitl,
        )
        page = context.new_page()
        _apply_stealth(page)

        # 로그인 시도
        if login_email and login_password:
            _login_with_playwright(page, login_email, login_password, enable_hitl=enable_hitl)

        # 목록 페이지 로드 (domcontentloaded 후 추가 대기)
        try:
            page.goto(list_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            page.goto(list_url, wait_until="commit", timeout=30000)
        _random_delay(2000, 3000)  # JS 렌더링 대기
        html = _safe_page_content(page)

        if _is_captcha_page(html):
            warnings.warn("목록 페이지에서 CAPTCHA 감지. 수집이 제한될 수 있습니다.", UserWarning)

        soup = BeautifulSoup(html, "lxml")

        # 기사 링크 추출 (다양한 구조 대응)
        for a in soup.select('a[href*="/article/detail/"]'):
            href = a.get("href") or ""
            if not href.startswith("http"):
                href = "https://www.ejarn.com" + (href if href.startswith("/") else "/" + href)
            if not href or "/article/detail/" not in href:
                continue
            if any(e.link == href for e in entries):
                continue

            text = (a.get_text() or "").strip()
            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
            date_str = date_match.group(1) if date_match else ""
            prefix_match = re.match(r"^([^\d]+)?\s*\d{4}\.\d{2}\.\d{2}\s*", text)
            if prefix_match:
                title = text[prefix_match.end():].strip()
            else:
                title = re.sub(r"\d{4}\.\d{2}\.\d{2}\s*", "", text).strip() or text[:120]

            entries.append(ListEntry(link=href, date_str=date_str, title=title))
            if len(entries) >= max_items:
                break

        # 각 기사 상세 수집 (동일 브라우저 = 로그인 쿠키 유지)
        for entry in entries:
            try:
                try:
                    page.goto(entry.link, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    page.goto(entry.link, wait_until="commit", timeout=20000)
                _random_delay(1000, 2000)
                art_html = _safe_page_content(page)
                body, topic, date_str = _extract_body_topic_date(art_html, entry.link)
                details.append(ArticleDetail(
                    link=entry.link,
                    date_str=date_str or entry.date_str,
                    topic=topic or entry.title,
                    body=body or "",
                ))
            except Exception as e:
                warnings.warn(f"상세 수집 실패 {entry.link}: {e}", UserWarning)
                details.append(ArticleDetail(
                    link=entry.link,
                    date_str=entry.date_str,
                    topic=entry.title,
                    body="",
                ))

        browser.close()

    return (entries, details)



def fetch_article_list(
    list_url: str | None = None,
    max_items: int = 10,
) -> List[ListEntry]:
    """
    eJARN 기사 목록 페이지에서 최신 기사 링크·날짜·제목을 수집한다.

    Parameters
    ----------
    list_url : str, optional
        목록 페이지 URL. None이면 설정값 사용.
    max_items : int
        가져올 기사 수 상한.

    Returns
    -------
    List[ListEntry]
        link, date_str(YYYY.MM.DD), title 리스트.
    """
    url = list_url or _config.EJARN_LIST_URL
    html = _get_html(url)
    soup = BeautifulSoup(html, "lxml")
    entries: List[ListEntry] = []

    # 메인 기사 링크: a[href*="/article/detail/"]
    for a in soup.select('a[href*="/article/detail/"]'):
        href = a.get("href") or ""
        if not href.startswith("http"):
            href = "https://www.ejarn.com" + href if href.startswith("/") else ""
        text = (a.get_text() or "").strip()
        if not text or not href or "/article/detail/" not in href:
            continue

        # 중복 제거: 동일 URL은 한 번만
        if any(e.link == href for e in entries):
            continue

        # 패턴: "eJARN News 2026.03.15제목" 또는 "Cover Story 2026.02.25제목" 등
        # 날짜 패턴 YYYY.MM.DD
        date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
        date_str = date_match.group(1) if date_match else ""
        # 제목: 날짜 앞 접두어 제거 후 날짜 제거
        prefix_match = re.match(r"^([^\d]+)?\s*\d{4}\.\d{2}\.\d{2}\s*", text)
        if prefix_match:
            title = text[prefix_match.end() :].strip()
        else:
            title = re.sub(r"\d{4}\.\d{2}\.\d{2}\s*", "", text).strip() or text

        entries.append(ListEntry(link=href, date_str=date_str, title=title))
        if len(entries) >= max_items:
            break

    return entries


def fetch_article_detail(link: str) -> ArticleDetail:
    """
    기사 상세 페이지에서 제목·날짜·본문을 추출한다.

    Parameters
    ----------
    link : str
        기사 상세 URL.

    Returns
    -------
    ArticleDetail
        link, date_str, topic, body.
    """
    html = _get_html(link)
    body, topic, date_str = _extract_body_topic_date(html, link)

    # 본문이 비어 있으면 Playwright로 JS 렌더링 후 재시도
    if (_config.EJARN_USE_PLAYWRIGHT and (not body or len(body) < 100)):
        pw_html = _get_html_playwright(link)
        if pw_html:
            body2, topic2, date_str2 = _extract_body_topic_date(pw_html, link)
            if body2 and len(body2) > len(body):
                body, topic, date_str = body2, topic2 or topic, date_str2 or date_str

    return ArticleDetail(link=link, date_str=date_str, topic=topic or "(No title)", body=body or "")


def _extract_article_date_str(html: str, soup: BeautifulSoup) -> str:
    """
    상세 HTML에서 게시일 문자열(YYYY.MM.DD) 추출.
    기존에는 html[:3000]만 검사해 로그인·긴 헤더 페이지에서 날짜를 놓치는 경우가 많았음.
    """
    # 1) meta property / name
    for key, val in (
        ("property", "article:published_time"),
        ("property", "article:modified_time"),
        ("property", "og:updated_time"),
        ("name", "publishdate"),
        ("name", "date"),
    ):
        tag = soup.find("meta", attrs={key: val})
        if tag and tag.get("content"):
            c = (tag.get("content") or "").strip()
            m = re.search(r"(\d{4})[-.](\d{2})[-.](\d{2})", c)
            if m:
                return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"

    # 2) <time datetime="...">
    for tm in soup.find_all("time"):
        dt = tm.get("datetime") or ""
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", dt)
        if m:
            return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"

    # 3) JSON-LD (datePublished)
    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        raw = script.string or script.get_text() or ""
        if "datePublished" in raw:
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', raw)
            if m:
                c = m.group(1)
                m2 = re.search(r"(\d{4})[-.](\d{2})[-.](\d{2})", c)
                if m2:
                    return f"{m2.group(1)}.{m2.group(2)}.{m2.group(3)}"

    # 4) 본문·헤더 텍스트 앞부분
    head_text = soup.get_text(separator=" ", strip=True)[:12000]
    m = re.search(r"(\d{4}\.\d{2}\.\d{2})", head_text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", head_text)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"

    # 5) HTML 문자열 (상한)
    window = html[:200000] if len(html) > 200000 else html
    m = re.search(r"(\d{4}\.\d{2}\.\d{2})", window)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", window)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"

    return ""


def _extract_body_topic_date(html: str, link: str) -> tuple[str, str, str]:
    """HTML에서 본문·제목·날짜 추출. (body, topic, date_str)."""
    soup = BeautifulSoup(html, "lxml")
    topic = ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        topic = og["content"].strip()
    if not topic:
        h1 = soup.find("h1")
        if h1:
            topic = h1.get_text().strip()
    if not topic:
        t = soup.find("title")
        if t:
            topic = (t.get_text() or "").strip().replace(" | eJARN.com", "").strip()
    topic = (topic or "").replace(" | eJARN.com", "").strip()

    date_str = _extract_article_date_str(html, soup)

    body = ""
    try:
        doc = ReadabilityDocument(html)
        summary_html = doc.summary()
        body_soup = BeautifulSoup(summary_html, "lxml")
        body = body_soup.get_text(separator="\n").strip()
    except Exception:
        pass
    if not body or len(body) < 100:
        for sel in ["[class*='detail']", "[class*='content']", "[class*='body']", "article", "main"]:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(separator="\n").strip()
                if len(t) > 150 and ("March" in t or "From " in t or "2026" in t):
                    body = t
                    break
        if not body or len(body) < 100:
            paras = [p.get_text().strip() for p in soup.select("p") if len(p.get_text()) > 80]
            body = "\n\n".join(paras) if paras else ""
        if not body or len(body) < 100:
            for tag in soup.find_all(["script", "style"]):
                tag.decompose()
            best = ""
            for div in soup.select("div"):
                t = div.get_text(separator="\n").strip()
                if 200 < len(t) < 50000 and ("March" in t or "From " in t or "said " in t):
                    if len(t) > len(best):
                        best = t
            if best:
                body = best

    if "To read more" in body:
        body = body.split("To read more")[0].strip()
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if not date_str and body:
        m = re.search(r"(\d{4}\.\d{2}\.\d{2})", body[:8000])
        if m:
            date_str = m.group(1)
        else:
            m2 = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", body[:8000])
            if m2:
                date_str = f"{m2.group(1)}.{m2.group(2)}.{m2.group(3)}"
    return (body or "", topic, date_str)


def fetch_jarn_regular_february_articles(
    max_articles: int = 5,
    login_email: str = "",
    login_password: str = "",
    enable_hitl: bool = True,
) -> tuple[List[ListEntry], List[ArticleDetail]]:
    """
    Publication > Jarn Regular 페이지에서 February 섹션의
    div.article-list.clm-feature 기사 목록(상한 max_articles)을 수집하고,
    각 기사 상세를 반환한다. 구독 본문 수집 시 login_email/login_password로 로그인한다.
    CAPTCHA 감지 + 스텔스 모드 적용.

    Returns
    -------
    tuple[List[ListEntry], List[ArticleDetail]]
        (목록 엔트리, 상세 리스트). 상세는 같은 순서로 1:1 대응.
    """
    import warnings
    from playwright.sync_api import sync_playwright

    list_url = _config.JARN_REGULAR_URL
    entries: List[ListEntry] = []
    details: List[ArticleDetail] = []

    with sync_playwright() as p:
        browser, context = _make_browser_context(
            p,
            headless=not enable_hitl,
            use_chrome_channel=enable_hitl,
        )
        page = context.new_page()
        _apply_stealth(page)

        # 로그인 시도 (CAPTCHA 처리 포함)
        if login_email and login_password:
            _login_with_playwright(page, login_email, login_password, enable_hitl=enable_hitl)

        # Jarn Regular 페이지 로드
        try:
            page.goto(list_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            page.goto(list_url, wait_until="commit", timeout=30000)
        _random_delay(2000, 3000)
        html = _safe_page_content(page)

        if _is_captcha_page(html):
            warnings.warn("Jarn Regular 페이지에서 CAPTCHA 감지. 수집이 제한될 수 있습니다.", UserWarning)

        soup = BeautifulSoup(html, "lxml")

        # February 섹션 내 .article-list.clm-feature 기사 링크
        cont_left = soup.select_one("div.cont div.contLeft section")
        if cont_left:
            article_list = cont_left.select_one("div.article-list.clm-feature") or cont_left.select_one("div.article-list")
            if not article_list:
                for div in cont_left.select("div"):
                    article_list = div.select_one("div.article-list.clm-feature") or div.select_one("div.article-list")
                    if article_list:
                        break
            if article_list:
                for a in article_list.select('a[href*="/article/detail/"]'):
                    href = a.get("href") or ""
                    if not href.startswith("http"):
                        href = "https://www.ejarn.com" + (href if href.startswith("/") else "/" + href)
                    text = (a.get_text() or "").strip()
                    date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
                    date_str = date_match.group(1) if date_match else ""
                    title = re.sub(r"\d{4}\.\d{2}\.\d{2}\s*", "", text).strip() or text
                    if href and "/article/detail/" in href:
                        entries.append(ListEntry(link=href, date_str=date_str, title=title))
                        if len(entries) >= max_articles:
                            break

        if not entries:
            # fallback: 페이지 내 모든 기사 링크
            for a in soup.select('a[href*="/article/detail/"]'):
                href = a.get("href") or ""
                if not href.startswith("http"):
                    href = "https://www.ejarn.com" + (href if href.startswith("/") else "/" + href)
                if any(e.link == href for e in entries):
                    continue
                text = (a.get_text() or "").strip()
                date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
                date_str = date_match.group(1) if date_match else ""
                title = re.sub(r"\d{4}\.\d{2}\.\d{2}\s*", "", text).strip() or text[:80]
                entries.append(ListEntry(link=href, date_str=date_str, title=title))
                if len(entries) >= max_articles:
                    break

        # 각 기사 상세 수집 (동일 브라우저 = 로그인 쿠키 유지)
        for entry in entries:
            try:
                try:
                    page.goto(entry.link, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    page.goto(entry.link, wait_until="commit", timeout=20000)
                _random_delay(1000, 2000)
                art_html = _safe_page_content(page)
                body, topic, date_str = _extract_body_topic_date(art_html, entry.link)
                details.append(ArticleDetail(
                    link=entry.link,
                    date_str=date_str or entry.date_str,
                    topic=topic or entry.title,
                    body=body or "",
                ))
            except Exception as e:
                warnings.warn(f"상세 수집 실패 {entry.link}: {e}", UserWarning)
                details.append(ArticleDetail(link=entry.link, date_str=entry.date_str, topic=entry.title, body=""))

        browser.close()

    return (entries, details)


# ---------------------------------------------------------------------------
# 배치: 기준일 이후 + 스크롤 목록 확장 (단일 page 세션용)
# ---------------------------------------------------------------------------


def _normalize_ejarn_href(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return "https://www.ejarn.com" + (href if href.startswith("/") else "/" + href)


def parse_article_list_entries_from_html(html: str) -> List[ListEntry]:
    """목록 HTML에서 기사 링크·날짜·제목 추출 (URL 기준 중복 제거, 순서 유지)."""
    soup = BeautifulSoup(html, "lxml")
    entries: List[ListEntry] = []
    for a in soup.select('a[href*="/article/detail/"]'):
        href = _normalize_ejarn_href(a.get("href") or "")
        if not href or "/article/detail/" not in href:
            continue
        if any(e.link == href for e in entries):
            continue
        text = re.sub(r"\s+", " ", (a.get_text() or "").strip())
        date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
        date_str = date_match.group(1) if date_match else ""
        prefix_match = re.match(r"^([^\d]+)?\s*\d{4}\.\d{2}\.\d{2}\s*", text)
        if prefix_match:
            title = text[prefix_match.end() :].strip()
        else:
            title = re.sub(r"\d{4}\.\d{2}\.\d{2}\s*", "", text).strip() or text[:120]
        entries.append(ListEntry(link=href, date_str=date_str, title=title))
    return entries


def _try_expand_ejarn_list(page) -> None:
    """목록 더보기/지연 로딩 유도(사이트마다 버튼 문구 상이)."""
    labels = (
        "Load more",
        "VIEW MORE",
        "View more",
        "Show more",
        "더보기",
    )
    for label in labels:
        try:
            page.get_by_text(label, exact=True).first.click(timeout=2000)
            _random_delay(700, 1400)
        except Exception:
            try:
                page.get_by_role("link", name=re.compile(re.escape(label), re.I)).first.click(timeout=2000)
                _random_delay(700, 1400)
            except Exception:
                try:
                    page.get_by_role("button", name=re.compile(re.escape(label), re.I)).first.click(timeout=2000)
                    _random_delay(700, 1400)
                except Exception:
                    pass


def _goto_list_page(page, url: str) -> None:
    """목록/인덱스 로드. networkidle은 장시간·무한 대기를 유발할 수 있어 사용하지 않음."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        page.goto(url, wait_until="commit", timeout=45000)
    _random_delay(800, 1500)
    try:
        page.wait_for_load_state("load", timeout=12000)
    except Exception:
        pass
    _random_delay(400, 900)
    try:
        page.wait_for_selector(
            'a[href*="/article/detail/"]',
            timeout=12000,
            state="attached",
        )
    except Exception:
        pass
    for _ in range(3):
        try:
            page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight * 0.25)")
        except Exception:
            pass
        _random_delay(200, 450)
    _try_expand_ejarn_list(page)
    _random_delay(500, 1000)


def _scroll_collect_article_entries(
    page,
    list_url: str,
    max_unique: int,
    max_scroll_rounds: int = 80,
    stable_needed: int = 5,
) -> List[ListEntry]:
    """목록 URL에서 스크롤하며 기사 링크를 최대 max_unique개까지 수집."""
    _goto_list_page(page, list_url)
    ordered: List[ListEntry] = []
    seen: set[str] = set()
    stable = 0
    prev_n = 0
    for round_idx in range(max(1, max_scroll_rounds)):
        html = _safe_page_content(page)
        for e in parse_article_list_entries_from_html(html):
            if e.link not in seen:
                seen.add(e.link)
                ordered.append(e)
                if len(ordered) >= max_unique:
                    return ordered
        n = len(ordered)
        # 링크가 0개일 때는 stable 카운트로 조기 종료하지 않음(JS·로그인 DOM 지연)
        if n == 0:
            stable = 0
        elif n == prev_n:
            stable += 1
            if stable >= stable_needed:
                break
        else:
            stable = 0
        prev_n = n
        try:
            page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        except Exception:
            pass
        _random_delay(550, 1100)
        if n > 0 and round_idx % 4 == 3:
            _try_expand_ejarn_list(page)
    return ordered


def _fetch_article_detail_on_page(page, entry: ListEntry) -> ArticleDetail:
    try:
        page.goto(entry.link, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        page.goto(entry.link, wait_until="commit", timeout=20000)
    _random_delay(800, 1500)
    art_html = _safe_page_content(page)
    body, topic, date_str = _extract_body_topic_date(art_html, entry.link)
    return ArticleDetail(
        link=entry.link,
        date_str=date_str or entry.date_str,
        topic=topic or entry.title,
        body=body or "",
    )


def fetch_category_since_on_page(
    page,
    list_url: str,
    since: date,
    max_list_articles: int,
    max_section_articles: int,
) -> List[FetchedArticleRow]:
    """카테고리형 목록: 스크롤 수집 후 since 이상만 상세 확인, 섹션당 최대 max_section_articles건."""
    import warnings

    from src.tools.dates import list_entry_may_include_since, parse_ejarn_date

    cap = max(1, max_section_articles)
    entries = _scroll_collect_article_entries(page, list_url, max_list_articles)
    rows: List[FetchedArticleRow] = []
    for entry in entries:
        if len(rows) >= cap:
            break
        if not list_entry_may_include_since(entry.date_str, since):
            continue
        detail = _fetch_article_detail_on_page(page, entry)
        dd = parse_ejarn_date(detail.date_str) or parse_ejarn_date(entry.date_str)
        if dd is None:
            warnings.warn(f"날짜 없음으로 제외: {entry.link}", UserWarning)
            continue
        if dd < since:
            continue
        rows.append(FetchedArticleRow(entry=entry, detail=detail))
    return rows


def fetch_jarn_series_since_on_page(
    page,
    index_url: str,
    since: date,
    max_list_per_topic: int,
    max_topics: int,
    max_section_articles: int,
) -> List[FetchedArticleRow]:
    """Jarn Regular(1) / Special(2): 토픽 순회, since 이후 기사, 섹션당 최대 max_section_articles건."""
    import warnings

    from src.tools.dates import list_entry_may_include_since, parse_ejarn_date

    cap = max(1, max_section_articles)

    _goto_list_page(page, index_url)
    soup = BeautifulSoup(_safe_page_content(page), "lxml")
    topic_candidates: list[tuple[str, str]] = []
    for a in soup.select('a[href*="/series/list/"]'):
        href = _normalize_ejarn_href(a.get("href") or "")
        if "/series/list/" not in href:
            continue
        title_text = re.sub(r"\s+", " ", (a.get_text() or "").strip())
        if not title_text:
            title_text = href.rstrip("/").split("/")[-2].replace("-", " ")
        if any(u == href for _, u in topic_candidates):
            continue
        topic_candidates.append((title_text, href))
        if len(topic_candidates) >= max(1, max_topics):
            break

    all_rows: List[FetchedArticleRow] = []
    seen_links: set[str] = set()

    for topic_name, topic_url in topic_candidates:
        if len(all_rows) >= cap:
            break
        try:
            entries = _scroll_collect_article_entries(page, topic_url, max_list_per_topic)
            for entry in entries:
                if len(all_rows) >= cap:
                    break
                if entry.link in seen_links:
                    continue
                if not list_entry_may_include_since(entry.date_str, since):
                    continue
                detail = _fetch_article_detail_on_page(page, entry)
                dd = parse_ejarn_date(detail.date_str) or parse_ejarn_date(entry.date_str)
                if dd is None:
                    warnings.warn(f"날짜 없음으로 제외: {entry.link}", UserWarning)
                    continue
                if dd < since:
                    continue
                seen_links.add(entry.link)
                otitles: List[str] = []
                for e2 in entries:
                    if e2.link == entry.link:
                        continue
                    ld2 = parse_ejarn_date(e2.date_str)
                    if ld2 is not None and ld2 >= since:
                        otitles.append(e2.title)
                all_rows.append(
                    FetchedArticleRow(
                        entry=entry,
                        detail=detail,
                        source_topic=topic_name,
                        source_topic_url=topic_url,
                        related_titles=list(dict.fromkeys(otitles))[:30],
                    )
                )
        except Exception as e:
            warnings.warn(f"Jarn 토픽 실패 {topic_url}: {e}", UserWarning)

    return all_rows


def execute_batch_fetch_on_logged_in_page(
    page,
    specs: List[tuple[str, str, str]],
    since: date,
    max_list_articles: int,
    max_topics: int,
    max_section_articles: int,
) -> dict[str, List[FetchedArticleRow]]:
    """
    이미 로그인된 page에서 섹션별 수집.

    Parameters
    ----------
    specs : list of (list_url, mode, basename)
        mode는 'jarn_series' 또는 'category'.
    max_section_articles : 섹션당 since 통과 후 최대 저장 건수.
    """
    import sys
    import time

    scroll_cap = max(max_list_articles, max(1, max_section_articles) * 15)

    out: dict[str, List[FetchedArticleRow]] = {}
    for list_url, mode, basename in specs:
        url = (list_url or "").strip()
        print(f"[batch] 섹션 시작: {basename} ({url})", file=sys.stderr)
        if mode == "jarn_series":
            rows = fetch_jarn_series_since_on_page(
                page,
                url,
                since,
                max_list_per_topic=scroll_cap,
                max_topics=max_topics,
                max_section_articles=max_section_articles,
            )
        elif mode == "category":
            rows = fetch_category_since_on_page(
                page, url, since, scroll_cap, max_section_articles
            )
        else:
            raise ValueError(f"알 수 없는 batch mode: {mode!r}")
        out[basename] = rows
        print(f"[batch] 섹션 완료: {basename} ({len(rows)}건)", file=sys.stderr)
        time.sleep(0.35)
    return out


