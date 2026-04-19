"""Fetch congressional trade disclosures from Quiver Quantitative (paid API)."""

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

QUIVER_LIVE_CONGRESS_URL = "https://api.quiverquant.com/beta/live/congresstrading"

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
    if "purchase" in s or "buy" in s:
        return "purchase"
    if "partial" in s and ("sale" in s or "sell" in s):
        return "sale_partial"
    if "sale" in s or "sell" in s:
        return "sale"
    if "exchange" in s:
        return "exchange"
    return s


def _stable_id(*parts: str) -> str:
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return h[:20]


def _normalize_chamber(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    s = raw.strip().lower()
    if s.startswith("s"):
        return "senate"
    if s.startswith("r") or s.startswith("h"):  # "Representative" or "House"
        return "house"
    return "unknown"


def _is_option(raw: Dict[str, Any]) -> bool:
    """Quiver marks options via TickerType='OP' or via description fields."""
    tt = (raw.get("TickerType") or "").strip().upper()
    if tt == "OP":
        return True
    desc = (raw.get("Description") or raw.get("asset_type") or "").lower()
    return any(k in desc for k in ("call", "put", "option"))


def _from_quiver(raw: Dict[str, Any]) -> Optional[Disclosure]:
    """Map a Quiver live/congresstrading item to our Disclosure."""
    ticker = (raw.get("Ticker") or "").strip().upper()
    if not ticker or ticker in ("--", "N/A", "NONE"):
        return None

    member = (raw.get("Representative") or raw.get("Senator") or raw.get("Name") or "").strip()
    chamber = _normalize_chamber(raw.get("House") or raw.get("Chamber"))

    tx_date = _parse_date(raw.get("TransactionDate") or raw.get("Transaction_Date"))
    disc_date = _parse_date(raw.get("ReportDate") or raw.get("Report_Date") or raw.get("last_modified"))

    # Quiver may give a numeric Amount, a Range string, or both.
    amount = raw.get("Amount")
    range_str = raw.get("Range") or raw.get("amount_range")
    if isinstance(amount, (int, float)) and amount > 0:
        # Amount is usually the LOWER bound of the disclosed range.
        lo = float(amount)
        # If we also have a range, pull the upper; else assume the SEC bucket doubled.
        if range_str:
            _, hi = _parse_amount_range(range_str)
            hi = max(hi, lo)
        else:
            hi = lo
    else:
        lo, hi = _parse_amount_range(range_str)

    asset_type = "option" if _is_option(raw) else "stock"

    did = _stable_id(
        "quiver",
        member,
        ticker,
        str(raw.get("TransactionDate") or ""),
        str(raw.get("Transaction") or ""),
        str(amount or range_str or ""),
    )
    return Disclosure(
        id=did,
        chamber=chamber,
        member=member,
        ticker=ticker,
        asset_type=asset_type,
        transaction_type=_normalize_txn_type(raw.get("Transaction")),
        transaction_date=tx_date,
        disclosure_date=disc_date,
        amount_min_usd=lo,
        amount_max_usd=hi,
    )


def _fetch_all_quiver(api_key: str, timeout: int = 30) -> List[Dict[str, Any]]:
    """Fetch the latest congressional-trading feed from Quiver."""
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    try:
        resp = requests.get(QUIVER_LIVE_CONGRESS_URL, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            log.warning("Quiver returned non-list response: %r", type(data).__name__)
            return []
        return data
    except Exception as e:
        log.error("Quiver fetch failed: %s", e)
        return []


def fetch_recent_disclosures(lookback_days: int, today: Optional[date] = None) -> List[Disclosure]:
    """Fetch Quiver's live congressional trading feed, filtered to the lookback window."""
    api_key = os.environ.get("QUIVER_API_KEY")
    if not api_key:
        log.error("QUIVER_API_KEY not set — cannot fetch disclosures")
        return []

    today = today or date.today()
    cutoff = today - timedelta(days=lookback_days)

    raw_items = _fetch_all_quiver(api_key)
    log.info("Quiver returned %d raw items", len(raw_items))

    out: List[Disclosure] = []
    skipped = 0
    for raw in raw_items:
        d = _from_quiver(raw)
        if d is None:
            skipped += 1
            continue
        ref = d.disclosure_date or d.transaction_date
        if ref is None or ref < cutoff:
            continue
        out.append(d)

    log.info("Parsed %d disclosures in last %d days (skipped %d unparseable)", len(out), lookback_days, skipped)
    return out
