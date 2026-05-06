"""
agents/item_qa_agent.py
물건별 Q&A. 컨텍스트(아이템 + 분석 결과)를 모아 AI 또는 mock에 질의.
"""
from __future__ import annotations

from typing import Any

from agents.confidence_agent import get_confidence
from core.ai_client import item_qa as ai_item_qa
from core.database import get_connection
from modules.documents.mock_documents import get_item_documents
from modules.risk.keyword_analyzer import get_risk_flags
from modules.valuation.price_matcher import get_price_analysis


def _build_context(item_id: int) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not row:
        return {}
    item = dict(row)
    pa = get_price_analysis(item_id) or {}
    flags = get_risk_flags(item_id)
    conf = get_confidence(item_id) or {}
    docs = get_item_documents(item_id)
    item.update({
        "price_analysis": pa,
        "risk_flags_summary": [
            {"type": f["flag_type"], "level": f["risk_level"]} for f in flags
        ],
        "risk_score": max((f["severity"] for f in flags), default=0),
        "confidence": conf,
        "documents": [
            {"type": d["doc_type"], "is_disclosed": bool(d["is_disclosed"])}
            for d in docs
        ],
    })
    return item


def ask(item_id: int, question: str) -> dict:
    ctx = _build_context(item_id)
    if not ctx:
        return {"error": f"item_id={item_id} 없음"}
    answer = ai_item_qa(question, ctx)
    return {
        "item_id": item_id,
        "question": question,
        "answer": answer,
        "context_summary": {
            "address": ctx.get("address_full"),
            "risk_score": ctx.get("risk_score"),
            "confidence": ctx.get("confidence", {}).get("overall_confidence"),
        },
        "disclaimer": "참고용 답변이며, 법률·투자 판단은 직접 검토하세요.",
    }
