from reporter import ReportSnapshot, render_html, render_markdown


def _snap(**overrides):
    base = dict(
        equity=101500.0,
        last_equity=100000.0,
        cash=50000.0,
        buying_power=150000.0,
        day_change_usd=1500.0,
        day_change_pct=1.5,
        positions=[
            {"symbol": "AAPL", "qty": 2.4, "avg_entry": 208.0, "current": 215.0,
             "market_value": 516.0, "pnl_usd": 16.8, "pnl_pct": 3.37},
            {"symbol": "MSFT", "qty": 1.1, "avg_entry": 450.0, "current": 440.0,
             "market_value": 484.0, "pnl_usd": -11.0, "pnl_pct": -2.22},
        ],
        pending_orders=[
            {"symbol": "NVDA", "side": "BUY", "order_type": "market",
             "qty": None, "notional": 500.0, "status": "accepted",
             "submitted_at": "2026-04-19T10:15:00Z"},
        ],
        recent_fills=[
            {"time": "2026-04-21T13:32:10Z", "side": "BUY", "symbol": "AAPL",
             "qty": 2.4, "price": 208.0},
        ],
        all_time_pct=1.5,
        week_pct=0.7,
    )
    base.update(overrides)
    return ReportSnapshot(**base)


def test_render_markdown_includes_positions_and_pnl():
    md = render_markdown(_snap())
    assert "AAPL" in md
    assert "MSFT" in md
    assert "+1.50%" in md      # day change positive
    assert "-$11.00" in md     # MSFT negative pnl
    assert "Recent fills" in md


def test_render_markdown_handles_empty_state():
    snap = _snap(positions=[], pending_orders=[], recent_fills=[])
    md = render_markdown(snap)
    assert "No open positions" in md
    assert "No pending orders" in md
    assert "No recent fills" in md


def test_render_includes_pending_orders():
    md = render_markdown(_snap())
    assert "Pending orders (1)" in md
    assert "NVDA" in md
    assert "accepted" in md
    assert "$500.00" in md

    html = render_html(_snap())
    assert "Pending orders (1)" in html
    assert "NVDA" in html


def test_render_html_has_table_markup():
    html = render_html(_snap())
    assert "<table>" in html
    assert "AAPL" in html
    assert "pos" in html  # css class for positive pnl
    assert "neg" in html  # css class for negative pnl


def test_render_handles_none_percentages():
    snap = _snap(all_time_pct=None, week_pct=None)
    md = render_markdown(snap)
    assert md.count("—") >= 2
