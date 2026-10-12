#!/usr/bin/env python3
"""
leadgrab — pull verified local-business leads (name, address, phone, website,
rating, review count) into a CSV.

Data source: Google local results, fetched through a scraping gateway
(Bright Data Web Unlocker by default; any gateway that accepts
{"url": ..., "zone": ..., "format": "raw"} works).

Usage:
    export BRIGHTDATA_TOKEN=your_token      # gateway auth
    export BRIGHTDATA_ZONE=unlocker1       # gateway zone
    python3 leadgrab.py "dentists in Austin, TX" --out austin_dentists.csv
    python3 leadgrab.py --cities Austin "San Diego" --categories dentists gyms

Output columns: name, category, type, address, city, rating, reviews,
                phone, website, cid
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

GATEWAY_URL = os.environ.get("LEADGRAB_GATEWAY", "https://api.brightdata.com/request")
TOKEN = os.environ.get("BRIGHTDATA_TOKEN", "")
ZONE = os.environ.get("BRIGHTDATA_ZONE", "default")


def gateway_fetch(url: str, retries: int = 3, timeout: int = 120) -> str:
    """Fetch a URL through the scraping gateway. Retries on empty responses."""
    body = json.dumps({"url": url, "zone": ZONE, "format": "raw"}).encode()
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(GATEWAY_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
            if text.strip():
                return text
            last_err = "empty response"
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed for {url}: {last_err}")


def search_local(query: str) -> list[dict]:
    """One Google local search -> list of business dicts (parsed JSON)."""
    q = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={q}&tbm=lcl&hl=en&gl=us&brd_json=1"
    try:
        return json.loads(gateway_fetch(url)).get("snack_pack", []) or []
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"  ! '{query}': {exc}", file=sys.stderr)
        return []


def enrich(entry: dict) -> dict:
    """Second pass: pull phone + website from the knowledge panel."""
    query = f"{entry.get('name','')} {entry.get('address','')} phone website"
    q = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={q}&hl=en&gl=us&brd_json=1"
    try:
        data = json.loads(gateway_fetch(url))
    except (RuntimeError, json.JSONDecodeError):
        return entry
    panel = data.get("knowledge", {}) or {}
    entry["phone"] = (panel.get("phone") or "").strip()
    entry["website"] = (panel.get("website") or panel.get("site") or "").strip()
    if not entry["website"]:
        organic = data.get("organic") or []
        if organic:
            entry["website"] = organic[0].get("link", "")
    if panel.get("address"):
        entry["address"] = panel["address"].strip()
    return entry


def build_row(entry: dict, category: str, city: str) -> dict:
    return {
        "name": (entry.get("name") or "").strip(),
        "category": category,
        "type": (entry.get("type") or "").strip(),
        "address": (entry.get("address") or "").strip(),
        "city": city,
        "rating": entry.get("rating"),
        "reviews": entry.get("reviews_cnt"),
        "phone": "",
        "website": "",
        "cid": entry.get("cid"),
    }


COLUMNS = ["name", "category", "type", "address", "city", "rating",
           "reviews", "phone", "website", "cid"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Verified local-business lead scraper")
    ap.add_argument("queries", nargs="*", help='free-form queries, e.g. "dentists in Austin, TX"')
    ap.add_argument("--cities", nargs="+", help="cities to sweep")
    ap.add_argument("--categories", nargs="+", help="business types to sweep")
    ap.add_argument("--out", default="leads.csv", help="output CSV path")
    ap.add_argument("--workers", type=int, default=4, help="parallel requests")
    ap.add_argument("--no-enrich", action="store_true", help="skip phone/website lookup (much faster)")
    args = ap.parse_args()

    if not TOKEN:
        print("Set BRIGHTDATA_TOKEN (and BRIGHTDATA_ZONE) first.", file=sys.stderr)
        return 1

    jobs: list[tuple[str, str, str]] = []  # (query, category, city)
    for q in args.queries:
        jobs.append((q, "", ""))
    if args.cities and args.categories:
        for city in args.cities:
            for cat in args.categories:
                jobs.append((f"{cat} in {city}", cat, city))
    if not jobs:
        ap.error("give queries, or both --cities and --categories")

    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    started = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(search_local, q): (q, cat, city) for q, cat, city in jobs}
        for fut in as_completed(futures):
            query, category, city = futures[fut]
            found = fut.result()
            print(f"  {query!r}: {len(found)} businesses")
            for entry in found:
                row = build_row(entry, category, city)
                key = (row["name"], row["city"])
                if row["name"] and key not in seen:
                    seen.add(key)
                    rows.append(row)

    if not args.no_enrich:
        print(f"enriching {len(rows)} rows (phone + website)...")
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(enrich, r) for r in rows]
            for done, fut in enumerate(as_completed(futures), 1):
                fut.result()
                if done % 25 == 0:
                    print(f"  {done}/{len(rows)}")

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    with_phone = sum(1 for r in rows if r.get("phone"))
    with_site = sum(1 for r in rows if r.get("website"))
    print(f"\n{len(rows)} leads in {time.time() - started:.0f}s -> {args.out}")
    print(f"  with phone: {with_phone} | with website: {with_site}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
