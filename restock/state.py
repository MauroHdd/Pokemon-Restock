"""Remembers what we've already seen so the same restock is only texted once."""
from __future__ import annotations

import json
import os
import time

from .models import Hit, Stock


class State:
    def __init__(self, path: str):
        self.path = path
        self.items: dict[str, dict] = {}
        self.source_failures: dict[str, dict] = {}
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                self.items = data.get("items", {})
                self.source_failures = data.get("source_failures", {})
            except (json.JSONDecodeError, OSError):
                pass

    def should_alert(self, hit: Hit) -> bool:
        """Alert only when a product becomes available, or its known quantity goes up."""
        if not hit.status.available:
            return False
        prev = self.items.get(hit.key)
        if prev is None:
            return True
        prev_status = Stock(prev["status"])
        if not prev_status.available:
            return True
        prev_qty = prev.get("quantity")
        if hit.quantity is not None and prev_qty is not None and hit.quantity > prev_qty:
            return True
        return False

    def record(self, hit: Hit) -> None:
        # An UNKNOWN reading never overwrites a known one (avoids false re-alerts).
        prev = self.items.get(hit.key)
        if hit.status == Stock.UNKNOWN and prev is not None:
            return
        self.items[hit.key] = {
            "status": hit.status.value,
            "quantity": hit.quantity,
            "retailer": hit.retailer,
            "product": hit.product_name,
            "store": hit.store_name,
            "updated": int(time.time()),
        }

    def mark_missing_as_out(self, retailer: str, seen_keys: set[str]) -> None:
        """For sources that only list in-stock stores (Best Buy, Shopify)."""
        for key, item in self.items.items():
            if item.get("retailer") == retailer and key not in seen_keys:
                if Stock(item["status"]).available:
                    item["status"] = Stock.OUT.value
                    item["quantity"] = None
                    item["updated"] = int(time.time())

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"items": self.items, "source_failures": self.source_failures}, f, indent=1)
        os.replace(tmp, self.path)
