"""Entry point: fetch signals, place buys, attach trailing stops, notify on sells."""

import logging
import os
import sys
from datetime import date

from alpaca_client import AlpacaClient
from config import load_config
from data_source import Disclosure, fetch_recent_disclosures
from filters import apply_signal_filters, dedupe_by_ticker
from notifier import Notifier
from reporter import build_snapshot, render_markdown
from trader import ensure_trailing_stops, execute_buys, notify_recent_sell_fills


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def _force_run() -> bool:
    return os.environ.get("FORCE_RUN", "").strip().lower() in ("1", "true", "yes")


def _test_ticker() -> str:
    return os.environ.get("TEST_TICKER", "").strip().upper()


def _synthetic_signal(ticker: str) -> Disclosure:
    today = date.today()
    return Disclosure(
        id=f"TEST-{ticker}-{today.isoformat()}",
        chamber="test",
        member="TEST USER",
        ticker=ticker,
        asset_type="stock",
        transaction_type="purchase",
        transaction_date=today,
        disclosure_date=today,
        amount_min_usd=50000,
        amount_max_usd=100000,
    )


def main() -> int:
    _setup_logging()
    log = logging.getLogger("main")

    cfg = load_config()
    log.info("Config: paper=%s position=$%s trail=%s%% max_positions=%d exposure_cap=$%s",
             cfg.is_paper, cfg.position_size_usd, cfg.trail_percent,
             cfg.max_concurrent_positions, cfg.max_total_exposure_usd)

    client = AlpacaClient(cfg)
    notifier = Notifier(cfg)

    # 1. Notify any sell-fills since last run BEFORE checking market clock — fills can happen outside RTH via GTC.
    try:
        fills = notify_recent_sell_fills(client, notifier, lookback_minutes=20)
        log.info("Sell-fill notifications sent: %d", fills)
    except Exception as e:
        log.error("Sell-fill check failed: %s", e)

    # 2. Only place new orders when the market is open, unless FORCE_RUN is set.
    force = _force_run()
    if not force and not client.is_market_open():
        log.info("Market is closed; skipping buy + trailing-stop attachment.")
        return 0
    if force:
        log.warning("FORCE_RUN=true — placing orders regardless of market clock (orders queue until next open)")

    # 3. Fetch + filter signals (or use synthetic test signal if TEST_TICKER set).
    test_ticker = _test_ticker()
    if test_ticker:
        log.warning("TEST_TICKER=%s — bypassing data source with synthetic purchase signal", test_ticker)
        disclosures = [_synthetic_signal(test_ticker)]
    else:
        disclosures = fetch_recent_disclosures(cfg.lookback_days)
    signals = apply_signal_filters(disclosures, cfg.min_trade_size_usd)
    signals = dedupe_by_ticker(signals)
    # Most recent first so we act on freshest signals under caps.
    signals.sort(key=lambda d: (d.disclosure_date or d.transaction_date or __import__("datetime").date.min), reverse=True)

    # 4. Place buys.
    try:
        placed = execute_buys(cfg, client, notifier, signals)
        log.info("Buys placed this run: %d", placed)
    except Exception as e:
        log.error("Buy loop failed: %s", e)

    # 5. Attach trailing stops to any held position that lacks one.
    try:
        attached = ensure_trailing_stops(cfg, client, notifier)
        log.info("Trailing stops attached this run: %d", attached)
    except Exception as e:
        log.error("Trailing-stop loop failed: %s", e)

    # 6. Write a portfolio report to the GitHub Actions job summary (Tier 1).
    _write_job_summary(client)

    return 0


def _write_job_summary(client: AlpacaClient) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        snap = build_snapshot(client)
        markdown = render_markdown(snap, title="Alpaca Paper — Run Summary")
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown)
            f.write("\n")
    except Exception as e:
        logging.getLogger("main").error("Failed to write job summary: %s", e)


if __name__ == "__main__":
    sys.exit(main())
