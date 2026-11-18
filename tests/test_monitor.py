import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import monitor  # noqa: E402
from restock.filters import at_msrp, category, is_pokemon_tcg, is_priority  # noqa: E402
from restock.geo import miles_between  # noqa: E402
from restock.models import Hit, Stock  # noqa: E402
from restock.sources.bestbuy import BestBuySource  # noqa: E402
from restock.sources.target import TargetSource  # noqa: E402
from restock.state import State  # noqa: E402

CFG = monitor.load_config(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
HOME = CFG["home"]


class FakeResp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, params=None, **kw):
        for frag, data in self.routes.items():
            if frag in url:
                return FakeResp(data(params) if callable(data) else data)
        raise AssertionError("unexpected url " + url)


# ---------- filters ----------
def test_filters():
    assert is_pokemon_tcg("Pokémon TCG: Scarlet & Violet Elite Trainer Box")
    assert is_pokemon_tcg("Pokemon Trading Card Game 30th Anniversary Booster Bundle")
    assert not is_pokemon_tcg("Pokemon Pikachu 12in Plush")
    assert not is_pokemon_tcg("Pokemon Legends Z-A - Nintendo Switch")
    assert not is_pokemon_tcg("Magic the Gathering Booster Bundle")
    assert category("Pokemon TCG Elite Trainer Box") == "Elite Trainer Box"
    assert category("Pokemon TCG Booster Bundle") == "Booster Bundle"
    assert category("Pokemon TCG Charizard Tin") == "Tin"
    assert is_priority("Pokemon 30th Anniversary Collection", ["Elite Trainer Box"])
    assert at_msrp("Pokemon TCG Elite Trainer Box", 59.99, CFG["msrp"], 0.05) is True
    assert at_msrp("Pokemon TCG Elite Trainer Box", 89.99, CFG["msrp"], 0.05) is False


def test_distance():
    # Gulf Breeze -> downtown Pensacola is ~5–6 miles
    d = miles_between(HOME["lat"], HOME["lon"], 30.4213, -87.2169)
    assert 4 < d < 8


# ---------- state / dedup ----------
def _hit(status, qty=None, store="1"):
    return Hit("Target", store, "Pensacola", "addr", "123", "Pokemon TCG ETB", 59.99,
               status, "http://x", quantity=qty, distance_mi=10)


def test_dedup(tmp_path):
    st = State(str(tmp_path / "s.json"))
    h = _hit(Stock.IN_STOCK, 3)
    assert st.should_alert(h)
    st.record(h)
    assert not st.should_alert(_hit(Stock.IN_STOCK, 3))      # same -> no repeat
    assert not st.should_alert(_hit(Stock.LIMITED, 2))       # dropped -> no repeat
    assert st.should_alert(_hit(Stock.IN_STOCK, 6))          # qty went up -> alert
    st.record(_hit(Stock.OUT))
    assert st.should_alert(_hit(Stock.IN_STOCK, 1))          # restocked -> alert
    assert not st.should_alert(_hit(Stock.UNKNOWN))          # unknown never alerts
    st.record(_hit(Stock.IN_STOCK, 1))
    st.record(_hit(Stock.UNKNOWN))                           # unknown doesn't overwrite
    assert st.items[_hit(Stock.IN_STOCK).key]["status"] == Stock.IN_STOCK.value
    st.save()
    assert State(str(tmp_path / "s.json")).items


# ---------- Target parsing ----------
TARGET_ROUTES = {
    "nearby_stores_v1": {"data": {"nearby_stores": {"stores": [
        {"store_id": "1111", "location_name": "Pensacola", "distance": 9.8,
         "mailing_address": {"address_line1": "1 Mall Rd", "city": "Pensacola",
                             "region": "FL", "postal_code": "32504"}},
    ]}}},
    "plp_search_v2": {"data": {"search": {"products": [
        {"tcin": "900", "price": {"current_retail": 29.99},
         "item": {"product_description": {"title": "Pokémon TCG 30th Anniversary Booster Bundle"},
                  "enrichment": {"buy_url": "https://www.target.com/p/-/A-900"}}},
        {"tcin": "901", "price": {"current_retail": 59.99},
         "item": {"product_description": {"title": "Pokemon TCG Elite Trainer Box"}}},
        {"tcin": "902", "price": {"current_retail": 19.99},
         "item": {"product_description": {"title": "Pokemon Pikachu Plush"}}},
    ]}}},
    "product_summary_with_fulfillment_v1": {"data": {"product_summaries": [
        {"tcin": "900", "fulfillment": {"store_options": [
            {"location_id": "1111", "location_available_to_promise_quantity": 4,
             "order_pickup": {"availability_status": "IN_STOCK"}}]}},
        {"tcin": "901", "fulfillment": {"store_options": [
            {"location_id": "1111", "order_pickup": {"availability_status": "OUT_OF_STOCK"},
             "in_store_only": {"availability_status": "OUT_OF_STOCK"}}]}},
    ]}},
}


def test_target_source():
    src = TargetSource(CFG["sources"]["target"] | {"keywords": ["pokemon"], "max_pages": 1},
                       HOME, session=FakeSession(TARGET_ROUTES))
    hits = {h.product_id: h for h in src.run()}
    assert set(hits) == {"900", "901"}                 # plush filtered out
    assert hits["900"].status == Stock.IN_STOCK and hits["900"].quantity == 4
    assert hits["901"].status == Stock.OUT
    assert hits["900"].address == "1 Mall Rd, Pensacola, FL, 32504"


# ---------- Best Buy parsing ----------
def test_bestbuy_source(monkeypatch):
    monkeypatch.setenv("BESTBUY_API_KEY", "k")
    routes = {
        "/stores.json": {"stores": [
            {"storeID": 55, "name": "Pensacola", "address": "7171 N Davis Hwy",
             "city": "Pensacola", "state": "FL", "postalCode": "32504", "distance": 12.1,
             "lowStock": True},
            {"storeID": 99, "name": "Far Away", "distance": 120.0}]},
        "/products(": {"products": [
            {"sku": 6543, "name": "Pokémon TCG: Elite Trainer Box", "salePrice": 59.99,
             "url": "https://bestbuy.com/x"}]},
    }
    hits = BestBuySource({}, HOME, session=FakeSession(routes)).run()
    assert len(hits) == 1 and hits[0].status == Stock.LIMITED


# ---------- end to end ----------
def test_end_to_end(tmp_path, monkeypatch, capsys):
    import restock.sources.target as t
    monkeypatch.setattr(t.requests, "Session", lambda: FakeSession(TARGET_ROUTES))
    monkeypatch.setattr(t.time, "sleep", lambda s: None)
    cfg = CFG | {"sources": {"target": {"enabled": True, "keywords": ["pokemon"], "max_pages": 1}}}
    state = State(str(tmp_path / "s.json"))
    n = monitor.Notifier(dry_run=True)
    assert monitor.check_once(cfg, state, n) == 1
    out = capsys.readouterr().out
    assert "30th Anniversary Booster Bundle" in out and "PRIORITY" in out
    assert "$29.99 (MSRP)" in out and "Quantity: 4" in out
    assert monitor.check_once(cfg, state, n) == 0       # no duplicate text


# ---------- Walmart parsing ----------
def test_walmart():
    import json as _j
    import pytest
    from restock.sources.walmart import WalmartBlocked, WalmartSource, parse_items
    page = {"props": {"pageProps": {"initialData": {"searchResult": {"itemStacks": [{"items": [
        {"usItemId": "55", "name": "Pokemon TCG Elite Trainer Box", "price": 49.97,
         "canonicalUrl": "/ip/x/55", "availabilityStatusV2": {"value": "IN_STOCK"},
         "fulfillmentBadgeGroups": [{"text": "Pickup today"}], "sellerName": "Walmart.com"},
        {"usItemId": "56", "name": "Pokemon TCG Booster Bundle", "price": 99.0,
         "availabilityStatusV2": {"value": "IN_STOCK"}, "sellerName": "CardFlipper LLC"},
        {"usItemId": "57", "name": "Pokemon TCG Booster Bundle", "price": 29.97,
         "availabilityStatusV2": {"value": "OUT_OF_STOCK"}, "sellerName": "Walmart.com"},
    ]}]}}}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{_j.dumps(page)}</script>'

    class R:
        status_code, url, text = 200, "https://www.walmart.com/search", html

    class S:
        def get(self, *a, **k):
            return R()

    store = CFG["sources"]["walmart"]["stores"][0]
    hits = {h.product_id: h for h in WalmartSource({}, HOME, S()).check_store(store)}
    assert set(hits) == {"55", "57"}                      # reseller skipped
    assert hits["55"].status == Stock.IN_STOCK and hits["55"].price == 49.97
    assert hits["57"].status == Stock.OUT
    with pytest.raises(WalmartBlocked):
        parse_items("<html>Robot or human?</html>")
