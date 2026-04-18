"""
Test Alpaca paper-trading connection and place a 1-share market buy of AAPL.

Usage:
    export ALPACA_API_KEY=your_key
    export ALPACA_API_SECRET=your_secret
    python test_alpaca.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional

BASE_URL = "https://paper-api.alpaca.markets/v2"


def request(method: str, path: str, key: str, secret: str, body: Optional[dict] = None):
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def main() -> int:
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        print("ERROR: set ALPACA_API_KEY and ALPACA_API_SECRET in your environment.")
        return 1

    print("1) Checking account...")
    status, account = request("GET", "/account", key, secret)
    if status != 200:
        print(f"  FAILED ({status}): {account}")
        return 1
    print(f"  OK — status={account.get('status')}, cash=${account.get('cash')}, buying_power=${account.get('buying_power')}")

    print("2) Placing market buy: 1 share AAPL (day)...")
    order = {
        "symbol": "AAPL",
        "qty": "1",
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
    }
    status, result = request("POST", "/orders", key, secret, order)
    if status not in (200, 201):
        print(f"  FAILED ({status}): {result}")
        return 1
    print(f"  OK — order id={result.get('id')}, status={result.get('status')}, submitted_at={result.get('submitted_at')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
