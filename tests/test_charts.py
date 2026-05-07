"""
tests/test_charts.py
plotly 차트 헬퍼가 정상 객체를 반환하는지 검증.
"""


def test_trend_line_chart_returns_figure():
    from dashboard.charts import trend_line_chart
    import plotly.graph_objects as go
    fig = trend_line_chart([
        {"ym": "2026-01", "avg_price": 100, "min_price": 90, "max_price": 110, "count": 3},
        {"ym": "2026-02", "avg_price": 105, "min_price": 95, "max_price": 115, "count": 4},
    ])
    assert isinstance(fig, go.Figure)
    # 평균/최고/최저/거래수 = 4개 trace
    assert len(fig.data) == 4


def test_trend_line_chart_empty_returns_placeholder():
    from dashboard.charts import trend_line_chart
    import plotly.graph_objects as go
    fig = trend_line_chart([])
    assert isinstance(fig, go.Figure)


def test_trend_with_reference_renders_dashed_lines():
    from dashboard.charts import trend_with_reference
    import plotly.graph_objects as go
    fig = trend_with_reference(
        [{"ym": "2026-01", "avg_price": 100, "min_price": 90, "max_price": 110, "count": 3}],
        references={"감정가": 80, "최저가": 60, "추정 시세": 100},
    )
    assert isinstance(fig, go.Figure)
    # 월평균 + 3개 기준선 = 4 trace
    assert len(fig.data) == 4


def test_grade_profit_bar_only_grades_with_data():
    from dashboard.charts import grade_profit_bar
    import plotly.graph_objects as go
    stats = {
        "A": {"count": 3, "win_rate": 100,
              "actual_profit": {"mean": 100, "min": 80, "max": 120}},
        "B": {"count": 0, "win_rate": 0, "actual_profit": {}},  # skipped
        "X": {"count": 5, "win_rate": 10,
              "actual_profit": {"mean": -50, "min": -80, "max": 10}},
    }
    fig = grade_profit_bar(stats)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1  # one bar trace with 2 grades


def test_pred_vs_actual_scatter_groups_by_grade():
    from dashboard.charts import pred_vs_actual_scatter
    import plotly.graph_objects as go
    pairs = [
        {"profit_estimate": 100, "simulated_profit": 90, "grade": "A", "address_full": "X"},
        {"profit_estimate": 200, "simulated_profit": 180, "grade": "A", "address_full": "Y"},
        {"profit_estimate": 50, "simulated_profit": 30, "grade": "B", "address_full": "Z"},
        {"profit_estimate": -30, "simulated_profit": -50, "grade": "X", "address_full": "W"},
    ]
    fig = pred_vs_actual_scatter(pairs)
    assert isinstance(fig, go.Figure)
    # A, B, X 등급 트레이스 + 대각선 = 4
    grade_traces = [t for t in fig.data if t.mode == "markers"]
    assert len(grade_traces) == 3


def test_grade_winrate_chart_creates_bar():
    from dashboard.charts import grade_winrate_chart
    import plotly.graph_objects as go
    fig = grade_winrate_chart({
        "A": {"count": 3, "win_rate": 100, "actual_profit": {"mean": 100}},
        "D": {"count": 5, "win_rate": 60, "actual_profit": {"mean": 10}},
    })
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
