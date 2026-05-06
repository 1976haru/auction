"""
agents/risk_checklist_agent.py
위험 키워드별 추가 확인사항(체크리스트) 생성기.
"""
from __future__ import annotations

from typing import Any

from core.database import get_connection, init_db
from core.logger import log
from modules.risk.keyword_analyzer import get_risk_flags

CHECKLISTS: dict[str, list[str]] = {
    "임차인": [
        "전입일자 확인",
        "확정일자 확인",
        "배당요구 여부 확인",
        "말소기준권리와 선후 비교",
        "보증금 인수 가능성 확인",
    ],
    "전입세대": [
        "전입세대열람 발급 후 세대원 확인",
        "보증금/임대차 계약 확인",
    ],
    "선순위임차인": [
        "대항력 발생 시점 확인",
        "보증금 인수 여부 확인",
        "임차권 등기 여부 확인",
    ],
    "대항력": [
        "전입+점유 요건 충족 시점 확인",
        "보증금 인수 가능성 확인",
    ],
    "유치권": [
        "유치권 신고 내용 확인",
        "공사대금 채권 존재 여부 확인",
        "점유 계속성 확인",
        "허위 유치권 가능성 검토",
        "현장 점유 상태 확인",
    ],
    "법정지상권": [
        "토지와 건물 소유관계 확인",
        "건물 존재 시점 확인",
        "등기부등본 확인",
        "현황조사서 확인",
    ],
    "지분매각": [
        "공유자우선매수권 확인",
        "지분비율 확인",
        "점유/사용 가능성 확인",
        "단독 처분 가능성 제한 안내",
    ],
    "공유지분": [
        "공유자우선매수권 확인",
        "지분비율 확인",
    ],
    "농지취득자격증명": [
        "농지취득자격증명 필요 여부 확인",
        "농지 이용계획서 확인",
        "지목 및 실제 이용상태 확인",
    ],
    "분묘기지권": [
        "분묘 위치/규모 확인",
        "분묘 소유자 협의 가능성 확인",
    ],
    "관리비 체납": [
        "관리비 체납 금액 확인",
        "공용부분 체납 인수 범위 확인",
    ],
    "위반건축물": [
        "위반 내용 및 시정명령 이행 여부 확인",
        "철거/이행강제금 부담 확인",
    ],
    "명도": [
        "점유자 명도 협의 가능성 확인",
        "명도 비용/기간 추정",
    ],
    "점유자 미상": [
        "점유자 신원 확인",
        "현장 방문 후 거주자 확인",
    ],
    "대금미납 재매각": [
        "이전 매각 무산 사유 확인",
        "동일 위험요인 재발 가능성 검토",
    ],
}

PUBLIC_SALE_EXTRA = [
    "공매 특수조건 확인 (인도책임/체납조건 등)",
    "온비드 공고문 원문 확인",
    "압류·체납 관련 조건 확인",
]


def build_checklist(item_id: int) -> list[dict]:
    init_db()
    flags = get_risk_flags(item_id)
    items: list[dict] = []
    seen: set[str] = set()
    for f in flags:
        items_list = CHECKLISTS.get(f["flag_type"], [])
        for txt in items_list:
            key = (f["flag_type"], txt)
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "flag_type": f["flag_type"],
                "item_text": txt,
                "priority": "high" if f.get("risk_level") == "high" else "medium",
            })
    # 공매 추가
    conn = get_connection()
    row = conn.execute("SELECT source FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if row and row["source"] == "public_sale":
        for txt in PUBLIC_SALE_EXTRA:
            items.append({"flag_type": "공매", "item_text": txt, "priority": "medium"})
    return items


def save_checklist(item_id: int, items: list[dict]) -> int:
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM risk_checklists WHERE item_id=?", (item_id,))
    for it in items:
        c.execute("""
            INSERT INTO risk_checklists (item_id, flag_type, item_text, priority)
            VALUES (?, ?, ?, ?)
        """, (item_id, it["flag_type"], it["item_text"], it.get("priority", "medium")))
    conn.commit()
    conn.close()
    return len(items)


def generate_for_all() -> int:
    init_db()
    conn = get_connection()
    ids = [r["id"] for r in conn.execute("SELECT id FROM items").fetchall()]
    conn.close()
    total = 0
    for iid in ids:
        cl = build_checklist(iid)
        save_checklist(iid, cl)
        total += len(cl)
    log.info(f"[checklist] {total}건 생성")
    return total


def get_checklist(item_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM risk_checklists WHERE item_id=? ORDER BY id", (item_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
