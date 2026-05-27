"""
modules/legal/rights_parser.py
등기부 텍스트 -> 권리 시계열(rights_timeline) 파싱 및 저장.

- USE_AI=true + 키 있음: Claude API로 파싱 보강
- 그 외: 정규식 기반 파싱
- 텍스트가 없으면: item_id 기반 결정적 mock 시계열(3~7건) 생성
"""
from __future__ import annotations

import json
import random
import re
from datetime import date, timedelta

from core import config
from core.ai_client import call_claude
from core.database import get_connection, init_db
from core.logger import log

# 파싱 대상 권리 유형 (정규식 키워드)
RIGHT_TYPE_PATTERNS: dict[str, str] = {
    "소유권이전": "갑구",
    "소유권보존": "갑구",
    "근저당권": "을구",
    "저당권": "을구",
    "전세권": "을구",
    "지상권": "을구",
    "임차권": "을구",
    "주택임차권": "을구",
    "담보가등기": "갑구",
    "가등기": "갑구",
    "가압류": "갑구",
    "가처분": "갑구",
    "압류": "갑구",
    "경매개시결정": "갑구",
    "예고등기": "갑구",
}

_DATE_PATTERNS = [
    re.compile(r"(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})"),
]


def parse_korean_amount(text: str) -> int | None:
    """'금 1억5,000만원', '채권최고액 240,000,000원', '1억 5천만원' -> 원 단위 정수."""
    if not text:
        return None
    s = text.replace(" ", "").replace(",", "")

    won = 0
    matched = False
    rest = s

    m_eok = re.search(r"(\d+(?:\.\d+)?)억", rest)
    if m_eok:
        won += int(float(m_eok.group(1)) * 100_000_000)
        matched = True
        rest = rest[m_eok.end():]

    m_cheonman = re.search(r"(\d+)천만", rest)
    if m_cheonman:
        won += int(m_cheonman.group(1)) * 10_000_000
        matched = True
        rest = rest[:m_cheonman.start()] + rest[m_cheonman.end():]

    m_man = re.search(r"(\d+)만", rest)
    if m_man:
        won += int(m_man.group(1)) * 10_000
        matched = True

    if matched and won > 0:
        return won

    # 순수 숫자 + 원 / '금' 접두
    m_num = re.search(r"(\d{6,})원", s)
    if m_num:
        return int(m_num.group(1))
    m_num2 = re.search(r"금(\d{6,})", s)
    if m_num2:
        return int(m_num2.group(1))
    return None


def _normalize_date(y: str, m: str, d: str) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _find_date(line: str) -> str | None:
    for pat in _DATE_PATTERNS:
        m = pat.search(line)
        if m:
            return _normalize_date(*m.groups())
    return None


def _parse_with_regex(text: str) -> list[dict]:
    rights: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        right_type = next((rt for rt in RIGHT_TYPE_PATTERNS if rt in line), None)
        if not right_type:
            continue
        reg_date = _find_date(line)
        amount = parse_korean_amount(line)
        holder = None
        m_holder = re.search(r"(?:채권자|권리자|소유자|임차인)\s*[:：]?\s*([^\s,/]+)", line)
        if m_holder:
            holder = m_holder.group(1)
        rights.append({
            "section": RIGHT_TYPE_PATTERNS[right_type],
            "register_date": reg_date,
            "right_type": right_type,
            "holder": holder,
            "amount": amount,
            "raw_text": line[:200],
        })
    return _finalize(rights)


def _parse_with_ai(text: str) -> list[dict]:
    prompt = (
        "다음 등기부 텍스트에서 권리 시계열을 추출해 JSON 배열로만 출력하라.\n"
        "각 원소 키: section(갑구/을구), register_date(YYYY-MM-DD), "
        "right_type, holder, amount(원 단위 정수 또는 null).\n"
        "단정 표현 금지. 텍스트:\n" + (text or "")[:3000]
    )
    result = call_claude(prompt, max_tokens=1500, as_json=True)
    if isinstance(result, list):
        cleaned = []
        for r in result:
            if not isinstance(r, dict):
                continue
            cleaned.append({
                "section": r.get("section"),
                "register_date": r.get("register_date"),
                "right_type": r.get("right_type"),
                "holder": r.get("holder"),
                "amount": r.get("amount"),
                "raw_text": json.dumps(r, ensure_ascii=False)[:200],
            })
        if cleaned:
            return _finalize(cleaned)
    log.info("[legal] AI 파싱 결과 비정상 -> 정규식으로 대체")
    return _parse_with_regex(text)


def _generate_mock(item_id: int) -> list[dict]:
    """item_id 기반 결정적 mock 권리 시계열 (3~7건)."""
    rng = random.Random(item_id * 7919 + 13)
    n = rng.randint(3, 7)
    start = date(rng.randint(2008, 2016), rng.randint(1, 12), rng.randint(1, 28))

    # 첫 권리는 소유권이전(갑구)
    rights: list[dict] = [{
        "section": "갑구",
        "register_date": start.isoformat(),
        "right_type": "소유권이전",
        "holder": f"소유자{rng.randint(1, 9)}",
        "amount": None,
        "raw_text": "(mock) 소유권이전",
    }]

    pool = ["근저당권", "가압류", "압류", "전세권", "임차권", "가처분", "지상권"]
    cur = start
    for _ in range(n - 2):
        cur = cur + timedelta(days=rng.randint(120, 900))
        rt = rng.choice(pool)
        amt = None
        if rt in ("근저당권", "전세권", "임차권", "가압류"):
            amt = rng.randint(3, 28) * 10_000_000
        rights.append({
            "section": RIGHT_TYPE_PATTERNS.get(rt, "을구"),
            "register_date": cur.isoformat(),
            "right_type": rt,
            "holder": f"권리자{rng.randint(1, 99)}",
            "amount": amt,
            "raw_text": f"(mock) {rt}",
        })

    # 마지막은 경매개시결정
    cur = cur + timedelta(days=rng.randint(60, 400))
    rights.append({
        "section": "갑구",
        "register_date": cur.isoformat(),
        "right_type": "경매개시결정",
        "holder": "법원",
        "amount": None,
        "raw_text": "(mock) 임의경매개시결정",
    })
    return _finalize(rights)


def _finalize(rights: list[dict]) -> list[dict]:
    """등기일자 오름차순 정렬 + seq 부여. 날짜 없는 항목은 뒤로."""
    def _key(r: dict):
        return (r.get("register_date") is None, r.get("register_date") or "")

    rights = sorted(rights, key=_key)
    for i, r in enumerate(rights, start=1):
        r["seq"] = i
        r.setdefault("amount", None)
        r.setdefault("holder", None)
    return rights


def parse_rights(text: str, item_id: int) -> list[dict]:
    """등기부 텍스트 -> 권리 시계열 리스트. 텍스트 없으면 mock 생성."""
    if not text or not text.strip():
        return _generate_mock(item_id)

    use_ai = config.USE_AI and not config.USE_MOCK_APIS and bool(config.ANTHROPIC_API_KEY)
    if use_ai:
        rights = _parse_with_ai(text)
    else:
        rights = _parse_with_regex(text)

    # 파싱 실패 시 안전하게 mock fallback
    if not rights:
        log.info(f"[legal] item_id={item_id} 파싱 결과 없음 -> mock 생성")
        return _generate_mock(item_id)
    return rights


def save_rights_timeline(item_id: int, rights: list[dict]) -> int:
    """권리 시계열을 rights_timeline 테이블에 저장(기존 행 교체)."""
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM rights_timeline WHERE item_id=?", (item_id,))
    for r in rights:
        c.execute("""
            INSERT INTO rights_timeline
                (item_id, seq, section, register_date, right_type, holder, amount,
                 is_senior, is_extinguished, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id, r.get("seq"), r.get("section"), r.get("register_date"),
            r.get("right_type"), r.get("holder"), r.get("amount"),
            int(r.get("is_senior", 0) or 0), int(r.get("is_extinguished", 0) or 0),
            r.get("raw_text"),
        ))
    conn.commit()
    conn.close()
    log.info(f"[legal] item_id={item_id} -> 권리 {len(rights)}건 저장")
    return len(rights)


def get_rights_timeline(item_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM rights_timeline WHERE item_id=? ORDER BY seq", (item_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
