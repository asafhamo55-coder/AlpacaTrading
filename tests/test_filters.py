from datetime import date

from data_source import Disclosure
from filters import (
    apply_signal_filters,
    dedupe_by_ticker,
    is_purchase,
    is_tradeable_equity_shape,
    meets_min_size,
)


def _d(**kw):
    base = dict(
        id="x",
        chamber="senate",
        member="Test",
        ticker="AAPL",
        asset_type="stock",
        transaction_type="purchase",
        transaction_date=date(2026, 1, 1),
        disclosure_date=date(2026, 1, 2),
        amount_min_usd=15001,
        amount_max_usd=50000,
    )
    base.update(kw)
    return Disclosure(**base)


def test_is_purchase():
    assert is_purchase(_d(transaction_type="purchase"))
    assert not is_purchase(_d(transaction_type="sale"))
    assert not is_purchase(_d(transaction_type="exchange"))


def test_is_tradeable_equity_shape_rejects_options():
    assert not is_tradeable_equity_shape(_d(asset_type="AAPL call option"))
    assert not is_tradeable_equity_shape(_d(asset_type="put options"))


def test_is_tradeable_equity_shape_rejects_bonds_and_funds():
    assert not is_tradeable_equity_shape(_d(asset_type="US Treasury note"))
    assert not is_tradeable_equity_shape(_d(asset_type="mutual fund"))
    assert not is_tradeable_equity_shape(_d(asset_type="etf"))


def test_is_tradeable_equity_shape_accepts_common_stock():
    assert is_tradeable_equity_shape(_d(ticker="AAPL", asset_type="common stock"))
    assert is_tradeable_equity_shape(_d(ticker="BRK.B", asset_type=""))


def test_is_tradeable_equity_shape_rejects_bad_ticker():
    assert not is_tradeable_equity_shape(_d(ticker="abcd"))
    assert not is_tradeable_equity_shape(_d(ticker=""))
    assert not is_tradeable_equity_shape(_d(ticker="TOOLONGTICKER"))


def test_meets_min_size():
    assert meets_min_size(_d(amount_min_usd=15001), 15000)
    assert not meets_min_size(_d(amount_min_usd=1000), 15000)


def test_apply_signal_filters_keeps_only_valid():
    ds = [
        _d(id="a", transaction_type="purchase"),
        _d(id="b", transaction_type="sale"),
        _d(id="c", asset_type="put option"),
        _d(id="d", amount_min_usd=5000),
    ]
    kept = apply_signal_filters(ds, min_trade_size_usd=15000)
    assert [d.id for d in kept] == ["a"]


def test_dedupe_by_ticker_keeps_most_recent():
    older = _d(id="o", ticker="NVDA", disclosure_date=date(2026, 1, 1))
    newer = _d(id="n", ticker="NVDA", disclosure_date=date(2026, 1, 5))
    other = _d(id="p", ticker="MSFT", disclosure_date=date(2026, 1, 3))
    out = dedupe_by_ticker([older, newer, other])
    ids = sorted(d.id for d in out)
    assert ids == ["n", "p"]
