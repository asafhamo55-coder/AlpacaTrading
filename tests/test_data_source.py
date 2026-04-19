from datetime import date

from data_source import _from_house, _from_senate, _parse_amount_range, _parse_date, _stable_id


def test_parse_amount_range():
    assert _parse_amount_range("$15,001 - $50,000") == (15001.0, 50000.0)
    assert _parse_amount_range("$1,001 - $15,000") == (1001.0, 15000.0)
    assert _parse_amount_range("1001 - 15000") == (1001.0, 15000.0)
    assert _parse_amount_range(None) == (0.0, 0.0)
    assert _parse_amount_range("") == (0.0, 0.0)


def test_parse_date_multiple_formats():
    assert _parse_date("01/15/2026") == date(2026, 1, 15)
    assert _parse_date("2026-01-15") == date(2026, 1, 15)
    assert _parse_date(None) is None
    assert _parse_date("not a date") is None


def test_stable_id_is_deterministic():
    a = _stable_id("senate", "Smith", "AAPL", "01/15/2026", "Purchase", "$15,001 - $50,000")
    b = _stable_id("senate", "Smith", "AAPL", "01/15/2026", "Purchase", "$15,001 - $50,000")
    assert a == b
    c = _stable_id("senate", "Smith", "MSFT", "01/15/2026", "Purchase", "$15,001 - $50,000")
    assert a != c


def test_from_senate_maps_fields():
    raw = {
        "senator": "Jane Smith",
        "ticker": "aapl",
        "asset_type": "Stock",
        "type": "Purchase",
        "transaction_date": "01/15/2026",
        "disclosure_date": "01/20/2026",
        "amount": "$15,001 - $50,000",
    }
    d = _from_senate(raw)
    assert d is not None
    assert d.chamber == "senate"
    assert d.member == "Jane Smith"
    assert d.ticker == "AAPL"
    assert d.transaction_type == "purchase"
    assert d.transaction_date == date(2026, 1, 15)
    assert d.disclosure_date == date(2026, 1, 20)
    assert d.amount_min_usd == 15001
    assert d.amount_max_usd == 50000


def test_from_house_maps_fields():
    raw = {
        "representative": "John Doe",
        "ticker": "MSFT",
        "asset_description": "Microsoft Common Stock",
        "type": "purchase",
        "transaction_date": "2026-02-01",
        "disclosure_date": "2026-02-10",
        "amount": "$1,001 - $15,000",
    }
    d = _from_house(raw)
    assert d is not None
    assert d.chamber == "house"
    assert d.member == "John Doe"
    assert d.ticker == "MSFT"
    assert d.transaction_type == "purchase"
    assert d.amount_min_usd == 1001


def test_from_senate_rejects_missing_ticker():
    assert _from_senate({"senator": "X", "ticker": "", "type": "Purchase"}) is None
    assert _from_senate({"senator": "X", "ticker": "--", "type": "Purchase"}) is None
