"""
agents/pdf_report_agent.py
매물별 상세 리포트 PDF 생성기.

- reportlab Platypus 로 구조화된 PDF 작성
- 한글 폰트는 HYSMyeongJo-Medium (reportlab 내장 Adobe CID font, 한국어 지원)
  -> 별도 ttf 파일 없이 동작. 모던 PDF 리더는 이 폰트를 자동 fallback 처리.
- generate_item_report_pdf(item_id) -> bytes
- generate_top_picks_pdf(picks) -> bytes (TOP 5 묶음)

Streamlit Cloud 의 ephemeral fs 에서도 동작하도록 메모리(BytesIO)에서 직접 생성.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agents.bidding_agent import get_bid_recommendation
from agents.confidence_agent import get_confidence
from agents.legal_risk_agent import FIELD_CHECK_TEMPLATE
from agents.risk_checklist_agent import build_checklist
from core.database import get_connection, init_db
from core.logger import log
from core.utils import days_until, loads, now_iso
from modules.documents.mock_documents import get_item_documents
from modules.profit_calculator import calc_profit
from modules.risk.keyword_analyzer import get_risk_flags, get_risk_level
from modules.valuation.price_matcher import get_price_analysis


_FONT_REGISTERED = False
_FONT_NAME = "HYSMyeongJo-Medium"


def _register_korean_font() -> str:
    """한글 폰트 등록. 1회만 실행."""
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(_FONT_NAME))
            _FONT_REGISTERED = True
        except Exception as e:
            log.warning(f"[pdf] 한글 폰트 등록 실패, fallback Helvetica: {e}")
            return "Helvetica"
    return _FONT_NAME


def _make_styles(font: str) -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName=font,
                                  fontSize=20, leading=24, alignment=0),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=font,
                              fontSize=14, leading=18, spaceBefore=8, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName=font,
                              fontSize=11, leading=14, spaceBefore=4, spaceAfter=2),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=font,
                                fontSize=9.5, leading=13),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName=font,
                                  fontSize=8, leading=11, textColor=colors.grey),
        "warn": ParagraphStyle("warn", parent=base["BodyText"], fontName=font,
                                 fontSize=9, leading=12, textColor=colors.red),
    }


def _table(data: list[list[str]], col_widths: list[float], font: str) -> Table:
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f4f8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _fetch_item_context(item_id: int) -> dict:
    init_db()
    conn = get_connection()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    rec = conn.execute(
        "SELECT score, grade, score_breakdown FROM recommendation_results "
        "WHERE item_id=? ORDER BY id DESC LIMIT 1", (item_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {}
    item = dict(row)
    pa = get_price_analysis(item_id) or {}
    market = pa.get("market_price_estimate") or int(item.get("appraisal_price", 0) * 0.95)
    pinfo = calc_profit(int(market or 0), int(item.get("min_bid_price", 0) or 0),
                        item.get("item_type", "아파트"))
    flags = get_risk_flags(item_id)
    cl = build_checklist(item_id)
    conf = get_confidence(item_id) or {}
    docs = get_item_documents(item_id)
    bid = get_bid_recommendation(item_id)
    score = rec["score"] if rec else None
    grade = rec["grade"] if rec else None
    breakdown = loads(rec["score_breakdown"], {}) if rec else {}
    return {
        "item": item, "price_analysis": pa, "profit_info": pinfo,
        "market": market, "flags": flags, "checklist": cl,
        "confidence": conf, "documents": docs, "bid": bid,
        "score": score, "grade": grade, "breakdown": breakdown,
        "risk_level": get_risk_level(item_id),
        "bid_days_left": days_until(item.get("bid_date")),
    }


def _build_item_story(ctx: dict, styles: dict, font: str) -> list:
    item = ctx["item"]
    pa = ctx["price_analysis"]
    pinfo = ctx["profit_info"]
    flags = ctx["flags"]
    cl = ctx["checklist"]
    conf = ctx["confidence"]
    bid = ctx["bid"]
    score = ctx.get("score")
    grade = ctx.get("grade") or "?"
    breakdown = ctx.get("breakdown") or {}

    story: list = []

    # 헤더
    story.append(Paragraph(f"매물 상세 리포트 - 등급 {grade}", styles["title"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f"<b>{item.get('address_full', '주소 미상')}</b>", styles["h2"]
    ))
    story.append(Paragraph(
        f"item_id #{item['id']} / {item.get('item_type', '미상')} / "
        f"면적 {item.get('area_m2', '-')}㎡ / {item.get('floor', '-')}층 / "
        f"매각기일 {item.get('bid_date', '미정')}",
        styles["small"],
    ))
    story.append(Spacer(1, 4 * mm))

    # 기본 정보
    story.append(Paragraph("기본 정보", styles["h2"]))
    info_rows = [
        ["항목", "값"],
        ["출처", item.get("source", "-")],
        ["case / mgmt", f"{item.get('case_no') or '-'} / {item.get('mgmt_no') or '-'}"],
        ["감정가(만원)", f"{int(item.get('appraisal_price') or 0):,}"],
        ["최저가(만원)", f"{int(item.get('min_bid_price') or 0):,}"],
        ["유찰", f"{item.get('fail_count', 0)}회"],
        ["매각기일", item.get("bid_date", "미정")],
        ["D-N", str(ctx.get("bid_days_left") or "-")],
        ["관심 등록", "예" if item.get("is_watched") else "아니오"],
    ]
    story.append(_table(info_rows, [40 * mm, 110 * mm], font))
    story.append(Spacer(1, 4 * mm))

    # 가격 분석
    story.append(Paragraph("시세 분석", styles["h2"]))
    price_rows = [
        ["지표", "값"],
        ["6개월 평균(만원)", f"{int(pa.get('avg_price_6m') or 0):,}"],
        ["12개월 평균(만원)", f"{int(pa.get('avg_price_12m') or 0):,}"],
        ["추정 시세(만원)", f"{int(ctx['market']):,}"],
        ["거래량", str(pa.get("transaction_count") or 0)],
        ["최저가/시세 비율", f"{(pa.get('minimum_to_market_ratio') or 0):.2f}"],
        ["감정가/시세 비율", f"{(pa.get('appraisal_to_market_ratio') or 0):.2f}"],
        ["시세 신뢰도", str(pa.get("confidence") or "-")],
        ["거품 의심", "예" if pa.get("appraisal_inflated") else "아니오"],
    ]
    story.append(_table(price_rows, [40 * mm, 110 * mm], font))
    story.append(Spacer(1, 4 * mm))

    # 위험 키워드
    story.append(Paragraph(f"위험 키워드 ({len(flags)}건)", styles["h2"]))
    if flags:
        risk_rows = [["등급", "유형", "설명"]] + [
            [f.get("risk_level", "-"), f.get("flag_type", "-"),
             (f.get("description") or "-")[:60]]
            for f in flags
        ]
        story.append(_table(risk_rows, [22 * mm, 32 * mm, 96 * mm], font))
    else:
        story.append(Paragraph("위험 키워드 미발견 (문서 미공개일 가능성)",
                                styles["body"]))
    story.append(Spacer(1, 4 * mm))

    # 추가 확인사항
    story.append(Paragraph(f"추가 확인사항 ({len(cl)}건)", styles["h2"]))
    if cl:
        for c in cl[:12]:
            story.append(Paragraph(
                f"• [{c.get('priority', 'medium')}] [{c.get('flag_type', '-')}] "
                f"{c.get('item_text', '-')}",
                styles["body"],
            ))
    else:
        story.append(Paragraph("추가 확인사항 없음", styles["body"]))
    story.append(Spacer(1, 4 * mm))

    # 신뢰도
    story.append(Paragraph("신뢰도", styles["h2"]))
    reasons = loads(conf.get("reasons_json"), [])
    conf_rows = [
        ["항목", "값"],
        ["시세 신뢰도", f"{(conf.get('price_confidence') or 0):.2f}"],
        ["권리 신뢰도", f"{(conf.get('legal_risk_confidence') or 0):.2f}"],
        ["문서 완성도", f"{(conf.get('document_confidence') or 0):.2f}"],
        ["주소 매칭", f"{(conf.get('address_match_confidence') or 0):.2f}"],
        ["★ 종합 신뢰도", f"{(conf.get('overall_confidence') or 0):.2f}"],
    ]
    story.append(_table(conf_rows, [40 * mm, 110 * mm], font))
    if reasons:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("사유: " + " / ".join(reasons), styles["small"]))
    story.append(Spacer(1, 4 * mm))

    # 손익 + 입찰가 추천
    story.append(Paragraph("예상 손익 + 입찰가 추천", styles["h2"]))
    profit_rows = [
        ["지표", "값"],
        ["예상 차익(만원)", f"{int(pinfo.get('profit') or 0):+,}"],
        ["예상 ROI(%)", f"{(pinfo.get('roi') or 0):.1f}"],
        ["총 비용(만원)", f"{int(pinfo.get('total_cost') or 0):,}"],
    ]
    story.append(_table(profit_rows, [40 * mm, 110 * mm], font))
    if "bids" in (bid or {}):
        story.append(Spacer(1, 3 * mm))
        bid_rows = [["시나리오", "입찰가(만원)", "예상 차익(만원)", "ROI(%)"]]
        for k, label in [("conservative", "보수"), ("standard", "기준"),
                          ("aggressive", "공격")]:
            b = bid["bids"][k]
            bid_rows.append([
                label,
                f"{int(b.get('price') or 0):,}",
                f"{int(b.get('profit') or 0):+,}",
                f"{(b.get('roi') or 0):.1f}",
            ])
        story.append(_table(bid_rows, [25 * mm, 40 * mm, 45 * mm, 25 * mm], font))
    story.append(Spacer(1, 4 * mm))

    # 점수 분해
    if score is not None:
        story.append(Paragraph(
            f"추천 점수 분해 - {score:.1f}/100 (등급 {grade})", styles["h2"]
        ))
        bd_rows = [["항목", "점수"]]
        for label, key, mx in [
            ("시세차익", "profit_pts", 45),
            ("시세 신뢰도", "price_conf_pts", 15),
            ("위험도", "risk_pts", 20),
            ("입찰기일", "bid_pts", 5),
            ("사용자 선호", "pref_pts", 5),
            ("데이터 완성도", "data_pts", 10),
        ]:
            bd_rows.append([label, f"{(breakdown.get(key) or 0):.1f} / {mx}"])
        story.append(_table(bd_rows, [60 * mm, 90 * mm], font))
        if breakdown.get("critical_reasons"):
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                "제외 사유: " + " / ".join(breakdown["critical_reasons"]),
                styles["warn"],
            ))
    story.append(Spacer(1, 4 * mm))

    # 현장조사 체크리스트
    story.append(Paragraph("현장조사 체크리스트", styles["h2"]))
    for c in FIELD_CHECK_TEMPLATE:
        story.append(Paragraph(f"☐ {c}", styles["body"]))
    story.append(Spacer(1, 4 * mm))

    # 면책
    story.append(Paragraph("면책", styles["h3"]))
    story.append(Paragraph(
        "본 리포트는 mock 또는 실 외부 데이터 기반 자동 분석 결과로 "
        "참고용입니다. 권리분석은 법률 판단이 아닌 위험요소 체크리스트이며, "
        "실제 입찰 전 매각물건명세서, 등기부등본, 현장조사, 전문가 검토를 "
        "반드시 병행하십시오.",
        styles["small"],
    ))
    story.append(Paragraph(
        f"리포트 생성: {now_iso()}",
        styles["small"],
    ))
    return story


def generate_item_report_pdf(item_id: int) -> bytes:
    """단일 매물 상세 리포트 PDF 바이트 반환."""
    ctx = _fetch_item_context(item_id)
    if not ctx:
        raise ValueError(f"item_id={item_id} 없음")
    font = _register_korean_font()
    styles = _make_styles(font)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"매물 리포트 #{item_id}",
        author="auction-agent",
    )
    story = _build_item_story(ctx, styles, font)
    doc.build(story)
    return buf.getvalue()


def generate_top_picks_pdf(item_ids: list[int]) -> bytes:
    """여러 매물 묶음 리포트 (각 매물마다 페이지 break)."""
    if not item_ids:
        raise ValueError("매물 id 가 비어있습니다")
    font = _register_korean_font()
    styles = _make_styles(font)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"오늘의 추천 묶음 ({len(item_ids)}건)",
        author="auction-agent",
    )
    story: list = [
        Paragraph(f"오늘의 추천 묶음 - {len(item_ids)}건", styles["title"]),
        Paragraph(now_iso(), styles["small"]),
        Spacer(1, 6 * mm),
    ]
    for i, iid in enumerate(item_ids):
        ctx = _fetch_item_context(iid)
        if not ctx:
            continue
        if i > 0:
            story.append(PageBreak())
        story.extend(_build_item_story(ctx, styles, font))
    doc.build(story)
    return buf.getvalue()
