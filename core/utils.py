"""
core/utils.py
공통 유틸리티 함수 모음.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Iterable

from core import config as _config


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # 범위 표현(2025-07-10~2025-07-12) 첫 날짜
    m = re.match(r"(\d{4}[-/]\d{2}[-/]\d{2})", s)
    if m:
        return parse_date(m.group(1))
    return None


def days_until(date_str: str | None) -> int | None:
    d = parse_date(date_str)
    if d is None:
        return None
    return (d.date() - datetime.now().date()).days


def safe_json(obj: Any, default=None) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps(default if default is not None else {}, ensure_ascii=False)


def loads(s: str | None, default=None):
    if not s:
        return default if default is not None else {}
    try:
        return json.loads(s)
    except Exception:
        return default if default is not None else {}


def export_path(filename: str) -> str:
    ensure_dir(_config.EXPORT_DIR)
    return os.path.join(_config.EXPORT_DIR, filename)


def chunked(lst: list, size: int) -> Iterable[list]:
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def short(text: str | None, n: int = 60) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= n else text[:n] + "..."


def to_man(value: Any) -> int:
    """다양한 표현 -> 만원 단위 정수"""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).replace(",", "").replace(" ", "")
    total = 0
    if "억" in s:
        parts = s.split("억")
        try:
            total += int(float(parts[0])) * 10000
        except ValueError:
            pass
        s = parts[1] if len(parts) > 1 else ""
    if "만원" in s:
        s = s.replace("만원", "")
    if s.isdigit():
        total += int(s)
    return total


def risk_emoji(level: str | int) -> str:
    if isinstance(level, (int, float)):
        n = int(level)
        if n <= 3:
            return "🟢"
        if n <= 6:
            return "🟡"
        return "🔴"
    table = {"low": "🟢", "medium": "🟡", "high": "🔴", "very_low": "⚪"}
    return table.get(str(level), "⬜")


def grade_from_score(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"
