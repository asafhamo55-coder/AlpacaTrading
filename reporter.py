"""Build portfolio reports (markdown + HTML) from live Alpaca state."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:  # avoid requiring alpaca-py at import time (keeps tests standalone)
    from alpaca_client import AlpacaClient

log = logging.getLogger(__name__)


@dataclass
class ReportSnapshot:
    """Everything we need to render a report — decoupled from Alpaca SDK types for easy testing."""

    equity: float
    last_equity: float
    cash: float
    buying_power: float
    day_change_usd: float
    day_change_pct: float
    positions: list              # list of dict rows
    recent_fills: list           # list of dict rows
    all_time_pct: Optional[float]
    week_pct: Optional[float]


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _pct_change(first: float, last: float) -> Optional[float]:
    if first is None or last is None or first == 0:
        return None
    return (last - first) / first * 100.0


def build_snapshot(client: "AlpacaClient") -> ReportSnapshot:
    acct = client.get_account()
    equity = _safe_float(getattr(acct, "equity", 0))
    last_equity = _safe_float(getattr(acct, "last_equity", 0))
    cash = _safe_float(getattr(acct, "cash", 0))
    buying_power = _safe_float(getattr(acct, "buying_power", 0))
    day_change_usd = equity - last_equity
    day_change_pct = (day_change_usd / last_equity * 100.0) if last_equity else 0.0

    # Positions
    position_rows = []
    for p in client.get_positions():
        position_rows.append({
            "symbol": p.symbol,
            "qty": _safe_float(p.qty),
            "avg_entry": _safe_float(p.avg_entry_price),
            "current": _safe_float(getattr(p, "current_price", 0)),
            "market_value": _safe_float(p.market_value),
            "pnl_usd": _safe_float(p.unrealized_pl),
            "pnl_pct": _safe_float(p.unrealized_plpc) * 100.0,
        })
    position_rows.sort(key=lambda r: r["pnl_usd"], reverse=True)

    # Recent fills (last 30 days, capped to 20 rows)
    fill_rows = []
    for a in client.get_recent_fills(days=30)[:20]:
        fill_rows.append({
            "time": getattr(a, "transaction_time", None),
            "side": str(getattr(a, "side", "")),
            "symbol": getattr(a, "symbol", ""),
            "qty": _safe_float(getattr(a, "qty", 0)),
            "price": _safe_float(getattr(a, "price", 0)),
        })

    # Portfolio history for longer windows
    all_time_pct = None
    week_pct = None
    hist_all = client.get_portfolio_history(period="1A", timeframe="1D")
    if hist_all:
        eq_series = hist_all.get("equity") or []
        if len(eq_series) >= 2 and eq_series[0]:
            all_time_pct = _pct_change(_safe_float(eq_series[0]), _safe_float(eq_series[-1]))
    hist_week = client.get_portfolio_history(period="1W", timeframe="1D")
    if hist_week:
        eq_series = hist_week.get("equity") or []
        if len(eq_series) >= 2 and eq_series[0]:
            week_pct = _pct_change(_safe_float(eq_series[0]), _safe_float(eq_series[-1]))

    return ReportSnapshot(
        equity=equity,
        last_equity=last_equity,
        cash=cash,
        buying_power=buying_power,
        day_change_usd=day_change_usd,
        day_change_pct=day_change_pct,
        positions=position_rows,
        recent_fills=fill_rows,
        all_time_pct=all_time_pct,
        week_pct=week_pct,
    )


# --- Rendering -------------------------------------------------------------

def _fmt_usd(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.2f}"


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "—"
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.2f}%"


def _fmt_time(t) -> str:
    if t is None:
        return ""
    if isinstance(t, str):
        return t[:16].replace("T", " ")
    try:
        return t.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(t)


def render_markdown(snap: ReportSnapshot, title: str = "Alpaca Paper — Portfolio Report") -> str:
    lines = [f"## {title}", ""]

    lines.append("### Account")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Equity | {_fmt_usd(snap.equity)} |")
    lines.append(f"| Cash | {_fmt_usd(snap.cash)} |")
    lines.append(f"| Buying power | {_fmt_usd(snap.buying_power)} |")
    lines.append(f"| Day change | {_fmt_usd(snap.day_change_usd)} ({_fmt_pct(snap.day_change_pct)}) |")
    lines.append(f"| Week change | {_fmt_pct(snap.week_pct)} |")
    lines.append(f"| All-time change | {_fmt_pct(snap.all_time_pct)} |")
    lines.append("")

    lines.append(f"### Open positions ({len(snap.positions)})")
    if not snap.positions:
        lines.append("_No open positions._")
    else:
        lines.append("| Symbol | Qty | Avg entry | Current | Value | PnL $ | PnL % |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for r in snap.positions:
            lines.append(
                f"| {r['symbol']} | {r['qty']:.4f} | {_fmt_usd(r['avg_entry'])} | "
                f"{_fmt_usd(r['current'])} | {_fmt_usd(r['market_value'])} | "
                f"{_fmt_usd(r['pnl_usd'])} | {_fmt_pct(r['pnl_pct'])} |"
            )
    lines.append("")

    lines.append(f"### Recent fills ({len(snap.recent_fills)})")
    if not snap.recent_fills:
        lines.append("_No recent fills._")
    else:
        lines.append("| Time | Side | Symbol | Qty | Price |")
        lines.append("|---|---|---|---:|---:|")
        for r in snap.recent_fills:
            lines.append(
                f"| {_fmt_time(r['time'])} | {r['side']} | {r['symbol']} | "
                f"{r['qty']:.4f} | {_fmt_usd(r['price'])} |"
            )
    lines.append("")
    lines.append(f"_Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    return "\n".join(lines)


def render_html(snap: ReportSnapshot, title: str = "Alpaca Paper — Portfolio Report") -> str:
    style = """
    <style>
      body { font-family: -apple-system, system-ui, Segoe UI, Roboto, sans-serif; color: #222; max-width: 760px; }
      h2 { border-bottom: 1px solid #ddd; padding-bottom: 4px; }
      h3 { color: #444; margin-top: 24px; }
      table { border-collapse: collapse; width: 100%; font-size: 13px; }
      th, td { padding: 6px 10px; border-bottom: 1px solid #eee; text-align: left; }
      th { background: #f7f7f7; }
      td.num, th.num { text-align: right; }
      .pos { color: #0a7d2b; }
      .neg { color: #b42318; }
      .muted { color: #888; font-size: 12px; }
    </style>
    """

    def pct_cell(x):
        if x is None:
            return '<td class="num muted">—</td>'
        cls = "pos" if x > 0 else ("neg" if x < 0 else "")
        return f'<td class="num {cls}">{_fmt_pct(x)}</td>'

    def usd_cell(x):
        cls = "pos" if x > 0 else ("neg" if x < 0 else "")
        return f'<td class="num {cls}">{_fmt_usd(x)}</td>'

    html = [f"<!doctype html><html><head><meta charset='utf-8'>{style}</head><body>"]
    html.append(f"<h2>{title}</h2>")

    html.append("<h3>Account</h3><table>")
    html.append(f"<tr><th>Equity</th>{usd_cell(snap.equity)}</tr>")
    html.append(f"<tr><th>Cash</th>{usd_cell(snap.cash)}</tr>")
    html.append(f"<tr><th>Buying power</th>{usd_cell(snap.buying_power)}</tr>")
    html.append(
        f"<tr><th>Day change</th><td class='num'>{_fmt_usd(snap.day_change_usd)} "
        f"(<span class='{'pos' if snap.day_change_pct>0 else 'neg' if snap.day_change_pct<0 else ''}'>"
        f"{_fmt_pct(snap.day_change_pct)}</span>)</td></tr>"
    )
    html.append(f"<tr><th>Week change</th>{pct_cell(snap.week_pct)}</tr>")
    html.append(f"<tr><th>All-time change</th>{pct_cell(snap.all_time_pct)}</tr>")
    html.append("</table>")

    html.append(f"<h3>Open positions ({len(snap.positions)})</h3>")
    if not snap.positions:
        html.append("<p><em>No open positions.</em></p>")
    else:
        html.append("<table><thead><tr><th>Symbol</th><th class='num'>Qty</th><th class='num'>Avg entry</th>"
                    "<th class='num'>Current</th><th class='num'>Value</th><th class='num'>PnL $</th>"
                    "<th class='num'>PnL %</th></tr></thead><tbody>")
        for r in snap.positions:
            html.append(
                f"<tr><td>{r['symbol']}</td><td class='num'>{r['qty']:.4f}</td>"
                f"<td class='num'>{_fmt_usd(r['avg_entry'])}</td>"
                f"<td class='num'>{_fmt_usd(r['current'])}</td>"
                f"<td class='num'>{_fmt_usd(r['market_value'])}</td>"
                f"{usd_cell(r['pnl_usd'])}{pct_cell(r['pnl_pct'])}</tr>"
            )
        html.append("</tbody></table>")

    html.append(f"<h3>Recent fills ({len(snap.recent_fills)})</h3>")
    if not snap.recent_fills:
        html.append("<p><em>No recent fills.</em></p>")
    else:
        html.append("<table><thead><tr><th>Time</th><th>Side</th><th>Symbol</th>"
                    "<th class='num'>Qty</th><th class='num'>Price</th></tr></thead><tbody>")
        for r in snap.recent_fills:
            html.append(
                f"<tr><td>{_fmt_time(r['time'])}</td><td>{r['side']}</td><td>{r['symbol']}</td>"
                f"<td class='num'>{r['qty']:.4f}</td><td class='num'>{_fmt_usd(r['price'])}</td></tr>"
            )
        html.append("</tbody></table>")

    html.append(f"<p class='muted'>Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>")
    html.append("</body></html>")
    return "\n".join(html)
