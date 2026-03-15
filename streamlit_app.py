import json
import multiprocessing as mp
import os
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from openai import OpenAI

# 히스토리 파일 경로 (앱과 동일 디렉터리)
HISTORY_FILE = Path(__file__).parent / ".ejarn_history.json"
HITL_STATUS_FILE = Path(__file__).parent / ".hitl_status.json"
HITL_CONFIRM_FILE = Path(__file__).parent / ".hitl_confirm.json"
MAX_HISTORY = 30  # 최대 보관 건수

from src.pipeline import (
    run_jarn_regular_balanced,
    run_jarn_special_balanced,
    run_pipeline,
)
from src.config import OPENAI_API_KEY


TOPIC_OPTIONS = {
    "Publication > Jarn Regular": "https://www.ejarn.com/series/index/1",
    "Publication > Jarn Special": "https://www.ejarn.com/series/index/2",
    "eJarn News": "https://www.ejarn.com/category/eJarn_news_index",
    "Cover Story": "https://www.ejarn.com/category/cover_story_index",
    "Event > Exhibition": "https://www.ejarn.com/category/exhibition_index",
    "Report": "https://www.ejarn.com/category/report_index",
    "Special Issue": "https://www.ejarn.com/category/special_issue_index",
    "Regular Issue": "https://www.ejarn.com/category/regular_issue_index",
}


def _inject_style() -> None:
    st.markdown(
        """
        <style>
          .stApp { background: linear-gradient(180deg, #f7f9fc 0%, #eef3f9 100%); }
          .block-container { padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1200px; }
          .hero-card {
            background: linear-gradient(135deg, #0b3a66 0%, #1b5f9f 65%, #2f7dc5 100%);
            color: white;
            border-radius: 16px;
            padding: 20px 22px;
            margin-bottom: 14px;
            box-shadow: 0 12px 24px rgba(9, 47, 86, 0.22);
          }
          .hero-card h1 { font-size: 1.55rem; margin: 0 0 6px 0; }
          .hero-card p { margin: 0; opacity: 0.95; }
          .soft-box {
            background: white;
            border: 1px solid #e3e9f3;
            border-radius: 12px;
            padding: 10px 12px;
          }
          .hist-btn button {
            text-align: left !important;
            font-size: 0.78rem !important;
            line-height: 1.4 !important;
            padding: 6px 10px !important;
            border-radius: 8px !important;
            white-space: normal !important;
            height: auto !important;
          }
          .hist-active button {
            background: #1b5f9f !important;
            color: white !important;
            border: none !important;
          }
          .hist-badge {
            display: inline-block;
            background: #e3edf8;
            color: #1b5f9f;
            font-size: 0.68rem;
            border-radius: 10px;
            padding: 1px 7px;
            margin-bottom: 4px;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _run_collection(selected_url: str, max_items: int, disable_ssl_verify: bool):
    verify_ssl = False if disable_ssl_verify else None

    if selected_url == "https://www.ejarn.com/series/index/1":
        return run_jarn_regular_balanced(max_topics=9, require_hitl_login=True)
    if selected_url == "https://www.ejarn.com/series/index/2":
        return run_jarn_special_balanced(max_topics=9, require_hitl_login=True)

    return run_pipeline(
        list_url=selected_url,
        max_articles=max_items,
        verify_ssl=verify_ssl,
        require_hitl_login=True,
    )


def _collection_worker(selected_url: str, max_items: int, disable_ssl_verify: bool, queue: mp.Queue) -> None:
    """Playwright 수집을 별도 프로세스에서 수행해 Windows asyncio 충돌을 피한다."""
    try:
        os.environ["EJARN_HITL_STATUS_FILE"] = str(HITL_STATUS_FILE.resolve())
        os.environ["EJARN_HITL_CONFIRM_FILE"] = str(HITL_CONFIRM_FILE.resolve())
        os.environ["EJARN_HITL_REQUIRE_CONFIRM"] = "1"
        os.environ["EJARN_HITL_NON_INTERACTIVE"] = "1"
        collection = _run_collection(selected_url, max_items, disable_ssl_verify)
        queue.put({"ok": True, "data": collection.model_dump(mode="json")})
    except Exception as e:
        queue.put({"ok": False, "error": str(e)})


def _start_collection_process(
    selected_url: str,
    max_items: int,
    disable_ssl_verify: bool,
) -> tuple[mp.Process, mp.Queue]:
    """수집 백그라운드 프로세스를 시작하고 (process, queue)를 반환한다."""
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()

    if HITL_STATUS_FILE.exists():
        try:
            HITL_STATUS_FILE.unlink()
        except Exception:
            pass
    if HITL_CONFIRM_FILE.exists():
        try:
            HITL_CONFIRM_FILE.unlink()
        except Exception:
            pass

    process = ctx.Process(
        target=_collection_worker,
        args=(selected_url, max_items, disable_ssl_verify, queue),
        daemon=True,
    )
    process.start()
    return process, queue


def _finalize_collection_process(process: mp.Process, queue: mp.Queue) -> dict:
    """완료된 수집 프로세스 결과를 회수해 JSON(dict)로 반환한다."""
    process.join(timeout=0)
    if process.exitcode is None:
        process.terminate()
        raise RuntimeError("수집 프로세스가 종료되지 않았습니다.")
    if process.exitcode != 0 and queue.empty():
        raise RuntimeError(f"수집 프로세스 비정상 종료(exit={process.exitcode}).")

    result = queue.get() if not queue.empty() else None

    if HITL_STATUS_FILE.exists():
        try:
            HITL_STATUS_FILE.unlink()
        except Exception:
            pass
    if HITL_CONFIRM_FILE.exists():
        try:
            HITL_CONFIRM_FILE.unlink()
        except Exception:
            pass

    if not result:
        raise RuntimeError("수집 결과를 받지 못했습니다.")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "수집 실패")
    return result["data"]


def _format_hitl_status(status_payload: dict) -> str:
    """HITL 상태 JSON을 Streamlit 안내 문구로 변환한다."""
    stage = status_payload.get("stage", "")
    waited = int(status_payload.get("waited_sec", 0) or 0)
    msg = status_payload.get("message", "")
    url = status_payload.get("url", "")
    on_login = status_payload.get("on_login_url")
    has_logout = status_payload.get("has_logout_link")
    has_user_menu = status_payload.get("has_user_menu")
    has_cookie = status_payload.get("has_auth_cookie")
    has_captcha = status_payload.get("has_captcha_marker")

    base = f"진행 상태: {stage or 'processing'} | 대기 {waited}초"
    if msg:
        base += f"\n- {msg}"
    if stage == "login_unverified_proceed":
        base += "\n- 안내: 완료 버튼 신호에 따라 로그인 확인 없이 다음 단계로 진행합니다."
    if url:
        base += f"\n- URL: {url}"
    if any(v is not None for v in [on_login, has_logout, has_user_menu, has_cookie]):
        base += (
            "\n- 판정: "
            f"on_login={on_login}, logout={has_logout}, user_menu={has_user_menu}, auth_cookie={has_cookie}, captcha={has_captcha}"
        )
    return base


# ---------------------------------------------------------------------------
# 히스토리 헬퍼
# ---------------------------------------------------------------------------

def _load_history() -> list[dict]:
    """디스크에서 수집 히스토리를 읽어 반환한다."""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_history(entry: dict) -> None:
    """수집 완료 항목을 히스토리 파일에 추가 저장한다."""
    entries = _load_history()
    # 동일 파일이 이미 있으면 교체
    entries = [e for e in entries if e.get("file") != entry.get("file")]
    entries.insert(0, entry)  # 최신 항목이 맨 위
    entries = entries[:MAX_HISTORY]
    HISTORY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _scan_folder_json(folder: Path | None = None) -> list[dict]:
    """폴더 내 eJARN 결과 JSON 파일을 스캔해 히스토리 엔트리 목록으로 반환한다."""
    import re
    folder = folder or Path(__file__).parent
    entries = []
    for p in sorted(folder.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        if p.resolve() == HISTORY_FILE.resolve():
            continue  # 히스토리 파일 자체는 제외
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        items = data.get("items")
        if not isinstance(items, list) or not items:
            continue  # eJARN 결과 파일이 아니면 제외
        source = data.get("source", "eJARN")
        collected_at = data.get(
            "collected_at",
            datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        )
        # 파일명에서 날짜 파트를 추출해 label 생성
        stem = p.stem  # e.g. ejarn_result_20260315_182721
        m = re.search(r"(\d{8})", stem)
        if m:
            d = m.group(1)
            label = f"{source} {d[:4]}-{d[4:6]}-{d[6:8]}"
        else:
            label = stem.replace("_", " ")
        entries.append({
            "label": label,
            "url": "",
            "file": str(p.resolve()),
            "collected_at": collected_at,
            "count": len(items),
        })
    return entries


def _sync_history_with_folder() -> None:
    """
    앱 시작 시 프로젝트 폴더의 JSON 파일을 스캔해 히스토리 파일에 병합한다.
    - 이미 히스토리에 있는 항목은 label/url 등 기존 값을 유지
    - 새 파일만 추가, collected_at 기준 최신순 정렬
    """
    scanned = _scan_folder_json()
    existing = _load_history()
    by_file: dict[str, dict] = {e["file"]: e for e in existing}
    for s in scanned:
        if s["file"] not in by_file:
            by_file[s["file"]] = s  # 새 파일만 추가
    merged = sorted(by_file.values(), key=lambda e: e.get("collected_at", ""), reverse=True)
    merged = merged[:MAX_HISTORY]
    HISTORY_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_output_name() -> str:
    return f"ejarn_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def _truncate(text: str, max_len: int = 180) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _answer_with_llm(query: str, result_json: dict, chat_history: list[dict]) -> str:
    if not OPENAI_API_KEY:
        return "OPENAI_API_KEY가 설정되어 있지 않아 챗봇 답변을 생성할 수 없습니다."

    items = result_json.get("items", [])
    compact_context = []
    for item in items:
        compact_context.append(
            {
                "date": item.get("date", ""),
                "topic": item.get("topic", ""),
                "summary": item.get("summary", ""),
                "company": item.get("company", []),
                "category": item.get("category", []),
                "product_type": item.get("product_type", []),
                "market_segment": item.get("market_segment", []),
                "link": item.get("link", ""),
            }
        )

    system_prompt = (
        "You are an analyst assistant for eJARN collection results. "
        "Answer only from the provided JSON context. "
        "If information is missing, explicitly say it is not in the current dataset. "
        "When possible, cite topic titles and links from the dataset in your answer. "
        "Respond in Korean."
    )

    history_messages = []
    for h in chat_history[-6:]:
        history_messages.append({"role": "user", "content": h.get("q", "")})
        history_messages.append({"role": "assistant", "content": h.get("a", "")})

    user_payload = {
        "query": query,
        "dataset": compact_context,
    }

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            *history_messages,
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        max_tokens=700,
    )
    return (response.choices[0].message.content or "").strip()


def main() -> None:
    st.set_page_config(
        page_title="eJARN Collector",
        page_icon="📰",
        layout="wide",
    )
    _inject_style()

    st.markdown(
        """
        <div class="hero-card">
          <h1>eJARN Insight Collector</h1>
          <p>주제를 선택하고 수집을 실행하면, 결과를 확인하고 JSON으로 저장/다운로드할 수 있습니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("수집 설정")
        selected_label = st.selectbox("주제 선택", list(TOPIC_OPTIONS.keys()), index=0)
        selected_url = TOPIC_OPTIONS[selected_label]

        max_items = st.number_input("수집 건수 (--max)", min_value=1, max_value=50, value=5, step=1)
        disable_ssl_verify = st.checkbox("SSL 검증 비활성화", value=False)

        output_name = st.text_input("저장 파일명", value=_default_output_name())
        if not output_name.lower().endswith(".json"):
            output_name += ".json"

        run_btn = st.button("수집 실행", type="primary", use_container_width=True)

        # ── 수집 히스토리 ──────────────────────────────────────────
        st.divider()
        st.markdown("#### 📋 수집 히스토리")

        hist_entries = _load_history()
        if not hist_entries:
            st.caption("아직 수집 기록이 없습니다.")
        else:
            # 히스토리 초기화 버튼
            if st.button("히스토리 전체 삭제", use_container_width=True):
                if HISTORY_FILE.exists():
                    HISTORY_FILE.unlink()
                st.session_state.viewing_result = None
                st.session_state.viewing_label = None
                st.rerun()

            for idx, entry in enumerate(hist_entries):
                label = entry.get("label", "(알 수 없음)")
                ts = entry.get("collected_at", "")[:16].replace("T", " ")
                count = entry.get("count", "?")
                file_path = entry.get("file", "")

                is_active = (
                    st.session_state.get("viewing_file") == file_path
                )
                btn_label = f"{label}\n{ts}  |  {count}건"

                col_cls = "hist-active" if is_active else "hist-btn"
                st.markdown(f'<div class="{col_cls}">', unsafe_allow_html=True)
                if st.button(btn_label, key=f"hist_{idx}", use_container_width=True):
                    try:
                        loaded = json.loads(Path(file_path).read_text(encoding="utf-8"))
                        st.session_state.viewing_result = loaded
                        st.session_state.viewing_label = label
                        st.session_state.viewing_file = file_path
                        st.session_state.chat_history = []
                    except Exception as e:
                        st.error(f"파일 로드 실패: {e}")
                st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("HITL 로그인 안내", expanded=True):
        st.info(
            "실행하면 Chrome 창이 열립니다. hCaptcha/로그인을 완료한 뒤 진행됩니다. "
            "터미널 입력이 없는 환경(Streamlit)에서는 최대 600초 동안 로그인 완료를 대기하며, "
            "시간 내 미완료 시 수집을 중단합니다."
        )

    if "latest_result" not in st.session_state:
        st.session_state.latest_result = None
        st.session_state.latest_file = None
    if "viewing_result" not in st.session_state:
        st.session_state.viewing_result = None
        st.session_state.viewing_label = None
        st.session_state.viewing_file = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "collecting" not in st.session_state:
        st.session_state.collecting = False
        st.session_state.collection_process = None
        st.session_state.collection_queue = None
        st.session_state.collection_started_at = 0.0
        st.session_state.pending_output_name = ""
        st.session_state.pending_selected_label = ""
        st.session_state.pending_selected_url = ""
        st.session_state.hitl_confirmed = False

    # 앱 시작(세션당 1회)마다 폴더 내 JSON을 스캔해 히스토리에 자동 병합
    if "history_synced" not in st.session_state:
        _sync_history_with_folder()
        st.session_state.history_synced = True

    if run_btn and not st.session_state.collecting:
        try:
            process, queue = _start_collection_process(
                selected_url,
                int(max_items),
                disable_ssl_verify,
            )
            st.session_state.collecting = True
            st.session_state.collection_process = process
            st.session_state.collection_queue = queue
            st.session_state.collection_started_at = time.time()
            st.session_state.pending_output_name = output_name
            st.session_state.pending_selected_label = selected_label
            st.session_state.pending_selected_url = selected_url
            st.session_state.hitl_confirmed = False
            st.rerun()
        except Exception as e:
            st.error(f"수집 시작 실패: {e}")

    if st.session_state.collecting:
        st.markdown("### 수집 진행 상태")
        elapsed = int(time.time() - (st.session_state.collection_started_at or time.time()))
        st.info(f"수집 실행 중... 경과 {elapsed}초")

        if HITL_STATUS_FILE.exists() and elapsed >= 5:
            try:
                status_payload = json.loads(HITL_STATUS_FILE.read_text(encoding="utf-8"))
                st.info(_format_hitl_status(status_payload))
            except Exception:
                pass

        c_run_1, c_run_2, c_run_3 = st.columns(3)
        if c_run_1.button("✅ 로그인 완료(진행)", use_container_width=True):
            HITL_CONFIRM_FILE.write_text(
                json.dumps({"confirmed_at": datetime.utcnow().isoformat()}, ensure_ascii=False),
                encoding="utf-8",
            )
            st.session_state.hitl_confirmed = True
            st.success("완료 신호를 전달했습니다. 로그인 성공이 확인되면 다음 단계로 진행합니다.")
        if c_run_2.button("🔄 상태 새로고침", use_container_width=True):
            st.rerun()
        if c_run_3.button("⛔ 수집 중단", use_container_width=True):
            try:
                p = st.session_state.collection_process
                if p and p.is_alive():
                    p.terminate()
            except Exception:
                pass
            st.session_state.collecting = False
            st.session_state.collection_process = None
            st.session_state.collection_queue = None
            st.warning("수집을 중단했습니다.")

        process = st.session_state.collection_process
        queue = st.session_state.collection_queue
        if process and not process.is_alive():
            try:
                result = _finalize_collection_process(process, queue)

                out_path = Path(st.session_state.pending_output_name or _default_output_name())
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

                st.session_state.latest_result = result
                st.session_state.latest_file = str(out_path)

                _save_history({
                    "label": st.session_state.pending_selected_label or selected_label,
                    "url": st.session_state.pending_selected_url or selected_url,
                    "file": str(out_path.resolve()),
                    "collected_at": result.get("collected_at", datetime.utcnow().isoformat()),
                    "count": len(result.get("items", [])),
                })
                st.session_state.viewing_result = result
                st.session_state.viewing_label = st.session_state.pending_selected_label or selected_label
                st.session_state.viewing_file = str(out_path.resolve())
                st.session_state.chat_history = []

                st.success(f"완료: {len(result.get('items', []))}건 저장됨 → {out_path}")
            except Exception as e:
                st.error(f"수집 실패: {e}")
            finally:
                st.session_state.collecting = False
                st.session_state.collection_process = None
                st.session_state.collection_queue = None
        else:
            # 백그라운드 프로세스 상태를 주기적으로 확인하기 위한 자동 새로고침
            time.sleep(2)
            st.rerun()

    # 히스토리 선택 결과 우선, 없으면 최신 결과
    result = st.session_state.viewing_result or st.session_state.latest_result
    viewing_label = st.session_state.get("viewing_label") or "최신 결과"
    if result:
        items = result.get("items", [])

        # 현재 보고 있는 결과 라벨 표시
        st.markdown(
            f'<span class="hist-badge">📂 {viewing_label}</span>',
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("수집 건수", len(items))
        c2.metric("소스", result.get("source", "-"))
        c3.metric("수집 시각", result.get("collected_at", "-")[:19])

        st.markdown("### 결과 미리보기")
        preview_rows = []
        for item in items:
            preview_rows.append(
                {
                    "date": item.get("date", ""),
                    "topic": item.get("topic", ""),
                    "summary": _truncate(item.get("summary", ""), 220),
                    "source_topic": item.get("source_topic", ""),
                    "category": ", ".join(item.get("category", [])),
                    "product_type": ", ".join(item.get("product_type", [])),
                    "link": item.get("link", ""),
                }
            )
        st.dataframe(preview_rows, use_container_width=True, hide_index=True)

        st.markdown("### 항목별 상세")
        for idx, item in enumerate(items, start=1):
            title = f"{idx}. {item.get('topic', '(No topic)')}"
            with st.expander(title, expanded=False):
                st.markdown(f"**요약**: {item.get('summary', '')}")
                st.markdown(f"**링크**: {item.get('link', '')}")
                st.markdown(
                    f"**분류**: category={', '.join(item.get('category', []))} | "
                    f"product={', '.join(item.get('product_type', []))}"
                )

        st.markdown("### JSON 기반 챗봇")
        st.caption("현재 화면의 수집 결과(JSON)만 기반으로 답변합니다.")

        for chat in st.session_state.chat_history:
            with st.chat_message("user"):
                st.write(chat.get("q", ""))
            with st.chat_message("assistant"):
                st.write(chat.get("a", ""))

        user_q = st.chat_input("예: 냉매가 Natural인 기사만 요약해줘")
        if user_q:
            with st.chat_message("user"):
                st.write(user_q)
            with st.chat_message("assistant"):
                with st.spinner("답변 생성 중..."):
                    try:
                        answer = _answer_with_llm(user_q, result, st.session_state.chat_history)
                    except Exception as e:
                        answer = f"챗봇 응답 실패: {e}"
                    st.write(answer)
            st.session_state.chat_history.append({"q": user_q, "a": answer})

        st.markdown("### JSON")
        st.json(result, expanded=False)

        data_bytes = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
        dl_filename = Path(
            st.session_state.get("viewing_file")
            or st.session_state.latest_file
            or _default_output_name()
        ).name
        st.download_button(
            label="JSON 다운로드",
            data=data_bytes,
            file_name=dl_filename,
            mime="application/json",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
