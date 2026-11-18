"""SMS through Twilio (plus an optional free push backup through ntfy.sh)."""
from __future__ import annotations

import logging
import os

import requests

from .models import Hit

log = logging.getLogger("notify")


def format_alert(hit: Hit, priority: bool, msrp: bool | None) -> str:
    price = f"${hit.price:,.2f}" if hit.price is not None else "Not listed"
    if msrp is True:
        price += " (MSRP)"
    qty = f"\nQuantity: {hit.quantity}" if hit.quantity is not None else ""
    dist = f"{hit.distance_mi:.0f} miles from Gulf Breeze" if hit.distance_mi is not None else "Unknown"
    star = "⭐ PRIORITY ⭐\n" if priority else ""
    return (
        f"🚨 POKÉMON RESTOCK ALERT 🚨\n{star}\n"
        f"Store: {hit.retailer} – {hit.store_name}\n"
        f"Location: {hit.address}\n"
        f"Product: {hit.product_name}\n"
        f"Price: {price}\n"
        f"Status: {hit.status.value} ({hit.availability_note}){qty}\n"
        f"Distance: {dist}\n\n"
        f"GO NOW: {hit.url}"
    )


class Notifier:
    def __init__(self, dry_run: bool = False, ntfy_topic: str = ""):
        self.dry_run = dry_run
        self.sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_ = os.getenv("TWILIO_FROM_NUMBER", "")
        self.to = os.getenv("ALERT_TO_NUMBER", "")
        self.ntfy_topic = os.getenv("NTFY_TOPIC") or ntfy_topic

    def send(self, body: str, link: str = "") -> bool:
        if self.dry_run:
            print("\n----- DRY RUN SMS -----\n" + body + "\n-----------------------")
            return True
        ok = False
        if self.sid and self.token and self.from_ and self.to:
            try:
                r = requests.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json",
                    auth=(self.sid, self.token),
                    data={"From": self.from_, "To": self.to, "Body": body},
                    timeout=20,
                )
                if r.status_code < 300:
                    ok = True
                else:
                    log.error("Twilio error %s: %s", r.status_code, r.text[:300])
            except requests.RequestException as e:
                log.error("Twilio request failed: %s", e)
        elif not self.ntfy_topic:
            log.warning("No alert method set: add ntfy_topic in config.yaml (or Twilio keys)")
        if self.ntfy_topic:
            try:
                requests.post(
                    f"https://ntfy.sh/{self.ntfy_topic}",
                    data=body.encode("utf-8"),
                    headers={"Title": "Pokemon restock!", "Priority": "urgent",
                             "Tags": "rotating_light", **({"Click": link} if link else {})},
                    timeout=15,
                )
                ok = True
            except requests.RequestException as e:
                log.error("ntfy failed: %s", e)
        return ok
