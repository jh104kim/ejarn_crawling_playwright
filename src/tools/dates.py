"""
eJARN 목록/상세에 쓰이는 날짜 문자열(YYYY.MM.DD) 파싱.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional


_DATE_DOT_RE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")


def parse_ejarn_date(date_str: str) -> Optional[date]:
    """'2026.03.15' 형태를 date로 변환. 파싱 불가면 None."""
    if not date_str or not str(date_str).strip():
        return None
    m = _DATE_DOT_RE.search(str(date_str).strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_since_date_env(s: str) -> date:
    """'YYYY-MM-DD' 또는 'YYYY.MM.DD' → date."""
    s = (s or "").strip()
    if not s:
        raise ValueError("since 날짜 문자열이 비었습니다.")
    parts = s.replace(".", "-").split("-")
    if len(parts) == 3:
        y, mo, d = int(parts[0]), int(parts[1]), int(parts[2])
        return date(y, mo, d)
    raise ValueError(f"since 날짜 형식을 알 수 없습니다: {s!r}")


def list_entry_may_include_since(list_date_str: str, since: date) -> bool:
    """
    목록에 표시된 날짜만으로 판단.
    None(미표기)이면 상세에서 확인해야 하므로 True.
    명시적으로 since 이전이면 False.
    """
    parsed = parse_ejarn_date(list_date_str)
    if parsed is None:
        return True
    return parsed >= since
