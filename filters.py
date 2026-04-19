"""Apply signal filters to disclosures to produce actionable buy signals."""

import logging
import re
from typing import Iterable, List

from data_source import Disclosure

log = logging.getLogger(__name__)

OPTION_HINTS = ("call", "put", " option", "option ")
NON_EQUITY_HINTS = ("bond", "note", "treasury", "municipal", "mutual fund", "etf", "fund")
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def is_purchase(d: Disclosure) -> bool:
    return d.transaction_type == "purchase"


def is_tradeable_equity_shape(d: Disclosure) -> bool:
    """Cheap client-side filter. A proper Alpaca tradeability check happens later."""
    if not TICKER_RE.match(d.ticker):
        return False
    desc = d.asset_type.lower()
    if any(h in desc for h in OPTION_HINTS):
        return False
    if any(h in desc for h in NON_EQUITY_HINTS):
        return False
    return True


def meets_min_size(d: Disclosure, min_usd: float) -> bool:
    # Use the lower bound of the disclosed range — conservative.
    return d.amount_min_usd >= min_usd


def apply_signal_filters(disclosures: Iterable[Disclosure], min_trade_size_usd: float) -> List[Disclosure]:
    kept: List[Disclosure] = []
    dropped_counts = {"not_purchase": 0, "not_equity": 0, "too_small": 0}
    for d in disclosures:
        if not is_purchase(d):
            dropped_counts["not_purchase"] += 1
            continue
        if not is_tradeable_equity_shape(d):
            dropped_counts["not_equity"] += 1
            continue
        if not meets_min_size(d, min_trade_size_usd):
            dropped_counts["too_small"] += 1
            continue
        kept.append(d)

    log.info("Filtered disclosures: kept=%d dropped=%s", len(kept), dropped_counts)
    return kept


def dedupe_by_ticker(disclosures: Iterable[Disclosure]) -> List[Disclosure]:
    """Keep one disclosure per ticker (the most recent). Avoids stacking orders for the same ticker in one run."""
    best: dict[str, Disclosure] = {}
    for d in disclosures:
        cur = best.get(d.ticker)
        if cur is None:
            best[d.ticker] = d
            continue
        cur_ref = cur.disclosure_date or cur.transaction_date
        new_ref = d.disclosure_date or d.transaction_date
        if new_ref and (cur_ref is None or new_ref > cur_ref):
            best[d.ticker] = d
    return list(best.values())
