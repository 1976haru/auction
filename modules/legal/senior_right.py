"""
modules/legal/senior_right.py
말소기준권리 자동 식별.

말소기준권리 = (근)저당권 / 가압류 / 압류 / 담보가등기 / 경매개시결정등기 / 전세권 중
등기일자가 가장 빠른 것. 말소기준권리와 그 이후 권리는 말소 예상, 이전 권리는 인수 검토 대상.
(실제 인수 여부는 개별 사안에 따라 다르므로 확인 필요)
"""
from __future__ import annotations

from core.database import get_connection, init_db
from core.logger import log
from modules.legal.rights_parser import get_rights_timeline

# 말소기준이 될 수 있는 권리 유형
SENIOR_RIGHT_TYPES = (
    "근저당권", "저당권", "가압류", "압류",
    "담보가등기", "경매개시결정", "전세권",
)


def _is_senior_candidate(right_type: str | None) -> bool:
    if not right_type:
        return False
    return any(t in right_type for t in SENIOR_RIGHT_TYPES)


def identify_senior_right(item_id: int) -> dict | None:
    """말소기준권리를 식별하고 rights_timeline에 is_senior/is_extinguished 표시.

    Returns: 말소기준권리 dict 또는 None(후보 없음).
    """
    timeline = get_rights_timeline(item_id)
    if not timeline:
        return None

    candidates = [
        r for r in timeline
        if _is_senior_candidate(r.get("right_type")) and r.get("register_date")
    ]
    if not candidates:
        log.info(f"[legal] item_id={item_id} 말소기준권리 후보 없음")
        return None

    candidates.sort(key=lambda r: (r.get("register_date") or "", r.get("seq") or 0))
    senior = candidates[0]
    senior_date = senior.get("register_date")
    senior_seq = senior.get("seq")

    init_db()
    conn = get_connection()
    c = conn.cursor()
    # 초기화
    c.execute("UPDATE rights_timeline SET is_senior=0 WHERE item_id=?", (item_id,))
    c.execute(
        "UPDATE rights_timeline SET is_senior=1 WHERE item_id=? AND seq=?",
        (item_id, senior_seq),
    )
    # 말소 예상: 말소기준권리 및 그 이후 등기일자 권리
    c.execute(
        """UPDATE rights_timeline
           SET is_extinguished = CASE
               WHEN register_date IS NOT NULL AND register_date >= ? THEN 1
               ELSE 0 END
           WHERE item_id=?""",
        (senior_date, item_id),
    )
    conn.commit()
    conn.close()

    senior["is_senior"] = 1
    log.info(
        f"[legal] item_id={item_id} 말소기준권리 -> "
        f"{senior.get('right_type')} ({senior_date})"
    )
    return senior


def get_senior_right(item_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM rights_timeline WHERE item_id=? AND is_senior=1 LIMIT 1",
        (item_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
