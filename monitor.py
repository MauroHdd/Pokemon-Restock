#!/usr/bin/env python3
"""Pokemon TCG restock monitor – checks sources, texts you on new local stock.

  python monitor.py --once          one check (used by GitHub Actions)
  python monitor.py --loop          run forever (used by Docker / a server)
  python monitor.py --once --dry-run   print alerts instead of texting
  python monitor.py --test-sms      send one test text
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time

import yaml

from restock.filters import at_msrp, is_priority
from restock.geo import miles_between
from restock.models import Hit
from restock.notify import Notifier, format_alert
from restock.sources.bestbuy import BestBuySource
from restock.sources.shopify import ShopifySource
from restock.sources.target import TargetSource
from restock.sources.walmart import WalmartSource
from restock.state import State

SOURCES = {"target": TargetSource, "walmart": WalmartSource, "bestbuy": BestBuySource, "shopify": ShopifySource}
log = logging.getLogger("monitor")


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def fill_distance(hit: Hit, home: dict) -> None:
    if hit.distance_mi is None and hit.lat is not None and hit.lon is not None:
        hit.distance_mi = miles_between(home["lat"], home["lon"], hit.lat, hit.lon)


def check_once(cfg: dict, state: State, notifier: Notifier) -> int:
    home = cfg["home"]
    alerts: list[tuple[bool, Hit, bool | None]] = []
    for key, src_cls in SOURCES.items():
        scfg = cfg["sources"].get(key, {})
        if not scfg.get("enabled"):
            continue
        if key == "bestbuy" and not os.getenv("BESTBUY_API_KEY"):
            continue  # Best Buy is optional: skipped quietly when there's no key
        src = src_cls(scfg, home)
        try:
            hits = src.run()
        except Exception as e:  # one broken retailer must never stop the others
            log.error("%s failed: %s", src.name, e)
            fail = state.source_failures.setdefault(key, {"count": 0, "warned": 0})
            fail["count"] += 1
            threshold = cfg["alerts"].get("source_failure_warn_after", 12)
            if scfg.get("warn_on_failure", True) and fail["count"] >= threshold and time.time() - fail["warned"] > 86400:
                notifier.send(f"⚠️ Restock monitor: {src.name} checks have failed "
                              f"{fail['count']} times in a row ({str(e)[:80]}). "
                              f"Alerts for {src.name} may be missed.")
                fail["warned"] = time.time()
            continue
        state.source_failures[key] = {"count": 0, "warned": 0}

        seen = set()
        for hit in hits:
            fill_distance(hit, home)
            if hit.distance_mi is not None and hit.distance_mi > home["radius_miles"]:
                continue
            seen.add(hit.key)
            if state.should_alert(hit):
                prio = is_priority(hit.product_name, cfg["alerts"]["priority_categories"])
                msrp = at_msrp(hit.product_name, hit.price, cfg["msrp"],
                               cfg["alerts"]["msrp_tolerance"])
                if cfg["alerts"].get("only_msrp") and msrp is False:
                    state.record(hit)
                    continue
                alerts.append((prio, hit, msrp))
            state.record(hit)
        if getattr(src, "lists_only_in_stock", False):
            state.mark_missing_as_out(hits[0].retailer if hits else src.name, seen)

    # Priority items (ETBs, booster bundles, 30th Anniversary) and MSRP first, closest first
    alerts.sort(key=lambda a: (not a[0], a[2] is not True, a[1].distance_mi or 999))
    cap = cfg["alerts"].get("max_texts_per_check", 8)
    for prio, hit, msrp in alerts[:cap]:
        notifier.send(format_alert(hit, prio, msrp), link=hit.url)
    if len(alerts) > cap:
        extra = alerts[cap:]
        lines = [f"- {h.product_name[:45]} @ {h.retailer} {h.store_name}" for _, h, _ in extra[:10]]
        notifier.send(f"🚨 +{len(extra)} more Pokémon restocks nearby:\n" + "\n".join(lines))
    state.save()
    log.info("Check done: %d new alerts", len(alerts))
    return len(alerts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--state", default=os.getenv("STATE_FILE", "state.json"))
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-sms", action="store_true")
    ap.add_argument("--check-shops", "--check-stores", dest="check_shops", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    load_dotenv()
    cfg = load_config(args.config)
    notifier = Notifier(dry_run=args.dry_run, ntfy_topic=cfg.get("ntfy_topic", ""))

    if args.check_shops:
        import requests
        for shop in cfg["sources"]["shopify"].get("shops", []):
            try:
                r = requests.get(shop["url"].rstrip("/") + "/products.json", timeout=20,
                                 headers={"User-Agent": "Mozilla/5.0 restock-monitor"})
                ok = r.status_code == 200 and "products" in r.json()
            except Exception:
                ok = False
            print(("✅ WORKS        " if ok else "❌ NOT SHOPIFY  ") + shop["name"])
        wcfg = cfg["sources"].get("walmart", {})
        if wcfg.get("enabled") and wcfg.get("stores"):
            try:
                n = len(WalmartSource(wcfg, cfg["home"]).check_store(wcfg["stores"][0]))
                print(f"✅ WORKS        Walmart (test store saw {n} Pokémon listings)")
            except Exception as e:
                print(f"❌ BLOCKED      Walmart – {e}")
        return 0

    if args.test_sms:
        ok = notifier.send("✅ Pokémon restock monitor is connected. You'll get alerts here "
                           "when stock appears within 50 miles of Gulf Breeze.")
        print("sent" if ok else "FAILED – check ntfy_topic in config.yaml")
        return 0 if ok else 1

    state = State(args.state)
    if args.loop:
        lo, hi = cfg["schedule"]["min_minutes"], cfg["schedule"]["max_minutes"]
        while True:
            try:
                check_once(cfg, state, notifier)
            except Exception:
                log.exception("check crashed; will retry")
            time.sleep(random.uniform(lo, hi) * 60)
    check_once(cfg, state, notifier)
    return 0


if __name__ == "__main__":
    sys.exit(main())
