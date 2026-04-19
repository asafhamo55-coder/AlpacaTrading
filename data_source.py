"""Fetch congressional trade disclosures from CapitolTrades (public BFF JSON endpoint)."""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

BFF_URL = "https://bff.capitoltrades.com/trades"
USER_AGENT = "Mozilla/5.0 (compatible; AlpacaTradingBot/1.0; +https://github.com/asafhamo55-coder/AlpacaTrading)"
PAGE_SIZE = 100

AMOUNT_RANGE_RE = re.compile(r"\$?([\d,]+)\s*[-–]\s*\$?([\d,]+)")


@dataclass(frozen=True)
class Disclosure:
    """Normalized representation of a congressional trade disclosure."""

    id: str
    chamber: str               # "senate" or "house" (or "unknown")
    member: str
    ticker: str
    asset_type: str
    transaction_type: str      # "purchase", "sale", "exchange", etc.
    transaction_date: Optional[date]
    disclosure_date: Optional[date]
    amount_min_usd: float
    amount_max_usd: float

    @property
    def amount_mid_usd(self) -> float:
        return (self.amount_min_usd + self.amount_max_usd) / 2


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount_range(s: Optional[str]) -> tuple[float, float]:
    if not s:
        return (0.0, 0.0)
    m = AMOUNT_RANGE_RE.search(s)
    if not m:
        digits = re.sub(r"[^\d]", "", s)
        v = float(digits) if digits else 0.0
        return (v, v)
    lo = float(m.group(1).replace(",", ""))
    hi = float(m.group(2).replace(",", ""))
    return (lo, hi)


def _normalize_txn_type(s: Optional[str]) -> str:
    if not s:
        return "unknown"
    s = s.lower().strip()
    if "buy" in s or "purchase" in s:
        return "purchase"
    if "partial" in s and "sale" in s:
        return "sale_partial"
    if "sell" in s or "sale" in s:
        return "sale"
    if "exchange" in s:
        return "exchange"
    return s


def _stable_id(*parts: str) -> str:
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return h[:20]


def _get(d: Dict[str, Any], *path, default=None):
    """Safely navigate nested dicts/lists."""
    cur: Any = d
    for p in path:
        if cur is None:
            return default
        if isinstance(p, int):
            if isinstance(cur, list) and -len(cur) <= p < len(cur):
                cur = cur[p]
            else:
                return default
        else:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return default
    return cur if cur is not None else default


def _from_capitoltrades(raw: Dict[str, Any]) -> Optional[Disclosure]:
    """Map a CapitolTrades BFF trade object to our Disclosure."""
    ticker = (_get(raw, "asset", "assetTicker") or _get(raw, "assetTicker") or "").strip().upper()
    if not ticker or ticker in ("--", "N/A", "NONE"):
        return None

    first = _get(raw, "politician", "firstName") or ""
    last = _get(raw, "politician", "lastName") or ""
    member = f"{first} {last}".strip() or (_get(raw, "politician", "fullName") or "Unknown")

    chamber_raw = (_get(raw, "politician", "chamber") or "").strip().lower()
    chamber = "senate" if chamber_raw.startswith("s") else ("house" if chamber_raw.startswith("h") else "unknown")

    tx_type_raw = _get(raw, "txType") or _get(raw, "transactionType") or ""
    asset_type = (_get(raw, "asset", "assetType") or _get(raw, "assetType") or "").strip().lower()

    txn_date = _parse_date(_get(raw, "txDate") or _get(raw, "_txDate") or _get(raw, "transactionDate"))
    disc_date = _parse_date(_get(raw, "pubDate") or _get(raw, "_pubDate") or _get(raw, "disclosureDate"))

    # Amount: CapitolTrades usually sends numeric valueMin/valueMax, plus a label in `value`.
    v_min = _get(raw, "valueMin")
    v_max = _get(raw, "valueMax")
    if isinstance(v_min, (int, float)) and isinstance(v_max, (int, float)):
        lo, hi = float(v_min), float(v_max)
    else:
        lo, hi = _parse_amount_range(_get(raw, "value") or _get(raw, "amount"))

    did = _stable_id(
        "ct",
        str(_get(raw, "txId") or _get(raw, "id") or ""),
        member,
        ticker,
        str(_get(raw, "txDate") or ""),
        _normalize_txn_type(tx_type_raw),
    )
    return Disclosure(
        id=did,
        chamber=chamber,
        member=member,
        ticker=ticker,
        asset_type=asset_type,
        transaction_type=_normalize_txn_type(tx_type_raw),
        transaction_date=txn_date,
        disclosure_date=disc_date,
        amount_min_usd=lo,
        amount_max_usd=hi,
    )


def _fetch_page(params: dict, timeout: int = 20) -> Optional[dict]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.get(BFF_URL, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("CapitolTrades fetch failed (%s): %s", params, e)
        return None


def fetch_recent_disclosures(lookback_days: int, today: Optional[date] = None) -> List[Disclosure]:
    """Fetch recent disclosures from CapitolTrades, newest first, stopping once past the lookback window."""
    today = today or date.today()
    cutoff = today - timedelta(days=lookback_days)

    out: List[Disclosure] = []
    page = 1
    max_pages = 20  # hard cap — we sort by -pubDate, so 20 * 100 = 2000 rows is plenty

    while page <= max_pages:
        params = {
            "page": page,
            "pageSize": PAGE_SIZE,
            "sortBy": "-pubDate",
        }
        body = _fetch_page(params)
        if body is None:
            break

        rows = body.get("data") if isinstance(body, dict) else None
        if not rows:
            break

        page_added = 0
        hit_cutoff = False
        for raw in rows:
            d = _from_capitoltrades(raw)
            if d is None:
                continue
            ref = d.disclosure_date or d.transaction_date
            if ref is None:
                continue
            if ref < cutoff:
                hit_cutoff = True
                continue
            out.append(d)
            page_added += 1

        log.info("CapitolTrades page %d: parsed=%d added=%d total=%d", page, len(rows), page_added, len(out))

        if hit_cutoff:
            # Page contained rows older than cutoff; since they're sorted desc, we're done.
            break
        # If no rows were added from a full page (all rejected), bail to avoid spinning.
        if page_added == 0:
            break
        # If the page is short, that's the end.
        if len(rows) < PAGE_SIZE:
            break

        page += 1

    log.info("Fetched %d disclosures in last %d days", len(out), lookback_days)
    return out
