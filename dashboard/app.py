"""
dashboard/app.py
Streamlit 대시보드 - 13개 탭.
실행: streamlit run dashboard/app.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import json
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agents.action_planner_agent import list_today_actions
from agents.alert_agent import (
    collect_pending_alerts,
    dispatch_alerts,
    list_recent_alerts,
)
from agents.bidding_agent import format_bid_report, get_bid_recommendation
from agents.change_detection_agent import list_recent_events
from agents.confidence_agent import get_confidence
from agents.daily_briefing_agent import generate_briefing, get_latest_briefing
from agents.item_qa_agent import ask
from agents.preference_learning_agent import (
    DEFAULT_PREF,
    get_preferences,
    save_preferences,
)
from agents.recommendation_agent import recommend
from agents.report_agent import build_item_report, render_markdown
from core.config import runtime_summary
from core.database import get_connection, init_db
from core.utils import days_until, risk_emoji
from modules.profit_calculator import calc_profit, recommend_bid_prices
from modules.risk.keyword_analyzer import RISK_KEYWORDS, get_risk_flags
from modules.valuation.price_matcher import (
    get_price_analysis,
    get_region_trend,
    get_trade_history,
    monthly_aggregate,
)

init_db()
st.set_page_config(page_title="경매·공매 AI 에이전트", layout="wide")

SOURCE_LABELS = {"auction": "경매", "public_sale": "공매"}


def _get_items(limit: int = 500) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM items WHERE status='active' "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


with st.sidebar:
    st.title("경매·공매 AI 에이전트")
    rt = runtime_summary()
    st.caption(f"Mode: {'MOCK' if rt['use_mock_apis'] else 'REAL'} / "
               f"AI: {'on' if rt['use_ai'] else 'off'}")
    tab_sel = st.radio(
        "메뉴",
        [
            "오늘의 브리핑",
            "오늘 할 일",
            "오늘의 추천 TOP 5",
            "전체 물건",
            "AI 에이전트 검색",
            "물건 상세분석",
            "수익 계산기",
            "위험 키워드",
            "신뢰도/데이터 부족",
            "시세 트렌드",
            "변화 감지",
            "사용자 선호 설정",
            "알림",
            "스트레스 테스트 결과",
            "도움말",
        ],
    )
    st.divider()
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM items WHERE status='active'").fetchone()[0]
    today_cnt = conn.execute(
        "SELECT COUNT(*) FROM items WHERE date(created_at)=date('now','localtime')"
    ).fetchone()[0]
    conn.close()
    st.metric("전체 물건", total)
    st.metric("오늘 신규", today_cnt)


# 1. 오늘의 브리핑 ---------------------------------------------------
if tab_sel == "오늘의 브리핑":
    st.header("오늘의 브리핑")
    if st.button("브리핑 새로 생성"):
        with st.spinner("브리핑 생성 중..."):
            generate_briefing()
        st.success("완료")
    b = get_latest_briefing()
    if not b:
        st.info("아직 브리핑이 없습니다. 위 버튼을 눌러 생성하세요.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 분석 물건", b["total_items"])
        c2.metric("실거래가 매칭", b["matched_items"])
        c3.metric("검토 후보", b["candidate_items"])
        c4.metric("고위험 후보", b["high_risk_items"])
        st.markdown("### 요약")
        st.write(b["summary"])
        st.markdown("### 오늘 우선 볼 물건 (검토 후보 A/B/C)")
        try:
            picks = json.loads(b["top_picks_json"] or "[]")
        except Exception:
            picks = []
        try:
            delta = json.loads(b["delta_json"] or "{}")
        except Exception:
            delta = {}
        if not picks:
            st.warning("검토 후보(A/B/C 등급)가 없습니다 - 추천 후보 부족")
        else:
            for i, r in enumerate(picks, 1):
                it = r.get("item", {})
                st.write(
                    f"{i}. [{r.get('grade')}] {it.get('address_full', '')} | "
                    f"차익 {r.get('profit_estimate', 0):,}만원 | "
                    f"점수 {r.get('score', 0):.1f}"
                )

        try:
            warning_picks = json.loads(b["warning_picks_json"] or "[]")
        except Exception:
            warning_picks = []
        if warning_picks:
            st.markdown("### 주의 후보 (D/X 등급 - 검토 보류 권장)")
            for i, r in enumerate(warning_picks, 1):
                it = r.get("item", {})
                cr = (r.get("score_breakdown") or {}).get("critical_reasons") or []
                reason = cr[0] if cr else "낮은 점수"
                st.write(
                    f"{i}. [{r.get('grade')}] {it.get('address_full', '')} | "
                    f"차익 {r.get('profit_estimate', 0):,}만원 | "
                    f"사유: {reason}"
                )

# 2. 오늘 할 일 ----------------------------------------------------
elif tab_sel == "오늘 할 일":
    st.header("오늘 할 일")
    actions = list_today_actions()
    if not actions:
        st.info("오늘 추가된 액션이 없습니다. 파이프라인을 실행하면 자동 생성됩니다.")
    else:
        df = pd.DataFrame(actions)
        cols = [c for c in ["priority", "action_type", "title", "address_full",
                            "detail", "due_date", "status"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True)

# 3. 오늘의 추천 TOP 5 ----------------------------------------------
elif tab_sel == "오늘의 추천 TOP 5":
    st.header("오늘의 추천 TOP 5")
    q = st.text_input("쿼리", value="시세차익 큰 물건 5개 찾아줘")
    if st.button("추천 실행", type="primary"):
        with st.spinner("분석 중..."):
            res = recommend(q)
        st.success(f"총 {res['total_found']}건 중 상위 {len(res['results'])}건")
        for i, r in enumerate(res["results"], 1):
            it = r["item"]
            st.markdown(
                f"**{i}. [{r['grade']}] {it.get('address_full', '미상')}**\n"
                f"- 차익 {r['profit_estimate']:,}만원 / ROI {r['roi_estimate']:.1f}%\n"
                f"- 위험 {r['risk_level']} {risk_emoji(r['risk_level'])} / 점수 {r['score']:.1f}\n"
                f"- 매각기일 {it.get('bid_date', '미정')}"
            )

# 4. 전체 물건 -----------------------------------------------------
elif tab_sel == "전체 물건":
    st.header("전체 물건")
    items = _get_items(1000)
    if not items:
        st.info("물건이 없습니다. `python scripts/generate_mock_data.py --count 100` 실행")
    else:
        df = pd.DataFrame(items)
        cols = [c for c in ["id", "source", "item_type", "address_full",
                            "appraisal_price", "min_bid_price", "fail_count",
                            "bid_date"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True)

# 5. AI 에이전트 검색 ----------------------------------------------
elif tab_sel == "AI 에이전트 검색":
    st.header("AI 에이전트 검색")
    examples = [
        "시세차익 가장 큰 물건 5개만 찾아줘",
        "공매만 보고 수익률 높은 물건 10개",
        "서울 아파트 중 위험 낮은 물건 3개",
        "유치권 있는 물건은 제외해줘",
        "요즘 괜찮은 거 있어?",
    ]
    cols = st.columns(len(examples))
    for i, ex in enumerate(examples):
        if cols[i].button(ex, key=f"ex_{i}"):
            st.session_state["agent_query"] = ex
    q = st.text_input("자연어 입력", value=st.session_state.get("agent_query", examples[0]))
    if st.button("실행", type="primary"):
        with st.spinner("에이전트가 분석 중..."):
            res = recommend(q)
        st.success(f"총 {res['total_found']}건 중 상위 {len(res['results'])}건")
        with st.expander("파싱된 의도 보기"):
            st.json(res["intent"])
        for i, r in enumerate(res["results"], 1):
            it = r["item"]
            with st.container():
                st.markdown(
                    f"### {i}. [{r['grade']}] {it.get('address_full', '미상')}"
                )
                c1, c2, c3 = st.columns(3)
                c1.metric("예상 시세차익(만원)", f"{r['profit_estimate']:,}")
                c2.metric("예상 ROI(%)", f"{r['roi_estimate']:.1f}")
                c3.metric("종합 점수", f"{r['score']:.1f}")
                st.caption(
                    f"위험 {r['risk_level']} {risk_emoji(r['risk_level'])} | "
                    f"신뢰도 {(r['confidence'].get('overall_confidence') or 0):.2f} | "
                    f"매각기일 {it.get('bid_date', '미정')}"
                )
                with st.expander("추천 리포트 보기"):
                    rep = build_item_report(r)
                    st.markdown(render_markdown(rep))

# 6. 물건 상세분석 -------------------------------------------------
elif tab_sel == "물건 상세분석":
    st.header("물건 상세분석")
    items = _get_items(500)
    if not items:
        st.info("물건이 없습니다.")
    else:
        labels = [f"#{it['id']} {it.get('address_full', '')[:30]}" for it in items]
        idx = st.selectbox("물건 선택", range(len(items)), format_func=lambda i: labels[i])
        it = items[idx]
        st.write(f"**{it.get('address_full')}**")
        c1, c2, c3 = st.columns(3)
        c1.metric("감정가(만원)", f"{it.get('appraisal_price', 0):,}")
        c2.metric("최저가(만원)", f"{it.get('min_bid_price', 0):,}")
        c3.metric("유찰", f"{it.get('fail_count', 0)}회")
        flags = get_risk_flags(it["id"])
        st.markdown("### 위험 키워드")
        if flags:
            st.dataframe(pd.DataFrame(flags)[
                ["flag_type", "risk_level", "severity", "description", "source_text"]
            ], use_container_width=True)
        else:
            st.info("위험 키워드 없음")
        st.markdown("### 입찰가 추천")
        bid = get_bid_recommendation(it["id"])
        st.text(format_bid_report(bid))

        # 시세 트렌드 차트
        st.markdown("### 시세 트렌드")
        trades = get_trade_history(it["id"])
        monthly = monthly_aggregate(trades)
        pa = get_price_analysis(it["id"]) or {}
        if monthly:
            df_m = pd.DataFrame(monthly).set_index("ym")
            chart_df = df_m[["avg_price", "min_price", "max_price"]].rename(
                columns={"avg_price": "평균", "min_price": "최저", "max_price": "최고"}
            )
            st.line_chart(chart_df, height=280)
            ref_lines = pd.DataFrame({
                "감정가": [it.get("appraisal_price", 0)] * len(df_m),
                "최저가": [it.get("min_bid_price", 0)] * len(df_m),
                "추정 시세": [pa.get("market_price_estimate", 0)] * len(df_m),
                "월평균": df_m["avg_price"].values,
            }, index=df_m.index)
            st.caption("기준선과 월평균 비교")
            st.line_chart(ref_lines, height=240)
            st.caption(f"매칭된 거래 {len(trades)}건 / 월별 {len(monthly)}개월")
            with st.expander("개별 거래 보기"):
                st.dataframe(pd.DataFrame(trades), use_container_width=True)
        else:
            st.info("매칭된 실거래 데이터가 없습니다.")

        st.markdown("### 물건 Q&A")
        question = st.text_input("질문하기", value="이 물건 위험해?")
        if st.button("질문하기 실행"):
            ans = ask(it["id"], question)
            st.write(ans["answer"])

# 7. 수익 계산기 ---------------------------------------------------
elif tab_sel == "수익 계산기":
    st.header("수익 계산기")
    c1, c2 = st.columns(2)
    with c1:
        market = st.number_input("시세 (만원)", value=80000, step=1000)
        bid = st.number_input("입찰가 (만원)", value=60000, step=1000)
        item_type = st.selectbox("물건 종류", ["아파트", "오피스텔", "빌라", "상가", "토지"])
    with c2:
        repair = st.number_input("수리비", value=500, step=100)
        eviction = st.number_input("명도비", value=300, step=100)
        target_roi = st.slider("목표 ROI(%)", 5, 30, 10)
    if st.button("계산", type="primary"):
        info = calc_profit(market, bid, item_type, repair, eviction)
        bids = recommend_bid_prices(market, item_type, target_roi)
        c1, c2, c3 = st.columns(3)
        c1.metric("예상 차익", f"{info['profit']:,}만원", delta=f"ROI {info['roi']:.1f}%")
        c2.metric("총 투자금", f"{info['invested']:,}만원")
        c3.metric("부대비용", f"{info['total_cost']:,}만원")
        df = pd.DataFrame([
            {"구분": v["label"], "입찰가(만원)": v["price"],
             "예상차익(만원)": v["profit"], "ROI(%)": f"{v['roi']:.1f}"}
            for v in bids.values() if isinstance(v, dict)
        ])
        st.dataframe(df, use_container_width=True)

# 8. 위험 키워드 ---------------------------------------------------
elif tab_sel == "위험 키워드":
    st.header("위험 키워드 사전")
    rows = []
    for k, info in RISK_KEYWORDS.items():
        rows.append({
            "type": k, "level": info["level"], "severity": info["severity"],
            "keywords": ", ".join(info["keywords"]),
            "description": info["description"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

# 9. 신뢰도/데이터 부족 ---------------------------------------------
elif tab_sel == "신뢰도/데이터 부족":
    st.header("신뢰도 / 데이터 부족 물건")
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT c.*, i.address_full, i.item_type
        FROM confidence_scores c LEFT JOIN items i ON i.id=c.item_id
        ORDER BY c.overall_confidence ASC LIMIT 100
        """
    ).fetchall()
    conn.close()
    if not rows:
        st.info("아직 신뢰도가 계산되지 않았습니다. 파이프라인을 실행하세요.")
    else:
        df = pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df[
            ["item_id", "address_full", "item_type", "price_confidence",
             "legal_risk_confidence", "document_confidence",
             "address_match_confidence", "overall_confidence", "reasons_json"]
        ], use_container_width=True)

# 10. 시세 트렌드 ---------------------------------------------------
elif tab_sel == "시세 트렌드":
    st.header("시세 트렌드 차트")
    st.caption("지역(시/구) + 물건 유형 단위 월별 평균 시세 / 단지(특정 매물) 단위 시세")

    mode = st.radio("보기 단위", ["지역+유형", "특정 매물(단지)"], horizontal=True)

    if mode == "지역+유형":
        conn = get_connection()
        rows = conn.execute("""
            SELECT DISTINCT i.address_si, i.address_gu, i.item_type
            FROM items i JOIN price_records p ON p.item_id=i.id
            WHERE i.address_si IS NOT NULL AND i.address_gu IS NOT NULL
              AND i.item_type IS NOT NULL
            ORDER BY i.address_si, i.address_gu, i.item_type
        """).fetchall()
        conn.close()
        opts = [(r["address_si"], r["address_gu"], r["item_type"]) for r in rows]
        if not opts:
            st.info("실거래 데이터가 없습니다. mock 데이터 생성 후 파이프라인을 실행하세요.")
        else:
            labels = [f"{a} {b} / {c}" for a, b, c in opts]
            idx = st.selectbox("지역 + 유형 선택", range(len(opts)),
                                format_func=lambda i: labels[i])
            si, gu, itype = opts[idx]
            months = st.slider("기간 (월)", 3, 24, 12)
            trend = get_region_trend(si, gu, itype, months=months)
            if not trend:
                st.info("해당 조건에 맞는 거래가 없습니다.")
            else:
                df = pd.DataFrame(trend).set_index("ym")
                c1, c2, c3 = st.columns(3)
                latest = df["avg_price"].iloc[-1]
                first = df["avg_price"].iloc[0]
                delta_pct = ((latest - first) / first * 100) if first else 0
                c1.metric("최근 월 평균", f"{int(latest):,}만원",
                           delta=f"{delta_pct:+.1f}% (기간 시작 대비)")
                c2.metric("기간 거래수", int(df["count"].sum()))
                c3.metric("기간 표본 월수", len(df))
                chart_df = df[["avg_price", "min_price", "max_price"]].rename(
                    columns={"avg_price": "평균", "min_price": "최저", "max_price": "최고"}
                )
                st.line_chart(chart_df, height=320)
                st.caption("월별 거래 건수")
                st.bar_chart(df[["count"]].rename(columns={"count": "거래수"}), height=180)

    else:
        items = _get_items(500)
        if not items:
            st.info("물건이 없습니다.")
        else:
            labels = [f"#{it['id']} {it.get('address_full', '')[:40]}" for it in items]
            idx = st.selectbox("매물 선택", range(len(items)),
                                format_func=lambda i: labels[i])
            it = items[idx]
            trades = get_trade_history(it["id"])
            monthly = monthly_aggregate(trades)
            pa = get_price_analysis(it["id"]) or {}
            if not monthly:
                st.info("이 매물에 매칭된 실거래가가 없습니다.")
            else:
                df = pd.DataFrame(monthly).set_index("ym")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("감정가", f"{it.get('appraisal_price', 0):,}만원")
                c2.metric("최저가", f"{it.get('min_bid_price', 0):,}만원")
                c3.metric("추정 시세", f"{pa.get('market_price_estimate', 0):,}만원")
                c4.metric("매칭 거래수", len(trades))
                ref_df = pd.DataFrame({
                    "월평균": df["avg_price"].values,
                    "감정가": [it.get("appraisal_price", 0)] * len(df),
                    "최저가": [it.get("min_bid_price", 0)] * len(df),
                    "추정 시세": [pa.get("market_price_estimate", 0)] * len(df),
                }, index=df.index)
                st.line_chart(ref_df, height=320)
                st.caption("기준선과 월평균 비교 (감정가/최저가가 시세보다 위에 있으면 거품 의심)")
                with st.expander("개별 거래 보기"):
                    st.dataframe(pd.DataFrame(trades), use_container_width=True)

# 11. 변화 감지 ----------------------------------------------------
elif tab_sel == "변화 감지":
    st.header("변화 감지 이벤트")
    events = list_recent_events()
    if not events:
        st.info("최근 변경 이벤트가 없습니다.")
    else:
        st.dataframe(pd.DataFrame(events), use_container_width=True)

# 11. 사용자 선호 설정 ---------------------------------------------
elif tab_sel == "사용자 선호 설정":
    st.header("사용자 선호 설정")
    pref = get_preferences()

    st.subheader("추천 필터")
    regions = st.text_input("선호 지역 (쉼표)", ",".join(pref.get("regions", [])))
    types = st.text_input("선호 유형 (쉼표)", ",".join(pref.get("item_types", [])))
    max_risk = st.selectbox(
        "최대 허용 위험 등급", ["low", "medium", "high"],
        index=["low", "medium", "high"].index(pref.get("max_risk_level", "medium"))
    )
    min_profit = st.number_input("최소 기대수익(만원)", value=int(pref.get("min_profit_man", 3000)))
    min_roi = st.number_input("최소 ROI", value=float(pref.get("min_roi", 0.05)))
    excludes = st.text_input("제외 키워드 (쉼표)", ",".join(pref.get("exclude_keywords", [])))

    st.divider()
    st.subheader("알림 설정")
    alerts_enabled = st.checkbox("알림 활성화", value=pref.get("alerts_enabled", True))
    alert_min_grade = st.selectbox(
        "최소 알림 등급", ["A", "B", "C"],
        index=["A", "B", "C"].index(pref.get("alert_min_grade", "B")),
    )
    alert_imminent_days = st.slider("입찰기일 임박 알림 (D-N 이내)", 1, 14,
                                     int(pref.get("alert_imminent_days", 3)))
    alert_only_watched = st.checkbox("관심 매물만 알림",
                                      value=pref.get("alert_only_watched", False))
    alert_include_briefing = st.checkbox("일일 브리핑도 알림에 포함",
                                          value=pref.get("alert_include_briefing", True))

    if st.button("저장", type="primary"):
        save_preferences({
            "regions": [s.strip() for s in regions.split(",") if s.strip()],
            "item_types": [s.strip() for s in types.split(",") if s.strip()],
            "max_risk_level": max_risk,
            "min_profit_man": int(min_profit),
            "min_roi": float(min_roi),
            "exclude_keywords": [s.strip() for s in excludes.split(",") if s.strip()],
            "notes": "수동 설정",
            "alerts_enabled": alerts_enabled,
            "alert_channel": pref.get("alert_channel", "telegram"),
            "alert_min_grade": alert_min_grade,
            "alert_imminent_days": alert_imminent_days,
            "alert_only_watched": alert_only_watched,
            "alert_include_briefing": alert_include_briefing,
        })
        st.success("저장됨")

# 12. 알림 ---------------------------------------------------------
elif tab_sel == "알림":
    st.header("알림")
    pref = get_preferences()

    if not pref.get("alerts_enabled", True):
        st.warning("알림이 비활성화 상태입니다. '사용자 선호 설정' 탭에서 다시 켤 수 있습니다.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("최소 등급", pref.get("alert_min_grade", "B"))
        c2.metric("D-N 이내", f"{pref.get('alert_imminent_days', 3)}일")
        c3.metric("관심만", "예" if pref.get("alert_only_watched") else "아니오")
        c4.metric("브리핑 포함", "예" if pref.get("alert_include_briefing", True) else "아니오")

    st.subheader("발송 대기 중 알림 (preview)")
    pending = collect_pending_alerts(pref)
    if not pending:
        st.info("발송 대기 중인 알림 없음 (모두 발송 완료 또는 조건 미충족).")
    else:
        df = pd.DataFrame([{
            "유형": a["alert_type"], "우선": a["priority"],
            "제목": a["title"], "본문": a["body"][:80] + "...",
        } for a in pending])
        st.dataframe(df, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("미리보기 (dry-run)"):
            res = dispatch_alerts(pref, dry_run=True)
            st.json(res)
    with col_b:
        if st.button("지금 발송", type="primary"):
            with st.spinner("발송 중..."):
                res = dispatch_alerts(pref, dry_run=False)
            st.success(f"발송 {res['sent']}건 / 스킵 {res['skipped']}건 / 실패 {res['failed']}건")
            st.json(res)

    st.divider()
    st.subheader("최근 알림 로그")
    logs = list_recent_alerts(50)
    if not logs:
        st.info("알림 로그 없음")
    else:
        df = pd.DataFrame(logs)
        cols = [c for c in ["id", "alert_type", "priority", "title", "channel",
                            "status", "sent_at", "created_at", "error_message"]
                if c in df.columns]
        st.dataframe(df[cols], use_container_width=True)

# 13. 스트레스 테스트 결과 -----------------------------------------
elif tab_sel == "스트레스 테스트 결과":
    st.header("스트레스 테스트 결과")
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM stress_test_results ORDER BY id DESC LIMIT 30"
    ).fetchall()
    conn.close()
    if not rows:
        st.info("결과 없음. `python scripts/run_stress_test.py --count 1000 --queries 20` 로 생성")
    else:
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)

# 13. 도움말 -------------------------------------------------------
elif tab_sel == "도움말":
    st.header("도움말")
    st.markdown("""
- 본 프로그램은 **mock-first** 모드로 동작합니다 (실제 API 키가 없어도 모든 기능이 돌아갑니다).
- 실제 API 연결을 원하면 `.env` 의 `USE_MOCK_APIS=false`, 그리고 각 키를 입력하세요.
- 권리분석 결과는 **위험요소 체크리스트**일 뿐 법률 판단이 아닙니다.
- 투자 권유가 아니므로 최종 판단은 본인이 별도 검토하세요.

**자주 쓰는 명령**
```bash
python scripts/generate_mock_data.py --count 100 --seed 42
python scripts/run_daily_pipeline.py --mock --count 100 --top 5
python scripts/run_stress_test.py --count 1000 --queries 20
streamlit run dashboard/app.py
pytest tests/
```
""")
