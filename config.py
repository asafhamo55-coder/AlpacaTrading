"""Load and validate configuration from environment variables."""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    alpaca_api_key: str
    alpaca_api_secret: str
    alpaca_base_url: str
    position_size_usd: float
    trail_percent: float
    max_concurrent_positions: int
    max_total_exposure_usd: float
    lookback_days: int
    min_trade_size_usd: float

    # Data source
    quiver_api_key: Optional[str]

    # Notifications (optional — emailing is a no-op if host/user/password are missing)
    smtp_host: Optional[str]
    smtp_port: int
    smtp_user: Optional[str]
    smtp_password: Optional[str]
    notify_to: Optional[str]
    notify_from: Optional[str]

    @property
    def is_paper(self) -> bool:
        return "paper-api" in self.alpaca_base_url

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.notify_to)


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def load_config() -> Config:
    smtp_user = os.environ.get("SMTP_USER")
    return Config(
        alpaca_api_key=_require("ALPACA_API_KEY"),
        alpaca_api_secret=_require("ALPACA_API_SECRET"),
        alpaca_base_url=os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        position_size_usd=float(os.environ.get("POSITION_SIZE_USD", "500")),
        trail_percent=float(os.environ.get("TRAIL_PERCENT", "5")),
        max_concurrent_positions=int(os.environ.get("MAX_CONCURRENT_POSITIONS", "10")),
        max_total_exposure_usd=float(os.environ.get("MAX_TOTAL_EXPOSURE_USD", "10000")),
        lookback_days=int(os.environ.get("LOOKBACK_DAYS", "7")),
        min_trade_size_usd=float(os.environ.get("MIN_TRADE_SIZE_USD", "15000")),
        quiver_api_key=os.environ.get("QUIVER_API_KEY"),
        smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=smtp_user,
        smtp_password=os.environ.get("SMTP_PASSWORD"),
        notify_to=os.environ.get("NOTIFY_TO", "asafhamo55@gmail.com"),
        notify_from=os.environ.get("NOTIFY_FROM", smtp_user),
    )
