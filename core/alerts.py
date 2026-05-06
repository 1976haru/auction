"""
core/alerts.py
하위 호환을 위한 알림 모듈. 실제 발송은 modules/alerts/telegram.py에 위임.
"""
from __future__ import annotations

from modules.alerts.telegram import send_message, format_top_picks


def format_item_alert(item: dict, profit: int, roi: float, risk_score: int) -> str:
    source_label = "[경매]" if item.get("source") == "auction" else "[공매]"
    risk = "low" if risk_score <= 3 else "med" if risk_score <= 6 else "high"
    return (
        f"{source_label} {item.get('address_full', '미상')[:40]}\n"
        f"감정가 {item.get('appraisal_price', 0):,}만원 | 최저가 {item.get('min_bid_price', 0):,}만원\n"
        f"예상차익 {profit:,}만원 | 수익률 {roi:.1f}% | 위험 {risk}({risk_score}/10)\n"
        f"매각기일: {item.get('bid_date', '미정')}"
    )


def send_daily_report(recommendations: list[dict]) -> bool:
    return send_message(format_top_picks(recommendations))
