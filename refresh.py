#!/usr/bin/env python3
"""Refresh resale values and regenerate data.js for the purse tracker.

Usage:
    python3 refresh.py                 # regenerate data.js from the stores only
    python3 refresh.py --fetch         # pull eBay comps, append a snapshot, regenerate
    python3 refresh.py --fetch --dry   # show what would be fetched, write nothing

Stores (data/):
    bags.json     canonical collection — one entry per bag (hand-edit freely)
    history.json  { bag_id: [{date, value}, ...] } value snapshots over time
Output:
    data.js       window.PURSE_DATA payload the dashboard reads

eBay credentials (only needed for --fetch) are read from, in order:
    1. config.json  (gitignored)  { "appId": "...", "certId": "...", ... }
    2. env vars     EBAY_APP_ID / EBAY_CERT_ID
See config.example.json for the template.

Value source:
    Until you're approved for eBay's Marketplace Insights API (actual SOLD
    prices), --fetch uses the Browse API (active listing ASKING prices) and
    takes the median, which runs a bit high. Set "useSold": true in config.json
    once approved to switch to true sold comps — the rest is identical.
"""
import base64
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
BAGS_STORE = DATA / "bags.json"
HISTORY_STORE = DATA / "history.json"
WISHLIST_STORE = DATA / "wishlist.json"
DATA_JS = ROOT / "data.js"
CONFIG = ROOT / "config.json"

# Fewer than this many comps = too thin a sample to trust; the estimate is
# excluded (no snapshot recorded) rather than logging a misleading value.
MIN_COMPS = 3

OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
INSIGHTS_URL = "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"


# ---------- stores ----------
def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def today():
    return date.today().isoformat()


# ---------- eBay credentials ----------
def load_config():
    import os
    cfg = {"appId": "", "certId": "", "marketplace": "EBAY_US", "useSold": False}
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text()))
    cfg["appId"] = cfg["appId"] or os.environ.get("EBAY_APP_ID", "")
    cfg["certId"] = cfg["certId"] or os.environ.get("EBAY_CERT_ID", "")
    return cfg


def get_token(cfg):
    """Client-credentials OAuth token for the Buy/Browse APIs."""
    creds = base64.b64encode(f"{cfg['appId']}:{cfg['certId']}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode()
    req = urllib.request.Request(
        OAUTH_URL, data=body,
        headers={"Authorization": f"Basic {creds}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def api_get(url, token, params, marketplace):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{q}",
        headers={"Authorization": f"Bearer {token}",
                 "X-EBAY-C-MARKETPLACE-ID": marketplace,
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def prices_from_browse(payload):
    out = []
    for it in payload.get("itemSummaries", []) or []:
        p = (it.get("price") or {}).get("value")
        if p is not None:
            out.append(float(p))
    return out


def prices_from_insights(payload):
    out = []
    for it in payload.get("itemSales", []) or []:
        p = (it.get("lastSoldPrice") or {}).get("value")
        if p is not None:
            out.append(float(p))
    return out


def trimmed_median(prices):
    """Median after dropping the cheapest/most-expensive 15% to shed junk
    (broken listings, mispriced fakes, bundles). Needs a few data points."""
    xs = sorted(prices)
    if len(xs) >= 7:
        k = max(1, int(len(xs) * 0.15))
        xs = xs[k:-k]
    return round(statistics.median(xs)) if xs else None


def estimate_value(bag, token, cfg):
    """Return (estimate, n_comps) for one bag, or (None, 0)."""
    query = bag.get("ebayQuery") or f"{bag['brand']} {bag['model']}"
    if cfg.get("useSold"):
        payload = api_get(INSIGHTS_URL, token,
                          {"q": query, "limit": 50}, cfg["marketplace"])
        prices = prices_from_insights(payload)
    else:
        payload = api_get(BROWSE_URL, token,
                          {"q": query, "limit": 50,
                           "filter": "buyingOptions:{FIXED_PRICE},conditionIds:{3000|4000|5000|6000}"},
                          cfg["marketplace"])
        prices = prices_from_browse(payload)
    return trimmed_median(prices), len(prices)


# ---------- actions ----------
def fetch(dry=False):
    cfg = load_config()
    bags = load(BAGS_STORE, [])
    if not dry and not (cfg["appId"] and cfg["certId"]):
        sys.exit("No eBay credentials. Add config.json (see config.example.json) "
                 "or set EBAY_APP_ID / EBAY_CERT_ID, or run with --dry.")

    source = "SOLD (Marketplace Insights)" if cfg.get("useSold") else "ACTIVE asking (Browse)"
    print(f"Fetching resale comps · source: {source}"
          + ("  [DRY RUN]" if dry else ""))

    if dry:
        for b in bags:
            print(f"  {b['brand']} {b['model']:22}  q=\"{b.get('ebayQuery') or ''}\"")
        print(f"\n{len(bags)} bags would be queried. No credentials used, nothing written.")
        return

    token = get_token(cfg)
    history = load(HISTORY_STORE, {})
    stamp = today()
    updated = skipped = 0
    for b in bags:
        if b.get("archived"):  # sold / let go — no comps needed
            continue
        if b.get("manualValue") is not None:
            print(f"  {b['brand']} {b['model']:22}  manual override ${b['manualValue']:,} (skipped fetch)")
            val = b["manualValue"]
        else:
            try:
                val, n = estimate_value(b, token, cfg)
            except Exception as e:  # keep going if one bag fails
                print(f"  {b['brand']} {b['model']:22}  ERROR {e}")
                skipped += 1
                continue
            if val is None or n < MIN_COMPS:
                reason = ("no comps found" if val is None
                          else f"only {n} comps (<{MIN_COMPS}, too few to trust)")
                print(f"  {b['brand']} {b['model']:22}  {reason} — excluded")
                # drop any stale snapshot for today so a weak value doesn't linger
                stale = history.get(b["id"])
                if stale:
                    stale[:] = [s for s in stale if s["date"] != stamp]
                skipped += 1
                continue
            print(f"  {b['brand']} {b['model']:22}  ${val:,}  ({n} comps)")
        series = history.setdefault(b["id"], [])
        # one snapshot per day: replace today's if re-run
        series[:] = [s for s in series if s["date"] != stamp]
        series.append({"date": stamp, "value": val})
        series.sort(key=lambda s: s["date"])
        updated += 1
        time.sleep(0.4)  # be gentle on the API

    HISTORY_STORE.write_text(json.dumps(history, indent=1) + "\n")
    print(f"\nhistory: {updated} bags updated, {skipped} skipped -> snapshot {stamp}")
    regenerate()


def current_value(bag, history):
    """manualValue wins; else the latest history snapshot; else None."""
    if bag.get("manualValue") is not None:
        return bag["manualValue"]
    series = history.get(bag["id"]) or []
    return series[-1]["value"] if series else None


def import_bundle(path):
    """Fold a purse-data.json exported from the dashboard back into the stores.

    Bundle shape: {"bags": [...], "history": {...}, "wishlist": [...]}.
    This is the round-trip: edit in the browser -> Export -> import here to
    make it permanent (and committable)."""
    bundle = json.loads(Path(path).read_text())
    DATA.mkdir(exist_ok=True)
    if "bags" in bundle:
        BAGS_STORE.write_text(json.dumps(bundle["bags"], indent=2) + "\n")
    if "history" in bundle:
        HISTORY_STORE.write_text(json.dumps(bundle["history"], indent=1) + "\n")
    if "wishlist" in bundle:
        WISHLIST_STORE.write_text(json.dumps(bundle["wishlist"], indent=2) + "\n")
    print(f"imported {path}: {len(bundle.get('bags', []))} bags, "
          f"{len(bundle.get('wishlist', []))} wishlist items")
    regenerate()


def regenerate():
    bags = load(BAGS_STORE, [])
    history = load(HISTORY_STORE, {})
    wishlist = load(WISHLIST_STORE, [])
    payload = {"generatedAt": today(), "bags": bags, "history": history, "wishlist": wishlist}
    DATA_JS.write_text("window.PURSE_DATA = " + json.dumps(payload, separators=(",", ":")) + ";\n")

    active = [b for b in bags if not b.get("archived")]
    archived = [b for b in bags if b.get("archived")]
    total = sum(current_value(b, history) or 0 for b in active)
    invested = sum(b.get("pricePaid") or 0 for b in active if current_value(b, history) is not None)
    priced = [b for b in active if b.get("pricePaid") and current_value(b, history) is not None]
    gain = sum((current_value(b, history) - b["pricePaid"]) for b in priced)
    realized = sum((b["soldPrice"] - b["pricePaid"]) for b in archived
                   if b.get("soldPrice") is not None and b.get("pricePaid") is not None)
    line = (f"store: {len(active)} active bags · resale ${total:,} · invested ${invested:,} · "
            f"unrealized {'+' if gain >= 0 else ''}${gain:,}")
    if archived:
        line += f" · {len(archived)} archived · realized {'+' if realized >= 0 else ''}${realized:,}"
    print(line)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--import" in args:
        i = args.index("--import")
        if i + 1 >= len(args):
            sys.exit("Usage: python3 refresh.py --import purse-data.json")
        import_bundle(args[i + 1])
    elif "--fetch" in args:
        fetch(dry="--dry" in args)
    else:
        regenerate()
