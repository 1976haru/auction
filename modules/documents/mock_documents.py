"""
modules/documents/mock_documents.py
경매·공매 문서를 mock 텍스트로 생성한다.
일부 케이스는 미공개로 처리해 신뢰도 저하 시뮬.
"""
from __future__ import annotations

import random
from typing import Any

from core.database import get_connection, init_db
from core.logger import log

DOC_TYPES = [
    "매각물건명세서",
    "현황조사서",
    "감정평가서",
    "공매재산명세",
    "공고문",
]

CASES = [
    {
        "name": "소유자 점유",
        "text": "본 물건의 점유자는 소유자 본인으로 확인됩니다. 특이사항 없음.",
        "tags": ["소유자 점유"],
    },
    {
        "name": "임차인 있음",
        "text": "본 물건에는 임차인이 거주중이며 전입세대 1세대 확인됩니다. 보증금과 확정일자, 대항력 확인이 필요합니다.",
        "tags": ["임차인", "전입세대", "대항력"],
    },
    {
        "name": "점유자 미상",
        "text": "현황조사 시 점유자 확인 불가. 점유자 미상으로 표시. 명도 협의가 필요할 수 있습니다.",
        "tags": ["점유자 미상", "명도"],
    },
    {
        "name": "유치권 신고",
        "text": "유치권자 A씨로부터 공사대금 채권 8,000만원 유치권 신고가 있었습니다. 유치권 성립 여부 확인 필요.",
        "tags": ["유치권", "공사대금"],
    },
    {
        "name": "법정지상권 가능성",
        "text": "토지와 건물 소유자가 다를 가능성이 있어 법정지상권 성립 여부 확인이 필요합니다.",
        "tags": ["법정지상권"],
    },
    {
        "name": "지분매각",
        "text": "본 물건은 공유지분 1/2 매각 건입니다. 공유자우선매수권 행사 여부 확인 필요.",
        "tags": ["지분매각", "공유지분"],
    },
    {
        "name": "관리비 체납",
        "text": "관리사무소 확인 결과 관리비 체납 약 280만원 존재. 인수 여부 확인 필요.",
        "tags": ["관리비 체납"],
    },
    {
        "name": "선순위임차인 가능성",
        "text": "전입세대 등본상 선순위 임차인이 존재할 가능성. 대항력 있는 임차인의 보증금 인수 여부 확인 필요.",
        "tags": ["선순위임차인", "대항력"],
    },
    {
        "name": "농지취득자격증명 필요",
        "text": "지목이 답으로 되어 있어 농지취득자격증명이 필요합니다. 현황 확인 후 발급 가능 여부 검토 필요.",
        "tags": ["농지취득자격증명"],
    },
    {
        "name": "특이사항 없음",
        "text": "조사 사항 중 특이사항이 발견되지 않았습니다. 일반적인 경매 절차로 진행됩니다.",
        "tags": ["특이사항 없음"],
    },
    {
        "name": "분묘기지권 가능성",
        "text": "토지 일부에 분묘가 존재합니다. 분묘기지권 성립 여부 확인이 필요합니다.",
        "tags": ["분묘기지권"],
    },
    {
        "name": "위반건축물",
        "text": "건축물대장상 위반건축물로 등재되어 있습니다. 시정명령 이행 여부 확인 필요.",
        "tags": ["위반건축물"],
    },
]


def _pick_case(rnd: random.Random, idx: int) -> dict:
    # idx 기반으로 약 8% 미공개, 30% 위험 케이스
    if rnd.random() < 0.08:
        return {"name": "문서 미공개", "text": "", "tags": [], "is_disclosed": False}
    return rnd.choice(CASES) | {"is_disclosed": True}


def generate_documents_for_item(item_id: int, item: dict, seed: int | None = None) -> list[dict]:
    """item에 대해 1~3개 문서 mock 생성."""
    rnd = random.Random(seed if seed is not None else item_id)
    generated = []
    n = rnd.randint(1, 3)
    for i in range(n):
        case = _pick_case(rnd, i)
        doc_type = rnd.choice(DOC_TYPES)
        text = case["text"]
        if text:
            text = (
                f"[{doc_type}] {item.get('address_full', '')}\n"
                f"감정가: {item.get('appraisal_price', 0):,}만원\n"
                f"최저가: {item.get('min_bid_price', 0):,}만원\n"
                f"---\n{text}"
            )
        generated.append({
            "doc_type": doc_type,
            "is_disclosed": case.get("is_disclosed", True),
            "extracted_text": text,
            "case_name": case.get("name", ""),
        })
    return generated


def save_documents(item_id: int, docs: list[dict]) -> int:
    init_db()
    conn = get_connection()
    c = conn.cursor()
    for d in docs:
        c.execute("""
            INSERT INTO documents
                (item_id, doc_type, file_url, file_path, is_disclosed, extracted_text, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id, d["doc_type"], None, None,
            1 if d.get("is_disclosed", True) else 0,
            d.get("extracted_text") or None,
            d.get("case_name") or None,
        ))
    conn.commit()
    conn.close()
    return len(docs)


def get_item_documents(item_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM documents WHERE item_id=? ORDER BY id", (item_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def populate_documents(seed: int | None = 42) -> int:
    """DB에 있는 모든 item에 mock 문서를 생성·저장한다."""
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM items").fetchall()
    conn.close()

    rnd = random.Random(seed)
    total = 0
    for r in rows:
        item = dict(r)
        existing = get_item_documents(item["id"])
        if existing:
            continue
        s = rnd.randint(0, 10**9)
        docs = generate_documents_for_item(item["id"], item, seed=s)
        total += save_documents(item["id"], docs)
    log.info(f"[mock-docs] 문서 {total}건 생성")
    return total
