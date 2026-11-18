"""Local card shops that run their website on Shopify.

Every Shopify store publishes /products.json. Its 'available' flag is the shop's
own inventory, so treat it as 'in stock at the shop – call to confirm'.
"""
from __future__ import annotations

import logging

import requests

from ..filters import is_pokemon_tcg
from ..models import Hit, Stock

log = logging.getLogger("shopify")


class ShopifySource:
    name = "Local card shops"
    lists_only_in_stock = False

    def __init__(self, cfg: dict, home: dict, session: requests.Session | None = None):
        self.shops = cfg.get("shops", [])
        self.home = home
        self.s = session or requests.Session()

    def run(self) -> list[Hit]:
        hits = []
        for shop in self.shops:
            base = shop["url"].rstrip("/")
            try:
                r = self.s.get(f"{base}/products.json", params={"limit": 250}, timeout=20,
                               headers={"User-Agent": "Mozilla/5.0 restock-monitor"})
                r.raise_for_status()
                products = r.json().get("products", [])
            except (requests.RequestException, ValueError) as e:
                log.warning("Shop %s failed: %s", shop["name"], e)
                continue
            for p in products:
                title = p.get("title", "")
                ptype = (p.get("product_type") or "").lower()
                sealed_type = any(w in ptype for w in ("sealed", "booster", "tcg", "card"))
                if not (is_pokemon_tcg(title) or ("pokemon" in title.lower() and sealed_type)):
                    continue
                variants = p.get("variants", [])
                available = any(v.get("available") for v in variants)
                prices = [float(v["price"]) for v in variants if v.get("price")]
                hits.append(Hit(
                    retailer=shop["name"], store_id=base, store_name=shop["name"],
                    address=shop.get("address", ""), product_id=str(p.get("id")),
                    product_name=title, price=min(prices) if prices else None,
                    status=Stock.IN_STOCK if available else Stock.OUT,
                    url=f"{base}/products/{p.get('handle')}",
                    lat=shop.get("lat"), lon=shop.get("lon"),
                    availability_note="In stock at shop – call to confirm / hold",
                ))
        return hits
