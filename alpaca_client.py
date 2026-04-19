"""Thin wrapper around the Alpaca REST API using alpaca-py."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderStatus, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    MarketOrderRequest,
    TrailingStopOrderRequest,
)

from config import Config

log = logging.getLogger(__name__)


class AlpacaClient:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._client = TradingClient(
            api_key=cfg.alpaca_api_key,
            secret_key=cfg.alpaca_api_secret,
            paper=cfg.is_paper,
        )
        self._rest_headers = {
            "APCA-API-KEY-ID": cfg.alpaca_api_key,
            "APCA-API-SECRET-KEY": cfg.alpaca_api_secret,
        }

    # --- market state -----------------------------------------------------

    def is_market_open(self) -> bool:
        return bool(self._client.get_clock().is_open)

    # --- account / positions ---------------------------------------------

    def get_account(self):
        return self._client.get_account()

    def get_positions(self) -> list:
        return self._client.get_all_positions()

    def is_symbol_tradable(self, symbol: str) -> bool:
        try:
            asset = self._client.get_asset(symbol)
        except Exception as e:
            log.debug("get_asset(%s) failed: %s", symbol, e)
            return False
        status_active = True
        if hasattr(asset, "status") and asset.status is not None:
            val = getattr(asset.status, "value", asset.status)
            status_active = str(val).lower() == "active"
        return bool(asset.tradable and status_active)

    def supports_fractional(self, symbol: str) -> bool:
        try:
            asset = self._client.get_asset(symbol)
        except Exception:
            return False
        return bool(getattr(asset, "fractionable", False))

    # --- orders -----------------------------------------------------------

    def recent_client_order_ids(self, lookback_days: int = 60) -> set[str]:
        """Client_order_ids seen on any-status orders from the last N days."""
        after = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        req = GetOrdersRequest(status=QueryOrderStatus.ALL, after=after, limit=500)
        orders = self._client.get_orders(filter=req)
        return {o.client_order_id for o in orders if o.client_order_id}

    def open_trailing_stop_symbols(self) -> set[str]:
        """Symbols that already have an OPEN trailing-stop sell order."""
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)
        orders = self._client.get_orders(filter=req)
        out = set()
        for o in orders:
            ot = getattr(o, "order_type", None)
            ot_str = str(getattr(ot, "value", ot)).lower() if ot is not None else ""
            if "trailing_stop" in ot_str and o.side == OrderSide.SELL:
                out.add(o.symbol)
        return out

    def get_open_orders(self) -> list:
        """All orders currently open (new / accepted / partially_filled / queued etc.)."""
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)
        try:
            return list(self._client.get_orders(filter=req))
        except Exception as e:
            log.warning("get_open_orders failed: %s", e)
            return []

    def recent_filled_sells(self, minutes: int = 20) -> list:
        """Sell orders that filled within the last N minutes (for after-the-fact notifications)."""
        after = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=after, limit=200, side=OrderSide.SELL)
        orders = self._client.get_orders(filter=req)
        return [o for o in orders if o.status == OrderStatus.FILLED]

    def place_market_buy_notional(self, symbol: str, notional_usd: float, client_order_id: str):
        req = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional_usd, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
        return self._client.submit_order(req)

    def place_market_buy_qty(self, symbol: str, qty: float, client_order_id: str):
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
        return self._client.submit_order(req)

    def get_recent_fills(self, days: int = 30) -> list:
        """FILL-type account activities within the last N days (most recent first)."""
        after = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        url = f"{self._cfg.alpaca_base_url}/account/activities/FILL"
        try:
            resp = requests.get(
                url,
                headers=self._rest_headers,
                params={"after": after, "page_size": 100, "direction": "desc"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            log.warning("get_recent_fills failed: %s", e)
            return []

    def get_portfolio_history(self, period: str = "1M", timeframe: str = "1D") -> Optional[dict]:
        """Return the raw portfolio history payload from Alpaca's REST API."""
        url = f"{self._cfg.alpaca_base_url}/account/portfolio/history"
        try:
            resp = requests.get(
                url,
                headers=self._rest_headers,
                params={"period": period, "timeframe": timeframe},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.warning("get_portfolio_history failed: %s", e)
            return None

    def place_trailing_stop_sell(self, symbol: str, qty: float, trail_percent: float, client_order_id: str):
        req = TrailingStopOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            trail_percent=str(trail_percent),
            client_order_id=client_order_id,
        )
        return self._client.submit_order(req)

    def get_latest_trade_price(self, symbol: str) -> Optional[float]:
        """Fallback price lookup so we can size whole-share orders when notional isn't supported."""
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestTradeRequest

            # Market-data API uses the same keys as trading API.
            data_client = StockHistoricalDataClient(
                api_key=self._client._api_key,
                secret_key=self._client._secret_key,
            )
            resp = data_client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
            trade = resp.get(symbol) if isinstance(resp, dict) else getattr(resp, symbol, None)
            return float(trade.price) if trade else None
        except Exception as e:
            log.debug("latest_trade(%s) failed: %s", symbol, e)
            return None
