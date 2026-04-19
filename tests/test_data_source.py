from datetime import date

from data_source import _from_capitoltrades, _parse_amount_range, _parse_date, _stable_id


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
    a = _stable_id("ct", "123", "Smith", "AAPL", "2026-01-15", "purchase")
    b = _stable_id("ct", "123", "Smith", "AAPL", "2026-01-15", "purchase")
    assert a == b
    c = _stable_id("ct", "124", "Smith", "AAPL", "2026-01-15", "purchase")
    assert a != c


def test_from_capitoltrades_maps_buy():
    raw = {
        "txId": "42",
        "politician": {"firstName": "Jane", "lastName": "Smith", "chamber": "Senate"},
        "asset": {"assetTicker": "aapl", "assetType": "Stock"},
        "txType": "buy",
        "txDate": "2026-01-15",
        "pubDate": "2026-01-20",
        "valueMin": 15001,
        "valueMax": 50000,
    }
    d = _from_capitoltrades(raw)
    assert d is not None
    assert d.chamber == "senate"
    assert d.member == "Jane Smith"
    assert d.ticker == "AAPL"
    assert d.transaction_type == "purchase"
    assert d.transaction_date == date(2026, 1, 15)
    assert d.disclosure_date == date(2026, 1, 20)
    assert d.amount_min_usd == 15001
    assert d.amount_max_usd == 50000


def test_from_capitoltrades_maps_house_and_sell():
    raw = {
        "txId": "99",
        "politician": {"firstName": "John", "lastName": "Doe", "chamber": "House"},
        "asset": {"assetTicker": "MSFT", "assetType": "Common Stock"},
        "txType": "sell",
        "txDate": "2026-02-01",
        "pubDate": "2026-02-10",
        "value": "$1,001 - $15,000",
    }
    d = _from_capitoltrades(raw)
    assert d is not None
    assert d.chamber == "house"
    assert d.member == "John Doe"
    assert d.ticker == "MSFT"
    assert d.transaction_type == "sale"
    assert d.amount_min_usd == 1001


def test_from_capitoltrades_rejects_missing_ticker():
    raw = {"politician": {"firstName": "X", "lastName": "Y"}, "asset": {"assetTicker": ""}, "txType": "buy"}
    assert _from_capitoltrades(raw) is None
    raw2 = {"politician": {"firstName": "X", "lastName": "Y"}, "asset": {"assetTicker": "--"}, "txType": "buy"}
    assert _from_capitoltrades(raw2) is None
