"""
dashboard/charts.py
Plotly 기반 인터랙티브 차트 헬퍼.

Streamlit native 차트(line_chart/bar_chart) 대비 줌, 툴팁, 시리즈 토글,
다중 축 같은 인터랙션을 제공한다.

각 함수는 plotly.graph_objects.Figure 를 반환하고 dashboard 에서
st.plotly_chart(fig, use_container_width=True) 로 렌더한다.
"""
from __future__ import annotations

from typing import Any

import plotly.express as px
import plotly.graph_objects as go


def _empty_fig(message: str = "데이터 없음") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14))
    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False),
                       height=200)
    return fig


def trend_line_chart(monthly: list[dict], title: str = "월별 시세") -> go.Figure:
    """월별 평균/최저/최고 + 거래수(보조축).

    monthly: [{ym, avg_price, min_price, max_price, count}, ...]
    """
    if not monthly:
        return _empty_fig("거래 데이터 없음")
    ym = [m["ym"] for m in monthly]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ym, y=[m["avg_price"] for m in monthly],
        mode="lines+markers", name="평균가",
        line=dict(width=3),
        hovertemplate="<b>%{x}</b><br>평균: %{y:,}만원<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=ym, y=[m["max_price"] for m in monthly],
        mode="lines", name="최고가",
        line=dict(dash="dot"),
        hovertemplate="<b>%{x}</b><br>최고: %{y:,}만원<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=ym, y=[m["min_price"] for m in monthly],
        mode="lines", name="최저가",
        line=dict(dash="dot"),
        fill="tonexty", fillcolor="rgba(135, 206, 235, 0.15)",
        hovertemplate="<b>%{x}</b><br>최저: %{y:,}만원<extra></extra>",
    ))
    # 거래수 보조축
    fig.add_trace(go.Bar(
        x=ym, y=[m["count"] for m in monthly], name="거래수",
        yaxis="y2", opacity=0.4,
        hovertemplate="<b>%{x}</b><br>거래: %{y}건<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis=dict(title="월"),
        yaxis=dict(title="가격(만원)"),
        yaxis2=dict(title="거래수", overlaying="y", side="right",
                     showgrid=False),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=380,
        margin=dict(t=60, b=40, l=40, r=40),
    )
    return fig


def trend_with_reference(monthly: list[dict], references: dict,
                         title: str = "월별 시세 vs 기준선") -> go.Figure:
    """월평균 라인 + 감정가/최저가/추정 시세 가로선.

    references: {"감정가": int, "최저가": int, "추정 시세": int}
    """
    if not monthly:
        return _empty_fig("거래 데이터 없음")
    ym = [m["ym"] for m in monthly]
    avg = [m["avg_price"] for m in monthly]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ym, y=avg, mode="lines+markers", name="월평균 시세",
        line=dict(width=3, color="#1f77b4"),
        hovertemplate="<b>%{x}</b><br>월평균: %{y:,}만원<extra></extra>",
    ))
    colors = {"감정가": "#d62728", "최저가": "#2ca02c", "추정 시세": "#ff7f0e"}
    for label, value in references.items():
        if not value or value <= 0:
            continue
        fig.add_trace(go.Scatter(
            x=ym, y=[value] * len(ym),
            mode="lines", name=label,
            line=dict(dash="dash", color=colors.get(label, "#888")),
            hovertemplate=f"<b>{label}</b>: %{{y:,}}만원<extra></extra>",
        ))
    fig.update_layout(
        title=title,
        xaxis=dict(title="월"),
        yaxis=dict(title="가격(만원)"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=380,
        margin=dict(t=60, b=40, l=40, r=40),
    )
    return fig


GRADE_COLOR = {
    "A": "#2ca02c", "B": "#1f77b4", "C": "#ff7f0e",
    "D": "#d62728", "X": "#7f7f7f",
}


def grade_profit_bar(grade_stats: dict[str, dict]) -> go.Figure:
    """등급별 평균 손익 막대 차트 (오차 막대 포함)."""
    rows = []
    for g in ["A", "B", "C", "D", "X"]:
        s = grade_stats.get(g)
        if not s or s.get("count", 0) == 0:
            continue
        ap = s["actual_profit"]
        rows.append({
            "grade": g, "mean": ap.get("mean", 0),
            "min": ap.get("min", 0), "max": ap.get("max", 0),
            "count": s["count"], "win_rate": s["win_rate"],
        })
    if not rows:
        return _empty_fig("등급별 통계 없음")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[r["grade"] for r in rows],
        y=[r["mean"] for r in rows],
        marker_color=[GRADE_COLOR[r["grade"]] for r in rows],
        error_y=dict(
            type="data", symmetric=False,
            array=[r["max"] - r["mean"] for r in rows],
            arrayminus=[r["mean"] - r["min"] for r in rows],
        ),
        text=[
            f"{r['count']}건<br>승률 {r['win_rate']}%<br>평균 {int(r['mean']):+,}만"
            for r in rows
        ],
        textposition="auto",
        hovertemplate=(
            "<b>등급 %{x}</b><br>"
            "평균 손익: %{y:,.0f}만원<br>"
            "%{text}<extra></extra>"
        ),
    ))
    fig.update_layout(
        title="등급별 평균 손익 (오차막대 = min/max)",
        xaxis=dict(title="등급"),
        yaxis=dict(title="실제 손익 (만원)"),
        height=380,
        margin=dict(t=60, b=40, l=40, r=40),
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#888")
    return fig


def pred_vs_actual_scatter(pairs: list[dict]) -> go.Figure:
    """예측 vs 실제 손익 산점도. 등급별 색상, 대각선 = 완벽 예측."""
    if not pairs:
        return _empty_fig("매칭된 쌍 없음")
    pred = [p.get("profit_estimate", 0) or 0 for p in pairs]
    actual = [p.get("simulated_profit", 0) or 0 for p in pairs]
    grades = [p.get("grade", "?") for p in pairs]
    addrs = [p.get("address_full") or "-" for p in pairs]

    fig = go.Figure()
    for grade in ["A", "B", "C", "D", "X"]:
        idx = [i for i, g in enumerate(grades) if g == grade]
        if not idx:
            continue
        fig.add_trace(go.Scatter(
            x=[pred[i] for i in idx],
            y=[actual[i] for i in idx],
            mode="markers",
            name=f"{grade} ({len(idx)})",
            marker=dict(size=10, color=GRADE_COLOR[grade], opacity=0.7,
                         line=dict(width=1, color="white")),
            text=[addrs[i] for i in idx],
            hovertemplate=(
                "<b>%{text}</b><br>"
                f"등급: {grade}<br>"
                "예측: %{x:,}만원<br>"
                "실제: %{y:,}만원<extra></extra>"
            ),
        ))

    # 대각선 (완벽 예측)
    if pred and actual:
        lo = min(min(pred), min(actual))
        hi = max(max(pred), max(actual))
        fig.add_trace(go.Scatter(
            x=[lo, hi], y=[lo, hi],
            mode="lines", name="완벽 예측 (y=x)",
            line=dict(dash="dash", color="#444", width=1),
            hoverinfo="skip", showlegend=True,
        ))
    # 손익분기선
    fig.add_hline(y=0, line_dash="dot", line_color="#aaa")
    fig.add_vline(x=0, line_dash="dot", line_color="#aaa")

    fig.update_layout(
        title="예측 vs 실제 손익 산점도",
        xaxis=dict(title="예측 손익 (만원)"),
        yaxis=dict(title="실제 손익 (만원)"),
        height=480,
        margin=dict(t=60, b=40, l=40, r=40),
        legend=dict(title="등급"),
        hovermode="closest",
    )
    return fig


def backtest_timeline(history: list[dict]) -> go.Figure:
    """백테스트 추이: 등급별 평균 손익 + 전체 평균 손익 + 단조감소 마커.

    history: history_chart_series() 결과
    """
    if not history:
        return _empty_fig("백테스트 기록 없음")
    x = [h["run_date"] for h in history]
    fig = go.Figure()
    for grade, color in GRADE_COLOR.items():
        y = [h.get(f"{grade.lower()}_mean", 0) for h in history]
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers",
            name=f"{grade} 평균",
            line=dict(color=color, width=2),
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"등급 {grade}: %{{y:,.0f}}만원<extra></extra>"
            ),
        ))
    # 전체 평균
    fig.add_trace(go.Scatter(
        x=x, y=[h["overall_mean_profit"] for h in history],
        mode="lines+markers", name="전체 평균",
        line=dict(color="#000", width=3, dash="dot"),
        hovertemplate="<b>%{x}</b><br>전체: %{y:,.0f}만원<extra></extra>",
    ))
    # 단조감소 OK / FAIL 마커 (보조)
    ok_x = [h["run_date"] for h in history if h.get("monotonic")]
    fail_x = [h["run_date"] for h in history if not h.get("monotonic")]
    if ok_x:
        fig.add_trace(go.Scatter(
            x=ok_x, y=[0] * len(ok_x), mode="markers",
            name="단조감소 OK",
            marker=dict(symbol="triangle-up", size=12, color="green"),
            hovertemplate="<b>%{x}</b><br>등급 단조감소 OK<extra></extra>",
        ))
    if fail_x:
        fig.add_trace(go.Scatter(
            x=fail_x, y=[0] * len(fail_x), mode="markers",
            name="단조감소 FAIL",
            marker=dict(symbol="x", size=12, color="red"),
            hovertemplate="<b>%{x}</b><br>등급 단조감소 깨짐<extra></extra>",
        ))
    fig.add_hline(y=0, line_dash="dot", line_color="#aaa")
    fig.update_layout(
        title="백테스트 등급별 평균 손익 추이",
        xaxis=dict(title="실행 시각"),
        yaxis=dict(title="평균 실제 손익 (만원)"),
        hovermode="x unified",
        height=420,
        margin=dict(t=60, b=40, l=40, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def backtest_winrate_timeline(history: list[dict]) -> go.Figure:
    """전체 승률 추이."""
    if not history:
        return _empty_fig("백테스트 기록 없음")
    x = [h["run_date"] for h in history]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=[h["overall_win_rate"] for h in history],
        mode="lines+markers", name="전체 승률(%)",
        line=dict(color="#1f77b4", width=3),
        hovertemplate="<b>%{x}</b><br>승률: %{y}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x, y=[h["total_pairs"] for h in history],
        mode="lines+markers", name="표본 수", yaxis="y2",
        line=dict(color="#888", dash="dot"),
        hovertemplate="<b>%{x}</b><br>표본: %{y}건<extra></extra>",
    ))
    fig.update_layout(
        title="전체 승률 + 표본 수 추이",
        xaxis=dict(title="실행 시각"),
        yaxis=dict(title="승률 (%)", range=[0, 110]),
        yaxis2=dict(title="표본 수", overlaying="y", side="right",
                     showgrid=False),
        hovermode="x unified",
        height=320,
        margin=dict(t=60, b=40, l=40, r=40),
    )
    return fig


def pipeline_timeline_chart(series: list[dict]) -> go.Figure:
    """파이프라인 실행 시간 + 처리량 추이.

    series: [{created_at, elapsed_sec, total_items, status}, ...] (오래된 순)
    """
    if not series:
        return _empty_fig("파이프라인 기록 없음")
    x = [s["created_at"] for s in series]
    elapsed = [s["elapsed_sec"] for s in series]
    items = [s["total_items"] for s in series]
    status = [s["status"] for s in series]
    colors = ["#2ca02c" if s == "ok" else "#d62728" for s in status]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=elapsed, name="소요(s)",
        marker_color=colors,
        hovertemplate="<b>%{x}</b><br>소요: %{y:.1f}s<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x, y=items, name="처리 매물 수", yaxis="y2",
        mode="lines+markers", line=dict(color="#1f77b4", width=2),
        hovertemplate="<b>%{x}</b><br>매물: %{y}건<extra></extra>",
    ))
    fig.update_layout(
        title="파이프라인 실행 시간 + 처리량 추이",
        xaxis=dict(title="실행 시각"),
        yaxis=dict(title="소요 시간 (초)"),
        yaxis2=dict(title="처리 매물 수", overlaying="y", side="right",
                     showgrid=False),
        height=320,
        margin=dict(t=60, b=40, l=40, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                     xanchor="right", x=1),
    )
    return fig


def alert_timeline_chart(series: list[dict]) -> go.Figure:
    """일자별 sent/failed 스택 막대."""
    if not series:
        return _empty_fig("알림 기록 없음")
    days = [s["day"] for s in series]
    sent = [s["sent"] or 0 for s in series]
    failed = [s["failed"] or 0 for s in series]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=days, y=sent, name="sent",
                          marker_color="#2ca02c"))
    fig.add_trace(go.Bar(x=days, y=failed, name="failed",
                          marker_color="#d62728"))
    fig.update_layout(
        title="일자별 알림 발송 (sent / failed)",
        barmode="stack",
        xaxis=dict(title="일자"),
        yaxis=dict(title="건수"),
        height=320,
        margin=dict(t=60, b=40, l=40, r=40),
    )
    return fig


def channel_distribution_pie(by_channel: dict[str, int]) -> go.Figure:
    """채널별 알림 분포 파이 차트."""
    if not by_channel:
        return _empty_fig("채널 발송 기록 없음")
    fig = go.Figure(data=[go.Pie(
        labels=list(by_channel.keys()),
        values=list(by_channel.values()),
        hole=0.4,
    )])
    fig.update_layout(
        title="채널별 알림 분포",
        height=300,
        margin=dict(t=60, b=20, l=20, r=20),
    )
    return fig


def grade_winrate_chart(grade_stats: dict[str, dict]) -> go.Figure:
    """등급별 승률 + 표본수 묶음 막대."""
    rows = []
    for g in ["A", "B", "C", "D", "X"]:
        s = grade_stats.get(g)
        if not s or s.get("count", 0) == 0:
            continue
        rows.append({"grade": g, "win_rate": s["win_rate"], "count": s["count"]})
    if not rows:
        return _empty_fig("등급별 통계 없음")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[r["grade"] for r in rows], y=[r["win_rate"] for r in rows],
        marker_color=[GRADE_COLOR[r["grade"]] for r in rows], name="승률(%)",
        text=[f"{r['win_rate']}%<br>n={r['count']}" for r in rows],
        textposition="auto",
        hovertemplate="<b>등급 %{x}</b><br>승률: %{y}%<extra></extra>",
    ))
    fig.update_layout(
        title="등급별 승률",
        xaxis=dict(title="등급"),
        yaxis=dict(title="승률 (%)", range=[0, 110]),
        height=300,
        margin=dict(t=60, b=40, l=40, r=40),
    )
    return fig
