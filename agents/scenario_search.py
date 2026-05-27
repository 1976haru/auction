"""
agents/scenario_search.py
자연어 검색을 시나리오 필터로 매핑한다.

예) "내 자본으로 살 수 있는 물건", "단타 수익률 20% 이상", "임대수익률 5% 이상",
    "실거주 좋은 곳", "위험 없는 물건", "비과세 가능한 거"
"""
from __future__ import annotations

import re

from core.database import get_connection

_SCENARIO_KO = {
    "short_sale": ["단타", "단기", "되팔", "전매"],
    "rental": ["임대", "월세", "전세", "임대수익"],
    "residence": ["실거주", "거주", "내가 살", "직접 살"],
}


def parse_scenario_query(query: str) -> dict:
    """자연어 -> 시나리오 필터 dict."""
    q = query or ""
    f: dict = {"scenario": None, "min_roi": None, "affordable_only": False,
               "low_risk": False, "tax_exempt": False}

    for scen, kws in _SCENARIO_KO.items():
        if any(k in q for k in kws):
            f["scenario"] = scen
            break

    # ROI/수익률 N% 이상
    m = re.search(r"(\d+(?:\.\d+)?)\s*%?\s*(?:이상|넘는|초과)", q)
    if m and ("수익" in q or "roi" in q.lower() or "%" in q or "이상" in q):
        f["min_roi"] = float(m.group(1))

    if any(k in q for k in ("내 자본", "자본으로", "살 수 있", "매수 가능", "감당")):
        f["affordable_only"] = True
    if any(k in q for k in ("위험 없", "안전", "리스크 낮", "저위험", "위험없")):
        f["low_risk"] = True
    if any(k in q for k in ("비과세", "세금 없", "절세")):
        f["tax_exempt"] = True
        f["scenario"] = f["scenario"] or "residence"

    return f


def search_by_scenario(query: str, profile: dict | None = None, limit: int = 20) -> list[dict]:
    """파싱된 필터로 scenario_results를 조회해 매칭 물건 반환."""
    f = parse_scenario_query(query)

    sql = [
        "SELECT s.item_id, s.scenario, s.annualized_roe, s.score, s.affordable,",
        "       s.capital_needed, i.address_full, i.item_type",
        "FROM scenario_results s JOIN items i ON i.id = s.item_id",
        "WHERE 1=1",
    ]
    params: list = []
    if f["scenario"]:
        sql.append("AND s.scenario = ?")
        params.append(f["scenario"])
    if f["min_roi"] is not None:
        sql.append("AND s.annualized_roe >= ?")
        params.append(f["min_roi"])
    if f["affordable_only"]:
        sql.append("AND s.affordable = 1")
    sql.append("ORDER BY s.score DESC, s.annualized_roe DESC LIMIT ?")
    params.append(limit)

    conn = get_connection()
    rows = conn.execute("\n".join(sql), params).fetchall()
    conn.close()

    results = [dict(r) for r in rows]

    # 저위험 필터(몬테카를로 손실확률) 후처리
    if f["low_risk"]:
        conn = get_connection()
        ok_ids = {r["id"] for r in conn.execute(
            "SELECT id FROM items WHERE loss_probability IS NULL OR loss_probability <= 0.2"
        ).fetchall()}
        conn.close()
        results = [r for r in results if r["item_id"] in ok_ids]

    return {"filter": f, "results": results}
