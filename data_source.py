"""Fetch congressional trade disclosures from senate-stock-watcher and house-stock-watcher."""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional

import requests

log = logging.getLogger(__name__)

SENATE_URL = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"
HOUSE_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"

AMOUNT_RANGE_RE = re.compile(r"\$?([\d,]+)\s*-\s*\$?([\d,]+)")


@dataclass(frozen=True)
class Disclosure:
    """Normalized representation of a congressional trade disclosure."""

    id: str
    chamber: str               # "senate" or "house"
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
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
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
    s = s.lower()
    if "purchase" in s:
        return "purchase"
    if "sale" in s and "partial" in s:
        return "sale_partial"
    if "sale" in s:
        return "sale"
    if "exchange" in s:
        return "exchange"
    return s.strip()


def _stable_id(*parts: str) -> str:
    """Build a deterministic id for deduplication across runs."""
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return h[:20]


def _from_senate(raw: dict) -> Optional[Disclosure]:
    ticker = (raw.get("ticker") or "").strip().upper()
    if not ticker or ticker in ("--", "N/A"):
        return None
    txn_date = _parse_date(raw.get("transaction_date"))
    disc_date = _parse_date(raw.get("disclosure_date"))
    lo, hi = _parse_amount_range(raw.get("amount"))
    member = (raw.get("senator") or "").strip()
    did = _stable_id("senate", member, ticker, raw.get("transaction_date") or "", raw.get("type") or "", raw.get("amount") or "")
    return Disclosure(
        id=did,
        chamber="senate",
        member=member,
        ticker=ticker,
        asset_type=(raw.get("asset_type") or "").strip().lower(),
        transaction_type=_normalize_txn_type(raw.get("type")),
        transaction_date=txn_date,
        disclosure_date=disc_date,
        amount_min_usd=lo,
        amount_max_usd=hi,
    )


def _from_house(raw: dict) -> Optional[Disclosure]:
    ticker = (raw.get("ticker") or "").strip().upper()
    if not ticker or ticker in ("--", "N/A"):
        return None
    txn_date = _parse_date(raw.get("transaction_date"))
    disc_date = _parse_date(raw.get("disclosure_date"))
    lo, hi = _parse_amount_range(raw.get("amount"))
    member = (raw.get("representative") or "").strip()
    did = _stable_id("house", member, ticker, raw.get("transaction_date") or "", raw.get("type") or "", raw.get("amount") or "")
    return Disclosure(
        id=did,
        chamber="house",
        member=member,
        ticker=ticker,
        asset_type=(raw.get("asset_description") or raw.get("asset_type") or "").strip().lower(),
        transaction_type=_normalize_txn_type(raw.get("type")),
        transaction_date=txn_date,
        disclosure_date=disc_date,
        amount_min_usd=lo,
        amount_max_usd=hi,
    )


def _fetch(url: str, timeout: int = 30) -> list:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_recent_disclosures(lookback_days: int, today: Optional[date] = None) -> List[Disclosure]:
    """Fetch Senate + House disclosures filed within the lookback window."""
    today = today or date.today()
    cutoff = today - timedelta(days=lookback_days)

    out: List[Disclosure] = []

    for url, mapper, label in (
        (SENATE_URL, _from_senate, "senate"),
        (HOUSE_URL, _from_house, "house"),
    ):
        try:
            raw_items = _fetch(url)
        except Exception as e:
            log.warning("Failed to fetch %s feed: %s", label, e)
            continue

        for raw in raw_items:
            d = mapper(raw)
            if d is None:
                continue
            # Prefer disclosure_date for recency; fall back to transaction_date
            ref = d.disclosure_date or d.transaction_date
            if ref is None or ref < cutoff:
                continue
            out.append(d)

    log.info("Fetched %d disclosures in last %d days", len(out), lookback_days)
    return out
