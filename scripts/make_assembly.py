#!/usr/bin/env python3
"""Create the assembly BOM and centroid for one population."""

import argparse
import csv
import json
import pathlib
import re
from collections import defaultdict

DISTRIBUTOR_OVERRIDE = {}

BOM_HEADERS = ("Designator", "Quantity", "Manufacturer", "MPN", "Value", "Footprint",
               "Distributor Part Number")
CENTROID_HEADERS = ("Designator", "Mid X (mm)", "Mid Y (mm)", "Layer", "Rotation (deg CCW)",
                    "Value", "Package")
RANGE = re.compile(r"^([A-Za-z_]+)(\d+)-([A-Za-z_]*)(\d+)$")


def expand(field):
    refs = []
    for token in (item.strip() for item in field.split(",")):
        if not token:
            continue
        match = RANGE.match(token)
        if match is None:
            refs.append(token)
            continue
        prefix, first, tail, last = match.group(1), int(match.group(2)), match.group(3), int(match.group(4))
        if tail and tail != prefix:
            raise ValueError(f"designator range {token} spans prefixes {prefix} and {tail}")
        if last < first:
            raise ValueError(f"designator range {token} runs backwards")
        refs.extend(f"{prefix}{index}" for index in range(first, last + 1))
    return refs


def read_bom(path):
    byref = {}
    for row in csv.DictReader(path.open(newline="")):
        manufacturer = row.get("Manufacturer", "").strip()
        mpn = row.get("MPN", "").strip()
        code = row.get("LCSC Part", "").strip()
        for ref in expand(row["Designator"]):
            if not manufacturer or not mpn:
                raise ValueError(f"source metadata missing for {ref}: Manufacturer and MPN required")
            if ref in byref:
                raise ValueError(f"duplicate source designator {ref}")
            byref[ref] = {**row, "Designator": ref, "Manufacturer": manufacturer, "MPN": mpn,
                          "LCSC Part": DISTRIBUTOR_OVERRIDE.get(code, code)}
    return byref


def read_pos(path):
    return {row["Ref"]: row for row in csv.DictReader(path.open(newline=""))}


def grouped_bom(parts):
    groups = defaultdict(list)
    for ref, row in parts.items():
        key = (row["Manufacturer"], row["MPN"], row["Value"], row["Footprint"], row["LCSC Part"])
        groups[key].append(ref)
    rows = []
    for key, refs in sorted(groups.items(), key=lambda item: min(item[1])):
        manufacturer, mpn, value, fp, distributor = key
        rows.append([",".join(sorted(refs)), len(refs), manufacturer, mpn, value, fp, distributor])
    return rows


def centroid(positions, wanted):
    missing = sorted(set(wanted) - set(positions))
    if missing:
        raise ValueError(f"centroid lacks fitted designators: {','.join(missing)}")
    rows = []
    for ref in sorted(wanted):
        row = positions[ref]
        rows.append([ref, round(float(row["PosX"]), 6), round(float(row["PosY"]), 6),
                     row["Side"].title(), round(float(row["Rot"]), 6), row["Val"], row["Package"]])
    return rows


def write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bom", required=True, type=pathlib.Path)
    parser.add_argument("--pos", required=True, type=pathlib.Path)
    parser.add_argument("--out-dir", required=True, type=pathlib.Path)
    parser.add_argument("--population", default="A")
    args = parser.parse_args()
    try:
        parts = read_bom(args.bom)
        bom = grouped_bom(parts)
        cpl = centroid(read_pos(args.pos), set(parts))
    except ValueError as exc:
        raise SystemExit(str(exc))
    out = args.out_dir / args.population
    write_csv(out / "bom.csv", BOM_HEADERS, bom)
    write_csv(out / "centroid.csv", CENTROID_HEADERS, cpl)
    print(json.dumps({"population": args.population, "bom_lines": len(bom), "fitted": len(cpl),
                      "passed": True}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
