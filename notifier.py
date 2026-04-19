"""Send email notifications via SMTP. No-op if SMTP credentials are not configured."""

import logging
import smtplib
from email.message import EmailMessage

from config import Config

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, cfg: Config):
        self._cfg = cfg

    def send(self, subject: str, body: str) -> bool:
        if not self._cfg.email_enabled:
            log.info("Email disabled (SMTP not configured); would have sent: %s", subject)
            return False

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._cfg.notify_from or self._cfg.smtp_user
        msg["To"] = self._cfg.notify_to
        msg.set_content(body)

        try:
            with smtplib.SMTP(self._cfg.smtp_host, self._cfg.smtp_port, timeout=20) as s:
                s.starttls()
                s.login(self._cfg.smtp_user, self._cfg.smtp_password)
                s.send_message(msg)
            log.info("Email sent to %s: %s", self._cfg.notify_to, subject)
            return True
        except Exception as e:
            log.error("Failed to send email: %s", e)
            return False

    def notify_buy(self, symbol: str, qty: float, notional_usd: float, member: str, chamber: str, order_id: str):
        subject = f"[Alpaca Paper] BUY {qty} {symbol}"
        body = (
            f"Market buy submitted on Alpaca paper account.\n\n"
            f"Symbol:   {symbol}\n"
            f"Quantity: {qty}\n"
            f"Notional: ${notional_usd:,.2f}\n"
            f"Order ID: {order_id}\n\n"
            f"Signal source:\n"
            f"  Chamber: {chamber}\n"
            f"  Member:  {member}\n"
        )
        self.send(subject, body)

    def notify_trailing_stop_attached(self, symbol: str, qty: float, trail_pct: float, order_id: str):
        subject = f"[Alpaca Paper] Trailing stop attached: {symbol}"
        body = (
            f"Trailing-stop sell placed on Alpaca paper account.\n\n"
            f"Symbol:   {symbol}\n"
            f"Quantity: {qty}\n"
            f"Trail:    {trail_pct}%\n"
            f"Order ID: {order_id}\n"
        )
        self.send(subject, body)

    def notify_sell_triggered(self, symbol: str, qty: float, filled_avg: float, order_id: str):
        subject = f"[Alpaca Paper] SELL filled (trail stop) {qty} {symbol}"
        body = (
            f"Trailing-stop sell filled on Alpaca paper account.\n\n"
            f"Symbol:      {symbol}\n"
            f"Quantity:    {qty}\n"
            f"Filled avg:  ${filled_avg:,.2f}\n"
            f"Order ID:    {order_id}\n"
        )
        self.send(subject, body)
