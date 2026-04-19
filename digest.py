"""Daily digest entry point — builds portfolio snapshot and emails an HTML summary."""

import logging
import sys
from datetime import date

from alpaca_client import AlpacaClient
from config import load_config
from notifier import Notifier
from reporter import build_snapshot, render_html, render_markdown


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def main() -> int:
    _setup_logging()
    log = logging.getLogger("digest")

    cfg = load_config()
    client = AlpacaClient(cfg)
    notifier = Notifier(cfg)

    snap = build_snapshot(client)
    today = date.today().isoformat()
    subject = (
        f"[Alpaca Paper] Daily digest {today} — "
        f"equity ${snap.equity:,.0f} ({snap.day_change_pct:+.2f}%)"
    )
    text = render_markdown(snap, title=f"Alpaca Paper — Daily digest {today}")
    html = render_html(snap, title=f"Alpaca Paper — Daily digest {today}")

    ok = notifier.send(subject, text, html=html)
    log.info("Daily digest send %s", "succeeded" if ok else "skipped/failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
