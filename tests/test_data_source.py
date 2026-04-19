from datetime import date

from data_source import _from_quiver, _parse_amount_range, _parse_date, _stable_id


def test_parse_amount_range():
    assert _parse_amount_range("$15,001 - $50,000") == (15001.0, 50000.0)
    assert _parse_amount_range("$1,001 - $15,000") == (1001.0, 15000.0)
    assert _parse_amount_range("1001 - 15000") == (1001.0, 15000.0)
    assert _parse_amount_range(None) == (0.0, 0.0)
    assert _parse_amount_range("") == (0.0, 0.0)


def test_parse_date_multiple_formats():
    assert _parse_date("2026-01-15") == date(2026, 1, 15)
    assert _parse_date("2026-01-15T12:34:56Z") == date(2026, 1, 15)
    assert _parse_date("01/15/2026") == date(2026, 1, 15)
    assert _parse_date(None) is None
    assert _parse_date("not a date") is None


def test_stable_id_is_deterministic():
    a = _stable_id("quiver", "Smith", "AAPL", "2026-01-15", "Purchase", "15001")
    b = _stable_id("quiver", "Smith", "AAPL", "2026-01-15", "Purchase", "15001")
    assert a == b
    c = _stable_id("quiver", "Smith", "MSFT", "2026-01-15", "Purchase", "15001")
    assert a != c


def test_from_quiver_maps_senate_purchase():
    raw = {
        "Representative": "Jane Smith",
        "Ticker": "aapl",
        "Transaction": "Purchase",
        "TransactionDate": "2026-01-15",
        "ReportDate": "2026-01-20",
        "Amount": 15001,
        "Range": "$15,001 - $50,000",
        "House": "Senate",
        "TickerType": "ST",
    }
    d = _from_quiver(raw)
    assert d is not None
    assert d.chamber == "senate"
    assert d.member == "Jane Smith"
    assert d.ticker == "AAPL"
    assert d.transaction_type == "purchase"
    assert d.transaction_date == date(2026, 1, 15)
    assert d.disclosure_date == date(2026, 1, 20)
    assert d.amount_min_usd == 15001
    assert d.amount_max_usd == 50000
    assert d.asset_type == "stock"


def test_from_quiver_maps_house_sale():
    raw = {
        "Representative": "John Doe",
        "Ticker": "MSFT",
        "Transaction": "Sale (Partial)",
        "TransactionDate": "2026-02-01",
        "ReportDate": "2026-02-10",
        "Range": "$1,001 - $15,000",
        "House": "Representative",
        "TickerType": "ST",
    }
    d = _from_quiver(raw)
    assert d is not None
    assert d.chamber == "house"
    assert d.transaction_type == "sale_partial"
    assert d.amount_min_usd == 1001
    assert d.asset_type == "stock"


def test_from_quiver_flags_options():
    raw = {
        "Representative": "Jane Smith",
        "Ticker": "NVDA",
        "Transaction": "Purchase",
        "TransactionDate": "2026-03-01",
        "ReportDate": "2026-03-05",
        "Range": "$15,001 - $50,000",
        "House": "Senate",
        "TickerType": "OP",
    }
    d = _from_quiver(raw)
    assert d is not None
    assert d.asset_type == "option"


def test_from_quiver_rejects_missing_ticker():
    assert _from_quiver({"Representative": "X", "Ticker": "", "Transaction": "Purchase"}) is None
    assert _from_quiver({"Representative": "X", "Ticker": "--", "Transaction": "Purchase"}) is None
