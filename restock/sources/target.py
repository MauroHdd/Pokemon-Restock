"""Target store inventory via the same 'redsky' JSON endpoints target.com's own pages use.

These are unofficial: Target can change field names or block traffic at any time.
Parsing is deliberately defensive and anything we can't read becomes UNKNOWN
(which never triggers an alert).
"""
from __future__ import annotations

import logging
import random
import time

import requests

from ..filters import is_pokemon_tcg
from ..models import Hit, Stock

log = logging.getLogger("target")

BASE = "https://redsky.target.com/redsky_aggregations/v1/web"
WEB_KEY = "9f36aeafbe60771e321a7cc95a78140772ab3e96"  # public key embedded in target.com
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://www.target.com",
    "Referer": "https://www.target.com/",
}

STATUS_MAP = {
    "IN_STOCK": Stock.IN_STOCK,
    "LIMITED_STOCK": Stock.LIMITED,
    "OUT_OF_STOCK": Stock.OUT,
    "UNAVAILABLE": Stock.OUT,
    "NOT_SOLD_IN_STORE": Stock.OUT,
}


def _get(session, url, params):
    r = session.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def _dig(d, *path, default=None):
    for p in path:
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and isinstance(p, int) and len(d) > p:
            d = d[p]
        else:
            return default
    return default if d is None else d


class TargetSource:
    name = "Target"

    def __init__(self, cfg: dict, home: dict, session: requests.Session | None = None):
        self.cfg = cfg
        self.home = home
        self.s = session or requests.Session()
        self.visitor = "".join(random.choice("0123456789ABCDEF") for _ in range(32))

    def stores(self) -> list[dict]:
        data = _get(self.s, f"{BASE}/nearby_stores_v1", {
            "key": WEB_KEY, "limit": 20, "within": self.home["radius_miles"],
            "place": self.home["zip"],
        })
        out = []
        for st in _dig(data, "data", "nearby_stores", "stores", default=[]):
            addr = st.get("mailing_address") or {}
            out.append({
                "id": str(st.get("store_id") or st.get("location_id")),
                "name": st.get("location_name") or "Target",
                "address": ", ".join(x for x in [
                    addr.get("address_line1"), addr.get("city"),
                    addr.get("region") or addr.get("state"), addr.get("postal_code"),
                ] if x),
                "distance": st.get("distance"),
            })
        return [s for s in out if s["id"] and s["id"] != "None"]

    def search(self, store_ids: list[str]) -> list[dict]:
        products, seen = [], set()
        for kw in self.cfg.get("keywords", ["pokemon cards"]):
            for offset in range(0, 24 * self.cfg.get("max_pages", 3), 24):
                data = _get(self.s, f"{BASE}/plp_search_v2", {
                    "key": WEB_KEY, "channel": "WEB", "count": 24, "offset": offset,
                    "keyword": kw, "page": f"/s/{kw}", "default_purchasability_filter": "false",
                    "pricing_store_id": store_ids[0],
                    "visitor_id": self.visitor,
                })
                batch = _dig(data, "data", "search", "products", default=[])
                titles = [_dig(p, "item", "product_description", "title", default="") for p in batch]
                log.info("Target search %r offset %d: %d raw results, sample=%s, errors=%s, keys=%s",
                         kw, offset, len(batch), titles[:3], str(data.get("errors"))[:200],
                         list((_dig(data, "data", "search", default={}) or {}).keys())[:8])
                for p in batch:
                    tcin = str(p.get("tcin"))
                    title = _dig(p, "item", "product_description", "title", default="")
                    title = title.replace("&#233;", "é").replace("&#38;", "&")
                    if tcin in seen or not is_pokemon_tcg(title):
                        continue
                    seen.add(tcin)
                    products.append({
                        "tcin": tcin,
                        "title": title,
                        "price": _dig(p, "price", "current_retail")
                        or _dig(p, "price", "reg_retail"),
                        "url": _dig(p, "item", "enrichment", "buy_url",
                                    default=f"https://www.target.com/p/-/A-{tcin}"),
                    })
                if len(batch) < 24:
                    break
                time.sleep(0.5)
        return products

    def fulfillment(self, tcins: list[str], store: dict) -> dict[str, tuple[Stock, int | None, str]]:
        result = {}
        for i in range(0, len(tcins), 20):
            chunk = tcins[i:i + 20]
            data = _get(self.s, f"{BASE}/product_summary_with_fulfillment_v1", {
                "key": WEB_KEY, "channel": "WEB", "tcins": ",".join(chunk),
                "store_id": store["id"], "required_store_id": store["id"],
                "has_required_store_id": "true", "zip": self.home["zip"],
                "state": "FL", "latitude": self.home["lat"], "longitude": self.home["lon"],
                "visitor_id": self.visitor,
            })
            for summ in _dig(data, "data", "product_summaries", default=[]):
                tcin = str(summ.get("tcin"))
                opts = _dig(summ, "fulfillment", "store_options", default=[])
                opt = next((o for o in opts if str(o.get("location_id")) == store["id"]),
                           opts[0] if opts else None)
                result[tcin] = self._parse_option(opt)
            time.sleep(0.4)
        return result

    @staticmethod
    def _parse_option(opt) -> tuple[Stock, int | None, str]:
        if not opt:
            return Stock.UNKNOWN, None, ""
        pickup = STATUS_MAP.get(_dig(opt, "order_pickup", "availability_status", default=""))
        shelf = STATUS_MAP.get(_dig(opt, "in_store_only", "availability_status", default=""))
        qty = opt.get("location_available_to_promise_quantity")
        qty = int(qty) if isinstance(qty, (int, float)) and qty >= 0 else None
        if pickup and pickup.available:
            return pickup, qty, "Order pickup available"
        if shelf and shelf.available:
            return shelf, qty, "On the shelf in store"
        if pickup or shelf:
            return Stock.OUT, qty, ""
        return Stock.UNKNOWN, qty, ""

    def run(self) -> list[Hit]:
        stores = self.stores()
        if not stores:
            raise RuntimeError("no Target stores returned")
        products = self.search([s["id"] for s in stores])
        log.info("Target: %d stores, %d Pokemon TCG products", len(stores), len(products))
        hits = []
        for store in stores:
            fl = self.fulfillment([p["tcin"] for p in products], store)
            for p in products:
                status, qty, note = fl.get(p["tcin"], (Stock.UNKNOWN, None, ""))
                hits.append(Hit(
                    retailer="Target", store_id=store["id"], store_name=store["name"],
                    address=store["address"], product_id=p["tcin"], product_name=p["title"],
                    price=float(p["price"]) if p["price"] else None, status=status,
                    quantity=qty, url=p["url"], distance_mi=store["distance"],
                    availability_note=note or "In-store pickup",
                ))
        return hits
