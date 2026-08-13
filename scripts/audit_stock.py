#!/usr/bin/env python3
"""Verify that live distributor stock covers every assembly line with 10 percent overage."""

import argparse
import csv
import datetime
import hashlib
import http.client
import json
import math
import pathlib
import re
import time
import urllib.request

FROZEN = {}
OVERAGE = 1.10
LCSC_PART = re.compile(r"^C\d+$")


def lcsc(code):
    url = f"https://www.lcsc.com/product-detail/{code}.html"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    failure = None
    for attempt in range(3):
        try:
            text = urllib.request.urlopen(request, timeout=30).read().decode("utf-8", "replace")
            break
        except (OSError, http.client.HTTPException) as exc:
            failure = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    else:
        raise ValueError(f"LCSC request failed after three attempts: {url}: {failure}")
    model = re.search(r'"productModel":"([^"]+)"', text)
    stock = re.search(r'"inventoryLevel":(\d+)', text)
    if not model or not stock:
        raise ValueError(f"LCSC page lacks structured model and stock: {url}")
    return int(stock.group(1)), model.group(1), url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assembly", required=True, type=pathlib.Path)
    parser.add_argument("--board", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--population", default="A")
    args = parser.parse_args()
    issues, parts, skipped = [], [], []
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    demand = {}
    for row in csv.DictReader((args.assembly / args.population / "bom.csv").open(newline="")):
        key = (row["Manufacturer"], row["MPN"], row["Distributor Part Number"].strip())
        demand[key] = demand.get(key, 0) + int(row["Quantity"])
    for (manufacturer, mpn, route), quantity in sorted(demand.items()):
        required = math.ceil(quantity * OVERAGE)
        if not LCSC_PART.match(route) and route not in FROZEN:
            skipped.append({"manufacturer": manufacturer, "mpn": mpn, "route": route,
                            "quantity": quantity})
            continue
        available, url, source, fetched_at = 0, "", "LCSC", now
        try:
            if route in FROZEN:
                frozen = FROZEN[route]
                available, url = int(frozen["available"]), frozen["url"]
                source, fetched_at = frozen["source"], frozen["fetched_at"]
            else:
                available, observed, url = lcsc(route)
                if observed.casefold() != mpn.casefold():
                    issues.append(f"{route} resolves to {observed} which differs from exact "
                                  f"released {mpn}")
            if available < required:
                issues.append(f"{route} available {available} is below required {required} "
                              f"including 10 percent overage")
        except (KeyError, ValueError) as exc:
            issues.append(str(exc))
        parts.append({
            "manufacturer": manufacturer, "mpn": mpn, "route": route, "quantity": quantity,
            "required_with_10_percent_overage": required, "available": available,
            "fetched_at": fetched_at, "source": source, "url": url,
            "passed": available >= required,
        })
    result = {
        "passed": not issues,
        "issues": issues,
        "board_sha256": hashlib.sha256(args.board.read_bytes()).hexdigest(),
        "checked_at": now,
        "policy": {"population": args.population, "overage_percent": 10},
        "parts": parts,
        "skipped": skipped,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
