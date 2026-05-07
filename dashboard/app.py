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

# 부트스트랩 (st.secrets -> env 복사 + DB 비어있으면 자동 시드)
from dashboard.bootstrap import bootstrap as _bootstrap  # noqa: E402
_BOOTSTRAP = _bootstrap()

from dashboard.charts import (
    alert_timeline_chart,
    backtest_timeline,
    backtest_winrate_timeline,
    channel_distribution_pie,
    grade_profit_bar,
    grade_winrate_chart,
    pipeline_timeline_chart,
    pred_vs_actual_scatter,
    trend_line_chart,
    trend_with_reference,
)
from agents.pdf_report_agent import generate_item_report_pdf, generate_top_picks_pdf
from agents.action_planner_agent import list_today_actions
from agents.alert_agent import (
    collect_pending_alerts,
    dispatch_alerts,
    list_recent_alerts,
)
from agents.monitoring_agent import (
    alert_summary as ma_alert_summary,
    alert_timeline_series,
    db_health,
    detect_anomalies,
    get_pipeline_history,
    get_stress_history,
    pipeline_timeline_series,
)
from agents.backtest_agent import (
    backtest_all_items,
    fetch_pred_actual_pairs,
    grade_ordering_check,
    history_chart_series,
    list_backtest_runs,
    save_backtest_run,
)
from agents.bidding_agent import format_bid_report, get_bid_recommendation
from agents.compare_agent import (
    annotate_best_worst,
    collect_compare_data,
    summarize_compare,
)
from agents.watchlist_agent import (
    bulk_set_watch,
    list_watched_items,
    toggle_watch as wl_toggle_watch,
    watch_summary,
)
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
    if _BOOTSTRAP.get("seeded"):
        st.success("자동 시드 완료 (mock 80건)")
    elif _BOOTSTRAP.get("hydrated"):
        st.caption(f"환경변수 {_BOOTSTRAP['hydrated']}개 secrets 에서 로드")
    tab_sel = st.radio(
        "메뉴",
        [
            "오늘의 브리핑",
            "오늘 할 일",
            "오늘의 추천 TOP 5",
            "전체 물건",
            "AI 에이전트 검색",
            "물건 상세분석",
            "물건 비교",
            "워치리스트",
            "수익 계산기",
            "위험 키워드",
            "신뢰도/데이터 부족",
            "시세 트렌드",
            "변화 감지",
            "사용자 선호 설정",
            "알림",
            "백테스트",
            "스트레스 테스트 결과",
            "운영 모니터링",
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
        st.session_state["top5_results"] = res

    res = st.session_state.get("top5_results")
    if res:
        st.success(f"총 {res['total_found']}건 중 상위 {len(res['results'])}건")
        for i, r in enumerate(res["results"], 1):
            it = r["item"]
            st.markdown(
                f"**{i}. [{r['grade']}] {it.get('address_full', '미상')}**\n"
                f"- 차익 {r['profit_estimate']:,}만원 / ROI {r['roi_estimate']:.1f}%\n"
                f"- 위험 {r['risk_level']} {risk_emoji(r['risk_level'])} / 점수 {r['score']:.1f}\n"
                f"- 매각기일 {it.get('bid_date', '미정')}"
            )
        # 묶음 PDF 다운로드
        ids = [r["item"]["id"] for r in res["results"]]
        if ids:
            try:
                pdf_bytes = generate_top_picks_pdf(ids)
                st.download_button(
                    label=f"TOP {len(ids)} 묶음 PDF 다운로드",
                    data=pdf_bytes,
                    file_name=f"report_top_{len(ids)}.pdf",
                    mime="application/pdf",
                )
            except Exception as e:
                st.error(f"PDF 생성 실패: {e}")

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

        # 시세 트렌드 차트 (plotly)
        st.markdown("### 시세 트렌드")
        trades = get_trade_history(it["id"])
        monthly = monthly_aggregate(trades)
        pa = get_price_analysis(it["id"]) or {}
        if monthly:
            st.plotly_chart(trend_line_chart(monthly, title="월별 평균/최저/최고 + 거래수"),
                              use_container_width=True)
            st.plotly_chart(trend_with_reference(monthly, {
                "감정가": it.get("appraisal_price", 0),
                "최저가": it.get("min_bid_price", 0),
                "추정 시세": pa.get("market_price_estimate", 0),
            }, title="기준선과 월평균 비교"), use_container_width=True)
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

        st.markdown("### PDF 리포트")
        try:
            pdf_bytes = generate_item_report_pdf(it["id"])
            st.download_button(
                label="이 매물 PDF 리포트 다운로드",
                data=pdf_bytes,
                file_name=f"report_item_{it['id']}.pdf",
                mime="application/pdf",
                key=f"pdf_dl_{it['id']}",
            )
            st.caption(f"PDF 크기: {len(pdf_bytes):,} bytes")
        except Exception as e:
            st.error(f"PDF 생성 실패: {e}")

# 7. 물건 비교 -----------------------------------------------------
elif tab_sel == "물건 비교":
    st.header("물건 비교")
    st.caption("2~5개 매물을 나란히 비교해서 어느 매물이 어떤 면에서 더 좋은지 한눈에 확인합니다.")

    items = _get_items(500)
    if not items:
        st.info("물건이 없습니다. mock 데이터를 먼저 생성하세요.")
    else:
        labels = {it["id"]: f"#{it['id']} {it.get('address_full', '')[:40]}" for it in items}
        selected_ids = st.multiselect(
            "매물 선택 (2~5개)",
            options=list(labels.keys()),
            default=list(labels.keys())[:3] if len(labels) >= 3 else list(labels.keys())[:2],
            format_func=lambda i: labels[i],
            max_selections=5,
        )
        if len(selected_ids) < 2:
            st.warning("2개 이상 선택해 주세요.")
        else:
            data = collect_compare_data(selected_ids)
            best_worst = annotate_best_worst(data)
            summary = summarize_compare(data)

            # 종합 요약
            st.subheader("종합 요약")
            c1, c2, c3 = st.columns(3)
            bs = summary.get("best_score", {})
            bp = summary.get("best_profit", {})
            lr = summary.get("lowest_risk", {})
            c1.metric("종합 점수 1위", f"#{bs.get('id', '-')} ({bs.get('grade', '-')})",
                       delta=f"{bs.get('score', 0):.1f}점")
            c2.metric("예상 차익 1위", f"#{bp.get('id', '-')}",
                       delta=f"{bp.get('profit', 0):,}만원")
            c3.metric("최저 위험", f"#{lr.get('id', '-')}",
                       delta=f"severity {lr.get('max_severity', 0)}")

            # 카드 뷰
            st.subheader("개별 매물 카드")
            cols = st.columns(len(data))
            for i, d in enumerate(data):
                with cols[i]:
                    grade = d.get("grade") or "?"
                    color = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "X": "⚫"}.get(grade, "⬜")
                    st.markdown(f"**{color} #{d['id']} [{grade}]**")
                    st.caption(d.get("address_full", "")[:40])
                    st.metric("종합 점수", f"{(d.get('score') or 0):.1f}")
                    st.metric("예상 차익", f"{(d.get('profit_estimate') or 0):,}만")
                    st.metric("ROI", f"{(d.get('roi_estimate') or 0):.1f}%")
                    st.caption(
                        f"위험 {d.get('risk_level', '-')} / "
                        f"신뢰도 {(d.get('overall_conf_num') or 0):.2f}"
                    )
                    if d.get("appraisal_inflated"):
                        st.error("감정가 거품 의심")
                    if d.get("is_watched"):
                        st.info("관심 등록됨")
                    bd = d.get("bid_days_left")
                    if bd is not None and bd >= 0:
                        if bd <= 3:
                            st.warning(f"입찰기일 D-{bd}")
                        else:
                            st.caption(f"매각기일 {d.get('bid_date')} (D-{bd})")

            # 비교 테이블
            st.subheader("비교 테이블")
            st.caption("✅ 이 비교에서 가장 좋은 값 / ❌ 가장 나쁜 값")
            sections = [
                ("기본 정보", [
                    ("주소", "address_full"),
                    ("종류", "item_type"),
                    ("면적(㎡)", "area_m2"),
                    ("층", "floor"),
                    ("매각기일", "bid_date"),
                    ("D-N (남은 일)", "bid_days_left"),
                    ("유찰", "fail_count"),
                ]),
                ("가격", [
                    ("감정가", "appraisal_price"),
                    ("최저가", "min_bid_price"),
                    ("추정 시세", "market_price_estimate"),
                    ("최저가/시세", "minimum_to_market_ratio"),
                    ("감정가/시세", "appraisal_to_market_ratio"),
                    ("거래 표본", "transaction_count"),
                    ("시세 신뢰도", "price_confidence"),
                ]),
                ("위험", [
                    ("등급", "risk_level"),
                    ("키워드 수", "risk_flag_count"),
                    ("최고 severity", "max_severity"),
                    ("주요 키워드", "top_flags"),
                ]),
                ("신뢰도 (0~1)", [
                    ("시세", "price_conf_num"),
                    ("권리", "legal_conf_num"),
                    ("문서", "doc_conf_num"),
                    ("주소", "addr_conf_num"),
                    ("종합", "overall_conf_num"),
                ]),
                ("예상 손익", [
                    ("예상 차익", "profit_estimate"),
                    ("예상 ROI(%)", "roi_estimate"),
                    ("총 비용", "total_cost"),
                    ("보수 입찰가", "bid_conservative"),
                    ("기준 입찰가", "bid_standard"),
                    ("공격 입찰가", "bid_aggressive"),
                ]),
                ("추천 / 액션", [
                    ("종합 점수", "score"),
                    ("등급", "grade"),
                    ("오늘 액션 수", "action_count"),
                    ("추가 확인사항 수", "checklist_count"),
                ]),
            ]
            id_labels = [f"#{d['id']}" for d in data]
            for section_name, fields in sections:
                st.markdown(f"**{section_name}**")
                rows = []
                for label, key in fields:
                    row = {"항목": label}
                    bw = best_worst.get(key, {})
                    for d, hdr in zip(data, id_labels):
                        val = d.get(key)
                        if isinstance(val, list):
                            display = ", ".join(str(x) for x in val) or "-"
                        elif isinstance(val, float):
                            display = f"{val:.3f}" if val < 10 else f"{val:,.0f}"
                        elif isinstance(val, int):
                            display = f"{val:,}"
                        elif val is None:
                            display = "-"
                        else:
                            display = str(val)
                        mark = bw.get(d["id"])
                        if mark == "best":
                            display = f"✅ {display}"
                        elif mark == "worst":
                            display = f"❌ {display}"
                        row[hdr] = display
                    rows.append(row)
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# 8. 워치리스트 ----------------------------------------------------
elif tab_sel == "워치리스트":
    st.header("워치리스트")
    st.caption("관심 등록한 매물만 모아 보고 일괄 관리합니다.")

    summary = watch_summary()
    if summary["count"] == 0:
        st.info(
            "관심 등록된 매물이 없습니다. '전체 물건' 또는 '오늘의 추천 TOP 5' "
            "탭에서 매물을 클릭한 후 ☆ 관심 등록 버튼을 누르세요."
        )

        # 관심 등록 빠른 추가
        st.subheader("빠른 관심 등록")
        items_all = _get_items(500)
        labels = {it["id"]: f"#{it['id']} {it.get('address_full', '')[:40]}" for it in items_all}
        if labels:
            picks = st.multiselect("매물 선택", options=list(labels.keys()),
                                    format_func=lambda i: labels[i], max_selections=20)
            if picks and st.button("선택 매물 관심 등록"):
                n = bulk_set_watch(picks, watched=True)
                st.success(f"{n}건 관심 등록 완료")
                st.rerun()
    else:
        # 요약 메트릭
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 매물 수", summary["count"])
        c2.metric("총 예상 차익", f"{int(summary['total_profit_estimate']):+,}만")
        c3.metric("입찰기일 임박", summary["imminent_count"], delta="D-7 이내")
        c4.metric("열린 액션", summary["open_actions_total"])

        # 등급 분포
        if summary["by_grade"]:
            st.caption(
                "등급 분포: " +
                " / ".join(f"{g} {n}" for g, n in summary["by_grade"].items())
            )
        warns = []
        if summary["high_risk_count"]:
            warns.append(f"고위험 매물 {summary['high_risk_count']}건")
        if summary["inflated_count"]:
            warns.append(f"감정가 거품 의심 {summary['inflated_count']}건")
        if warns:
            st.warning(" / ".join(warns))

        items = list_watched_items()
        st.subheader(f"관심 매물 ({len(items)}건)")

        # 컨트롤
        sort_by = st.selectbox(
            "정렬",
            ["입찰기일 임박순", "예상 차익 높은순", "점수 높은순", "위험 낮은순", "최근 변경순"],
        )
        sort_key = {
            "입찰기일 임박순": lambda it: it.get("bid_days_left") or 9999,
            "예상 차익 높은순": lambda it: -(it.get("profit_estimate") or 0),
            "점수 높은순": lambda it: -(it.get("score") or 0),
            "위험 낮은순": lambda it: it.get("max_severity") or 0,
            "최근 변경순": lambda it: -(it.get("recent_changes_7d") or 0),
        }[sort_by]
        items_sorted = sorted(items, key=sort_key)

        # 일괄 처리 컨트롤
        with st.expander("일괄 처리"):
            ids_for_bulk = [it["id"] for it in items_sorted]
            select_all = st.checkbox("전체 선택")
            default_picks = ids_for_bulk if select_all else []
            picked = st.multiselect(
                "대상 매물",
                options=ids_for_bulk,
                default=default_picks,
                format_func=lambda i: next(
                    f"#{i} {x.get('address_full', '')[:35]}"
                    for x in items_sorted if x["id"] == i
                ),
            )
            cb1, cb2, cb3 = st.columns(3)
            with cb1:
                if st.button("선택 매물 관심 해제", type="secondary"):
                    if picked:
                        n = bulk_set_watch(picked, watched=False)
                        st.success(f"{n}건 관심 해제")
                        st.rerun()
                    else:
                        st.warning("선택된 매물이 없습니다")
            with cb2:
                if st.button("선택 매물 알림 발송"):
                    if picked:
                        from agents.alert_agent import dispatch_alerts
                        # only_watched 모드로 발송
                        from agents.preference_learning_agent import get_preferences
                        pref = get_preferences()
                        pref_force = {**pref, "alert_only_watched": True}
                        res = dispatch_alerts(pref=pref_force, dry_run=False)
                        st.success(f"발송 {res['sent']} / 스킵 {res['skipped']}건")
                    else:
                        st.warning("선택된 매물이 없습니다")
            with cb3:
                if st.button("선택 매물 비교 화면으로"):
                    if 2 <= len(picked) <= 5:
                        st.session_state["compare_ids"] = picked
                        st.info("'물건 비교' 탭으로 이동하세요. 선택이 자동 적용됩니다.")
                    else:
                        st.warning("2~5개 선택해야 비교 가능합니다")

        # 매물 카드
        for it in items_sorted:
            grade = it.get("grade") or "?"
            color = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "X": "⚫"}.get(grade, "⬜")
            bd = it.get("bid_days_left")
            badges = []
            if bd is not None and 0 <= bd <= 3:
                badges.append(f"D-{bd} 임박")
            if it.get("appraisal_inflated"):
                badges.append("감정가 거품")
            if it.get("recent_changes_7d", 0) > 0:
                badges.append(f"7일 내 {it['recent_changes_7d']}건 변경")
            if it.get("open_actions", 0) > 0:
                badges.append(f"열린 액션 {it['open_actions']}건")
            badge_str = " · ".join(f"`{b}`" for b in badges) if badges else ""
            with st.expander(
                f"{color} [{grade}] #{it['id']} {it.get('address_full', '')} "
                f"| 차익 {int(it.get('profit_estimate') or 0):+,}만 | "
                f"점수 {(it.get('score') or 0):.1f}"
            ):
                if badge_str:
                    st.markdown(badge_str)
                cc1, cc2, cc3, cc4 = st.columns(4)
                cc1.metric("감정가", f"{it.get('appraisal_price', 0):,}만")
                cc2.metric("최저가", f"{it.get('min_bid_price', 0):,}만")
                cc3.metric("추정 시세", f"{it.get('market_price', 0):,}만")
                cc4.metric("ROI", f"{(it.get('roi_estimate') or 0):.1f}%")
                st.caption(
                    f"위험 {it.get('risk_level', '-')} (severity {it.get('max_severity', 0)}) | "
                    f"키워드 {it.get('flag_count', 0)}개 | 거래 {it.get('transaction_count', 0)}건 | "
                    f"매각기일 {it.get('bid_date', '미정')} (D-{bd if bd is not None else '?'})"
                )
                ac1, ac2, ac3 = st.columns(3)
                with ac1:
                    if st.button("관심 해제", key=f"unwatch_{it['id']}"):
                        wl_toggle_watch(it["id"], False)
                        st.rerun()
                with ac2:
                    if st.button("입찰가 시뮬", key=f"bidrec_{it['id']}"):
                        rec = get_bid_recommendation(it["id"])
                        st.text(format_bid_report(rec))
                with ac3:
                    if st.button("Q&A 열기", key=f"qa_{it['id']}"):
                        ans = ask(it["id"], "이 물건 위험한가? 추가로 확인할 사항은?")
                        st.write(ans["answer"])

# 9. 수익 계산기 ---------------------------------------------------
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
                st.plotly_chart(
                    trend_line_chart(trend, title=f"{si} {gu} {itype} 월별 시세"),
                    use_container_width=True,
                )

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
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("감정가", f"{it.get('appraisal_price', 0):,}만원")
                c2.metric("최저가", f"{it.get('min_bid_price', 0):,}만원")
                c3.metric("추정 시세", f"{pa.get('market_price_estimate', 0):,}만원")
                c4.metric("매칭 거래수", len(trades))
                st.plotly_chart(trend_with_reference(monthly, {
                    "감정가": it.get("appraisal_price", 0),
                    "최저가": it.get("min_bid_price", 0),
                    "추정 시세": pa.get("market_price_estimate", 0),
                }, title="기준선과 월평균 비교 (감정가/최저가가 시세보다 위에 있으면 거품 의심)"),
                use_container_width=True)
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
    available_channels = ["telegram", "slack", "discord", "email"]
    current_channels = pref.get("alert_channels") or [pref.get("alert_channel", "telegram")]
    alert_channels = st.multiselect(
        "알림 채널 (다중 선택)",
        available_channels,
        default=[c for c in current_channels if c in available_channels] or ["telegram"],
        help="선택한 모든 채널로 동시 발송. 키 미설정 채널은 자동 콘솔 fallback.",
    )
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
            "alert_channel": alert_channels[0] if alert_channels else "telegram",
            "alert_channels": alert_channels or ["telegram"],
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

# 13. 백테스트 ------------------------------------------------------
elif tab_sel == "백테스트":
    st.header("추천 정확도 백테스트")
    st.caption("등급별 적중률 / 평균 수익 / 예측 오차. mock 환경에서는 outcome_simulations이 '실제'를 대신합니다.")

    scenario = st.selectbox("시나리오", ["standard", "conservative", "aggressive"], index=0)
    if st.button("백테스트 실행", type="primary"):
        with st.spinner("전체 매물 평가 중..."):
            report = backtest_all_items(scenario=scenario)
        ordering = grade_ordering_check(report)
        run_id = save_backtest_run(report, ordering)
        st.session_state["bt_report"] = report
        st.session_state["bt_ordering"] = ordering
        st.session_state["bt_scenario"] = scenario
        st.success(f"실행 완료 - run #{run_id} 시계열에 저장됨")

    report = st.session_state.get("bt_report")
    ordering = st.session_state.get("bt_ordering")
    if not report:
        st.info("'백테스트 실행' 버튼을 눌러 결과를 생성하세요.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("매칭 쌍", report["total_pairs"])
        if report.get("overall"):
            c2.metric("전체 승률", f"{report['overall']['win_rate']}%")
            c3.metric("평균 실제 손익",
                       f"{int(report['overall']['actual_profit']['mean']):+,}만원")

        st.subheader("등급별 통계")
        rows = []
        for g in ["A", "B", "C", "D", "X"]:
            s = report["grades"].get(g)
            if not s or s["count"] == 0:
                continue
            rows.append({
                "등급": g,
                "건수": s["count"],
                "승률(%)": s["win_rate"],
                "평균 실제 손익(만원)": int(s["actual_profit"]["mean"]),
                "중앙값 실제 손익": int(s["actual_profit"]["median"]),
                "평균 예측 손익": int(s["pred_profit"]["mean"]),
                "평균 절대 오차": int(s["abs_error"]["mean"]),
                "상대 오차(%)": round(s["relative_error_pct"]["mean"], 1),
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            # 등급별 평균 손익 + 승률 (plotly)
            c1, c2 = st.columns([3, 2])
            with c1:
                st.plotly_chart(grade_profit_bar(report["grades"]),
                                  use_container_width=True)
            with c2:
                st.plotly_chart(grade_winrate_chart(report["grades"]),
                                  use_container_width=True)

        if ordering:
            st.subheader("등급 순서 검증")
            ok = ordering["monotonic_decreasing"]
            st.write(f"단조 감소: {'OK - 등급별 평균 손익이 A->B->C->D 순으로 떨어집니다' if ok else 'FAIL - 등급별 평균 손익이 단조 감소하지 않음 (B등급이 A보다 클 수 있음 - 표본 크기 차이)'}")
            st.json(ordering["grade_means"])

        st.subheader("예측 vs 실제 산점도")
        pairs = fetch_pred_actual_pairs(scenario=st.session_state["bt_scenario"], limit=500)
        if pairs:
            st.plotly_chart(pred_vs_actual_scatter(pairs),
                              use_container_width=True)
            st.caption("점선 대각선이 완벽 예측 (y=x). 등급별 색상으로 구분. 손익 0선과 교차하는 사분면으로 winning/losing 구분.")
        else:
            st.info("recommendation_results 가 충분히 쌓여야 산점도가 그려집니다.")

    # 시계열 추적 (백테스트 실행 여부와 무관하게 표시)
    st.divider()
    st.subheader("백테스트 시계열 추적")
    st.caption("'백테스트 실행' 버튼을 누를 때마다 결과가 누적됩니다. 알고리즘 튜닝 효과를 시간순으로 확인할 수 있습니다.")
    history_scenario = st.selectbox("시계열 시나리오 필터",
                                     ["standard", "conservative", "aggressive"],
                                     index=0, key="history_scenario")
    history = history_chart_series(limit=50, scenario=history_scenario, mode="all_items")
    if not history:
        st.info(f"{history_scenario} 시나리오의 백테스트 기록 없음. 위 버튼으로 실행하세요.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("기록 수", len(history))
        if len(history) >= 2:
            first_mean = history[0]["overall_mean_profit"]
            last_mean = history[-1]["overall_mean_profit"]
            delta = last_mean - first_mean
            c2.metric("평균 손익 변화",
                       f"{int(last_mean):+,}만원",
                       delta=f"{int(delta):+,}만원 (첫 기록 대비)")
            first_wr = history[0]["overall_win_rate"]
            last_wr = history[-1]["overall_win_rate"]
            c3.metric("승률 변화", f"{last_wr}%",
                       delta=f"{last_wr - first_wr:+.1f}%p")
        st.plotly_chart(backtest_timeline(history), use_container_width=True)
        st.plotly_chart(backtest_winrate_timeline(history),
                          use_container_width=True)
        with st.expander("기록 표 보기"):
            runs = list_backtest_runs(limit=50, scenario=history_scenario, mode="all_items")
            if runs:
                df = pd.DataFrame(runs)
                cols = [c for c in ["id", "run_date", "scenario", "mode",
                                     "total_pairs", "overall_win_rate",
                                     "overall_mean_profit", "monotonic_decreasing",
                                     "a_mean", "b_mean", "c_mean",
                                     "d_mean", "x_mean"] if c in df.columns]
                st.dataframe(df[cols], use_container_width=True)

# 14. 스트레스 테스트 결과 -----------------------------------------
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
elif tab_sel == "운영 모니터링":
    st.header("운영 모니터링")
    st.caption("파이프라인 / 알림 / 스트레스 테스트 / DB 상태를 한 화면에서 확인합니다.")

    # 이상 감지 배너
    issues = detect_anomalies()
    if issues:
        for it in issues:
            if it["severity"] == "warning":
                st.warning(f"[!] {it['message']}")
            else:
                st.info(f"{it['message']}")
    else:
        st.success("최근 운영 데이터에서 이상 징후가 감지되지 않았습니다.")

    # 메트릭 카드
    health = db_health()
    pipelines = get_pipeline_history(50)
    alerts_summary = ma_alert_summary(limit=1000)
    stress = get_stress_history(20)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 매물", health["tables"].get("items", 0))
    c2.metric("파이프라인 누적", len(pipelines))
    c3.metric("알림 누적", alerts_summary["total"])
    c4.metric("DB 크기", f"{health['db_size_kb']:.0f} KB")

    # 파이프라인 시계열
    st.subheader("파이프라인 실행 추이")
    series_p = pipeline_timeline_series(30)
    if series_p:
        st.plotly_chart(pipeline_timeline_chart(series_p),
                          use_container_width=True)
    else:
        st.info("파이프라인 실행 기록 없음. `python scripts/run_daily_pipeline.py` 실행")

    # 알림 통계 (시계열 + 채널 분포)
    st.subheader("알림 발송 통계")
    cc1, cc2 = st.columns([3, 2])
    with cc1:
        timeline = alert_timeline_series(200)
        st.plotly_chart(alert_timeline_chart(timeline),
                          use_container_width=True)
    with cc2:
        st.plotly_chart(channel_distribution_pie(alerts_summary["by_channel"]),
                          use_container_width=True)

    # 알림 상세 통계 표
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        st.markdown("**채널별**")
        if alerts_summary["by_channel"]:
            df = pd.DataFrame(
                [{"채널": k, "건수": v} for k, v in alerts_summary["by_channel"].items()]
            ).sort_values("건수", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("기록 없음")
    with sc2:
        st.markdown("**상태별**")
        if alerts_summary["by_status"]:
            df = pd.DataFrame(
                [{"상태": k, "건수": v} for k, v in alerts_summary["by_status"].items()]
            ).sort_values("건수", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("기록 없음")
    with sc3:
        st.markdown("**유형별**")
        if alerts_summary["by_type"]:
            df = pd.DataFrame(
                [{"유형": k, "건수": v} for k, v in alerts_summary["by_type"].items()]
            ).sort_values("건수", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("기록 없음")

    # 최근 파이프라인 실행 표
    st.subheader("최근 파이프라인 실행")
    if pipelines:
        df_p = pd.DataFrame(pipelines)
        cols = [c for c in ["id", "run_type", "status", "total_items",
                            "elapsed_sec", "started_at", "finished_at"]
                if c in df_p.columns]
        st.dataframe(df_p[cols].head(15), use_container_width=True,
                       hide_index=True)
    else:
        st.caption("기록 없음")

    # 최근 스트레스 테스트
    st.subheader("최근 스트레스 테스트")
    if stress:
        df_s = pd.DataFrame(stress)
        cols = [c for c in ["id", "scenario", "item_count", "query_count",
                            "elapsed_sec", "success", "created_at"]
                if c in df_s.columns]
        st.dataframe(df_s[cols], use_container_width=True, hide_index=True)
    else:
        st.caption("기록 없음. `python scripts/run_stress_test.py --count 1000 --queries 20`")

    # DB 헬스 - 테이블별 행수
    st.subheader("DB 상태")
    cc1, cc2 = st.columns([2, 1])
    with cc1:
        df_t = pd.DataFrame(
            sorted(
                ({"테이블": k, "행수": v} for k, v in health["tables"].items()),
                key=lambda x: -x["행수"],
            )
        )
        st.dataframe(df_t, use_container_width=True, hide_index=True)
    with cc2:
        st.metric("총 테이블", health["table_count"])
        st.metric("총 행수", f"{health['total_rows']:,}")
        st.caption(f"DB 경로: `{health['db_path']}`")

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
