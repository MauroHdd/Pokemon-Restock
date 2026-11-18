"""Best Buy via its official developer API (free key from developer.bestbuy.com).

The store-availability endpoint returns only the stores where a SKU can be
picked up today, so any store that drops off the list is treated as out of stock.
"""
from __future__ import annotations

import logging
import os
import time

import requests

from ..filters import is_pokemon_tcg
from ..models import Hit, Stock

log = logging.getLogger("bestbuy")
API = "https://api.bestbuy.com/v1"


class BestBuySource:
    name = "Best Buy"
    lists_only_in_stock = True

    def __init__(self, cfg: dict, home: dict, session: requests.Session | None = None):
        self.cfg = cfg
        self.home = home
        self.s = session or requests.Session()
        self.key = os.getenv("BESTBUY_API_KEY", "")

    def _get(self, path, params):
        params = {**params, "apiKey": self.key, "format": "json"}
        for attempt in range(3):
            r = self.s.get(f"{API}{path}", params=params, timeout=20)
            if r.status_code == 429:  # rate limit: 5 calls/sec
                time.sleep(1 + attempt)
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()

    def products(self) -> list[dict]:
        data = self._get("/products(search=pokemon&search=card)", {
            "show": "sku,name,salePrice,regularPrice,url,inStoreAvailability",
            "pageSize": 100,
        })
        return [p for p in data.get("products", []) if is_pokemon_tcg(p.get("name", ""))]

    def run(self) -> list[Hit]:
        if not self.key:
            raise RuntimeError("BESTBUY_API_KEY not set")
        hits = []
        prods = self.products()
        log.info("Best Buy: %d Pokemon TCG SKUs", len(prods))
        for p in prods:
            data = self._get(f"/products/{p['sku']}/stores.json",
                             {"postalCode": self.home["zip"]})
            time.sleep(0.25)
            for st in data.get("stores", []):
                dist = st.get("distance")
                if dist is not None and float(dist) > self.home["radius_miles"]:
                    continue
                hits.append(Hit(
                    retailer="Best Buy", store_id=str(st.get("storeID")),
                    store_name=st.get("name", "Best Buy"),
                    address=", ".join(x for x in [st.get("address"), st.get("city"),
                                                  st.get("state"), st.get("postalCode")] if x),
                    product_id=str(p["sku"]), product_name=p["name"],
                    price=p.get("salePrice") or p.get("regularPrice"),
                    status=Stock.LIMITED if st.get("lowStock") else Stock.IN_STOCK,
                    url=p.get("url") or f"https://www.bestbuy.com/site/{p['sku']}.p",
                    distance_mi=float(dist) if dist is not None else None,
                    availability_note="Store pickup today",
                ))
        return hits
