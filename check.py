#!/usr/bin/env python3
"""Rent Check: finds new rental listings on wba.nl and pushes them to your phone.

Standard library only. Usage:
    python3 check.py            # check the newest pages, notify about new listings
    python3 check.py --all      # walk every page (used automatically on the first run)
    python3 check.py --dry-run  # print what would be sent, change nothing

Notifications go to Telegram when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
(see README.md). Without them, new listings are only printed.
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ----------------------------------------------------------------- settings --
BASE = "https://www.wba.nl"
STATE_FILE = Path(__file__).with_name("listings.json")
PAGES_PER_RUN = 2          # newest listings are first; 2 pages = the newest 24
MAX_PAGES = 30             # safety cap for --all
USER_AGENT = "Mozilla/5.0 (personal rent checker; low frequency)"

# Towns to watch: roughly 25 km around Apeldoorn, plus Deventer, Zwolle, Arnhem.
# Lower case. Edit freely; a listing matches when its town is in this set.
TOWNS = {
    # Apeldoorn and its villages
    "apeldoorn", "ugchelen", "beekbergen", "lieren", "loenen", "hoenderloo",
    "klarenbeek", "wenum wiesel", "beemte broekland", "hoog soeren",
    "radio kootwijk", "oosterhuizen",
    # north and west
    "vaassen", "emst", "epe", "oene", "heerde", "uddel", "garderen",
    "elspeet", "kootwijk", "harskamp", "otterlo",
    # east, towards the IJssel
    "twello", "teuge", "wilp", "voorst", "terwolde", "nijbroek", "bussloo",
    "steenenkamer", "welsum", "olst", "gorssel", "epse",
    # south
    "eerbeek", "hall", "brummen", "empe", "tonden", "zutphen", "warnsveld",
    "laag-soeren", "laag soeren", "dieren", "spankeren", "ellecom",
    "de steeg", "rheden", "velp",
    # the three cities
    "deventer", "diepenveen", "schalkhaar", "bathmen", "colmschate",
    "zwolle",
    "arnhem",
}
SKIP_TYPES = {"garagebox"}                 # property types you never want
SKIP_STATUSES = {"verhuurd", "verkocht"}   # no notification if already gone
MAX_RENT = None                            # e.g. 1500 to ignore pricier homes
# ------------------------------------------------------------------------------


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def text(fragment):
    """Strip tags and tidy whitespace."""
    out = html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", out).strip()


def first(pattern, s):
    m = re.search(pattern, s, re.S)
    return m.group(1) if m else ""


def normalise_town(raw):
    town = raw.strip().lower()
    # the site writes e.g. "VOORST GEM VOORST" (town + municipality)
    return town.split(" gem ")[0]


def parse_listings(page):
    """Return a list of dicts, one per listing card on an overview page."""
    listings = []
    for card in page.split('class="pandlist-container')[1:]:
        url = first(r"""href=["'](https?://[^"']+/nl/(?:huur|koop)woning/[^"']+)["']""", card)
        m = re.search(r"/nl/(huur|koop)woning/([^/]+)/.*-(\d+)-\d+$", url)
        if not m:
            continue
        specs = {
            text(k): text(v)
            for k, v in re.findall(
                r"<li>\s*<span>(.*?)</span>\s*<span>(.*?)</span>\s*</li>", card, re.S
            )
        }
        price_text = text(first(r'class="pand-price">(.*?)</div>', card))
        digits = re.sub(r"[^\d]", "", first(r"€\s*([\d.]+)", price_text))
        town_raw = text(first(r'class="pand-title">(.*?)</div>', card))
        listings.append({
            "id": int(m.group(3)),
            "source": "wba",
            "kind": "huur" if m.group(1) == "huur" else "koop",
            "type": specs.get("Type") or m.group(2),
            "town": normalise_town(town_raw).title(),
            "street": text(first(r'class="pand-address">(.*?)</div>', card)),
            "price": int(digits) if digits else None,
            "price_text": price_text,
            "status": text(first(r'class="pandstatus[^"]*">(.*?)</span>', card)),
            "area": specs.get("Woonoppervlakte", ""),
            "bedrooms": specs.get("Slaapkamers", ""),
            "interior": specs.get("Interieur", ""),
            "image": first(r"background-image:\s*url\('([^']+)'\)", card),
            "url": url,
        })
    return listings


def wanted(item):
    if item["kind"] != "huur":
        return False
    if item["town"].lower() not in TOWNS:
        return False
    if item["type"].lower() in SKIP_TYPES:
        return False
    if MAX_RENT and item["price"] and item["price"] > MAX_RENT:
        return False
    return True


def telegram(method, token, payload):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=30).read()


def notify(item, token, chat_id):
    """Send one listing to Telegram: photo, details and a button to the listing."""
    details = " · ".join(
        x for x in (item["type"], item["area"],
                    f'{item["bedrooms"]} slaapk.' if item["bedrooms"] else "",
                    item["interior"]) if x
    )
    price = item["price_text"].replace("Huurprijs ", "")
    caption = "\n".join([
        f'<b>{html.escape(item["town"])} · {html.escape(item["street"])}</b>',
        f"{html.escape(price)} per maand",
        html.escape(details),
        f'Status: {html.escape(item["status"] or "onbekend")}',
    ])
    common = {
        "chat_id": chat_id,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [[{"text": "Bekijk op wba.nl", "url": item["url"]}]]},
    }
    if item["image"]:
        try:
            telegram("sendPhoto", token, {**common, "photo": item["image"], "caption": caption})
            return
        except urllib.error.HTTPError:
            pass  # Telegram could not fetch the photo; fall back to text
    telegram("sendMessage", token, {**common, "text": caption})


def main(argv):
    dry_run = "--dry-run" in argv
    state = {"seen_ids": [], "listings": []}
    first_run = not STATE_FILE.exists()
    if not first_run:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    seen = set(state["seen_ids"])
    known = {l["id"]: l for l in state["listings"]}

    pages = MAX_PAGES if (first_run or "--all" in argv) else PAGES_PER_RUN
    found = []
    for n in range(1, pages + 1):
        page = fetch(f"{BASE}/nl/aanbod" if n == 1 else f"{BASE}/nl/aanbod/page/{n}")
        items = parse_listings(page)
        if not items:
            if n == 1:
                sys.exit("No listings found on page 1 - the site layout may have changed.")
            break
        found.extend(items)
        time.sleep(1)  # be polite

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_items = []
    for item in found:
        is_new = item["id"] not in seen
        seen.add(item["id"])
        if not wanted(item):
            continue
        item["first_seen"] = known.get(item["id"], {}).get("first_seen", now)
        known[item["id"]] = item  # refreshes status and price of known listings
        if is_new and item["status"].lower() not in SKIP_STATUSES:
            new_items.append(item)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    for item in sorted(new_items, key=lambda l: l["id"]):
        line = f'{item["town"]}, {item["street"]} - {item["price_text"]} [{item["status"]}] {item["url"]}'
        if first_run:
            print("first run, not notifying:", line)
        elif dry_run or not (token and chat_id):
            print("NEW (not sent):", line)
        else:
            notify(item, token, chat_id)
            print("NEW, sent:", line)

    if not dry_run:
        out = {
            "updated": now,
            "seen_ids": sorted(seen),
            "listings": sorted(known.values(), key=lambda l: -l["id"]),
        }
        new_text = json.dumps(out, ensure_ascii=False, indent=1)
        # only rewrite when something other than the timestamp changed
        old = dict(state, updated=now)
        old["listings"] = sorted(state["listings"], key=lambda l: -l["id"])
        old["seen_ids"] = sorted(state["seen_ids"])
        if first_run or json.dumps(old, ensure_ascii=False, indent=1) != new_text:
            STATE_FILE.write_text(new_text + "\n", encoding="utf-8")
    print(f"checked {len(found)} listings, {len(new_items)} new in your area")


if __name__ == "__main__":
    main(sys.argv[1:])
