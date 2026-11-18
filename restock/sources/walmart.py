"""Walmart – EXPERIMENTAL.

Reads walmart.com's search page for each local store. Walmart actively blocks
automated traffic ("Robot or human?"), especially from cloud servers, so this
may stop working at any time. When blocked, it raises an error: the monitor
skips Walmart for that run and keeps checking every other store.
Only items sold by Walmart itself with in-store pickup evidence count.
"""
from __future__ import annotations

import json
import logging
import random
import re
import time

import requests

from ..filters import is_pokemon_tcg
from ..models import Hit, Stock

log = logging.getLogger("walmart")

SEARCH = "https://www.walmart.com/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class WalmartBlocked(RuntimeError):
    pass


def _price(item):
    pi = item.get("priceInfo") or {}
    for v in (item.get("price"), (pi.get("currentPrice") or {}).get("price"),
              pi.get("linePrice"), pi.get("itemPrice")):
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            m = re.search(r"[\d,]+\.\d{2}", v)
            if m:
                return float(m.group().replace(",", ""))
    return None


def parse_items(html: str) -> list[dict]:
    if "Robot or human" in html or "px-captcha" in html:
        raise WalmartBlocked("Walmart showed a robot check")
    m = NEXT_DATA.search(html)
    if not m:
        raise WalmartBlocked("Walmart page had no product data (likely blocked)")
    data = json.loads(m.group(1))
    stacks = (data.get("props", {}).get("pageProps", {}).get("initialData", {})
              .get("searchResult", {}).get("itemStacks", [])) or []
    return [it for st in stacks for it in (st.get("items") or []) if isinstance(it, dict)]


def classify(item: dict) -> tuple[Stock, int | None]:
    avail = ((item.get("availabilityStatusV2") or {}).get("value")
             or item.get("availabilityStatus") or "").upper()
    fulfil = json.dumps([item.get("fulfillmentBadgeGroups"), item.get("fulfillmentSummary"),
                         item.get("fulfillmentBadge"), item.get("fulfillmentType")]).lower()
    qty = None
    m = re.search(r"only (\d+) left", json.dumps(item).lower())
    if m:
        qty = int(m.group(1))
    if "OUT_OF_STOCK" in avail:
        return Stock.OUT, None
    pickup = "pickup" in fulfil or "in-store" in fulfil or "in store" in fulfil
    if avail == "IN_STOCK" and pickup:
        return (Stock.LIMITED if qty is not None and qty <= 3 else Stock.IN_STOCK), qty
    return Stock.UNKNOWN, qty


class WalmartSource:
    name = "Walmart"
    lists_only_in_stock = False

    def __init__(self, cfg: dict, home: dict, session: requests.Session | None = None):
        self.cfg = cfg
        self.home = home
        self.s = session or requests.Session()

    def check_store(self, store: dict) -> list[Hit]:
        r = self.s.get(SEARCH, headers=HEADERS, timeout=25, params={
            "q": self.cfg.get("keyword", "pokemon trading cards"),
            "facet": "fulfillment_method_in_store:In-store",
            "affinityOverride": "store_specific",
        }, cookies={"assortmentStoreId": str(store["id"]), "hasLocData": "1"})
        if r.status_code in (403, 412, 429) or "/blocked" in getattr(r, "url", ""):
            raise WalmartBlocked(f"Walmart refused the request (HTTP {r.status_code})")
        hits = []
        for it in parse_items(r.text):
            name = it.get("name") or ""
            seller = (it.get("sellerName") or "Walmart.com").lower()
            if "walmart" not in seller or not is_pokemon_tcg(name):
                continue  # skip marketplace resellers
            status, qty = classify(it)
            url = it.get("canonicalUrl") or f"/ip/{it.get('usItemId')}"
            hits.append(Hit(
                retailer="Walmart", store_id=str(store["id"]), store_name=store["name"],
                address=store["address"], product_id=str(it.get("usItemId") or it.get("id")),
                product_name=name, price=_price(it), status=status, quantity=qty,
                url=("https://www.walmart.com" + url) if url.startswith("/") else url,
                lat=store.get("lat"), lon=store.get("lon"),
                availability_note="In store / pickup at this Walmart",
            ))
        return hits

    def run(self) -> list[Hit]:
        hits = []
        for store in self.cfg.get("stores", []):
            hits += self.check_store(store)   # a block on any store stops Walmart for this run
            time.sleep(random.uniform(2, 5))
        log.info("Walmart: %d Pokemon TCG listings across %d stores",
                 len(hits), len(self.cfg.get("stores", [])))
        return hits
