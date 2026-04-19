"""Orchestrate buys, trailing-stop attachments, and sell notifications."""

import logging
import math
import time
from typing import Iterable, List

from alpaca_client import AlpacaClient
from config import Config
from data_source import Disclosure
from notifier import Notifier

log = logging.getLogger(__name__)

BUY_ORDER_PREFIX = "buy-"
TRAIL_ORDER_PREFIX = "trail-"


def _buy_client_order_id(disclosure_id: str) -> str:
    # Max 128 chars; disclosure ids are ~20.
    return f"{BUY_ORDER_PREFIX}{disclosure_id}"


def _trail_client_order_id(symbol: str) -> str:
    return f"{TRAIL_ORDER_PREFIX}{symbol}-{int(time.time())}"


def execute_buys(
    cfg: Config,
    client: AlpacaClient,
    notifier: Notifier,
    signals: List[Disclosure],
) -> int:
    """Place market buys for new signals, respecting concurrency and exposure caps. Returns count placed."""
    seen = client.recent_client_order_ids(lookback_days=60)
    positions = client.get_positions()
    held_symbols = {p.symbol for p in positions}

    available_slots = cfg.max_concurrent_positions - len(positions)
    current_exposure = sum(float(p.market_value) for p in positions)
    remaining_exposure = cfg.max_total_exposure_usd - current_exposure

    account = client.get_account()
    buying_power = float(account.buying_power)

    placed = 0
    for d in signals:
        if available_slots <= 0:
            log.info("Reached max concurrent positions (%d); stopping buy loop", cfg.max_concurrent_positions)
            break
        if remaining_exposure < cfg.position_size_usd:
            log.info("Exposure cap reached; stopping buy loop")
            break
        if buying_power < cfg.position_size_usd:
            log.info("Insufficient buying power ($%.2f); stopping buy loop", buying_power)
            break
        if d.ticker in held_symbols:
            log.debug("Already hold %s; skipping", d.ticker)
            continue

        coid = _buy_client_order_id(d.id)
        if coid in seen:
            log.debug("Disclosure %s already processed (client_order_id=%s)", d.id, coid)
            continue

        if not client.is_symbol_tradable(d.ticker):
            log.info("Symbol %s not tradable on Alpaca; skipping", d.ticker)
            continue

        qty_shares = None  # None for notional (fractional) orders — share count determined at fill
        try:
            if client.supports_fractional(d.ticker):
                order = client.place_market_buy_notional(
                    symbol=d.ticker,
                    notional_usd=cfg.position_size_usd,
                    client_order_id=coid,
                )
            else:
                price = client.get_latest_trade_price(d.ticker)
                if not price or price <= 0:
                    log.info("No price for %s; skipping", d.ticker)
                    continue
                qty = math.floor(cfg.position_size_usd / price)
                if qty <= 0:
                    log.info("Position size $%.2f < 1 share of %s @ $%.2f; skipping", cfg.position_size_usd, d.ticker, price)
                    continue
                order = client.place_market_buy_qty(d.ticker, qty, client_order_id=coid)
                qty_shares = qty
        except Exception as e:
            log.warning("Buy failed for %s: %s", d.ticker, e)
            continue

        if qty_shares is None:
            log.info("Placed notional buy: %s $%.2f order_id=%s", d.ticker, cfg.position_size_usd, order.id)
        else:
            log.info("Placed buy: %s qty=%s order_id=%s", d.ticker, qty_shares, order.id)
        notifier.notify_buy(
            symbol=d.ticker,
            notional_usd=cfg.position_size_usd,
            member=d.member,
            chamber=d.chamber,
            order_id=str(order.id),
            qty_shares=qty_shares,
        )
        held_symbols.add(d.ticker)
        available_slots -= 1
        remaining_exposure -= cfg.position_size_usd
        buying_power -= cfg.position_size_usd
        placed += 1

    return placed


def ensure_trailing_stops(
    cfg: Config,
    client: AlpacaClient,
    notifier: Notifier,
) -> int:
    """Attach a 5% trailing-stop sell to every AGENT-purchased position that lacks one.

    Positions bought manually by the user (outside the agent) are intentionally skipped —
    we identify agent positions by the BUY_ORDER_PREFIX on Alpaca's client_order_id.
    """
    agent_symbols = client.symbols_with_client_order_id_prefix(BUY_ORDER_PREFIX)
    positions = client.get_positions()
    open_trail = client.open_trailing_stop_symbols()

    attached = 0
    skipped_manual = 0
    for p in positions:
        if p.symbol not in agent_symbols:
            skipped_manual += 1
            continue
        if p.symbol in open_trail:
            continue
        # qty_available reflects shares not already tied up in open sell orders
        qty = float(getattr(p, "qty_available", p.qty))
        if qty <= 0:
            continue
        coid = _trail_client_order_id(p.symbol)
        try:
            order = client.place_trailing_stop_sell(
                symbol=p.symbol,
                qty=qty,
                trail_percent=cfg.trail_percent,
                client_order_id=coid,
            )
        except Exception as e:
            log.warning("Trailing-stop attach failed for %s: %s", p.symbol, e)
            continue

        log.info("Attached trailing stop: %s qty=%s trail=%s%% order_id=%s", p.symbol, qty, cfg.trail_percent, order.id)
        notifier.notify_trailing_stop_attached(
            symbol=p.symbol,
            qty=qty,
            trail_pct=cfg.trail_percent,
            order_id=str(order.id),
        )
        attached += 1

    if skipped_manual:
        log.info("Skipped %d non-agent position(s) (manual buys not eligible for agent trailing stops)", skipped_manual)
    return attached


def notify_recent_sell_fills(
    client: AlpacaClient,
    notifier: Notifier,
    lookback_minutes: int = 20,
) -> int:
    """Email about any trailing-stop sells that filled since the previous run."""
    fills = client.recent_filled_sells(minutes=lookback_minutes)
    count = 0
    for o in fills:
        if not (o.client_order_id and o.client_order_id.startswith(TRAIL_ORDER_PREFIX)):
            continue
        avg = float(o.filled_avg_price) if o.filled_avg_price else 0.0
        qty = float(o.filled_qty) if o.filled_qty else 0.0
        notifier.notify_sell_triggered(
            symbol=o.symbol,
            qty=qty,
            filled_avg=avg,
            order_id=str(o.id),
        )
        count += 1
    return count
