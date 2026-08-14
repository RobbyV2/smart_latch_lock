#!/usr/bin/env python3
"""Cross-check the assembly BOM and centroid against the raw KiCad exports."""

import argparse
import csv
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_assembly


def rows(path):
    return list(csv.DictReader(path.open(newline="")))


def dicts(values, headers):
    return [dict(zip(headers, row)) for row in values]


def bom_index(data):
    index = {}
    for row in data:
        names = tuple(item for item in row["Designator"].split(",") if item)
        key = (row["Manufacturer"], row["MPN"], row["Value"], row["Footprint"],
               row["LCSC Part #"])
        if key in index:
            raise ValueError(f"BOM line {key!r} appears more than once")
        index[key] = (int(row["Quantity"]), names)
    return index


def centroid_index(data):
    index = {}
    for row in data:
        ref = row["Designator"]
        if ref in index:
            raise ValueError(f"centroid designator {ref} appears more than once")
        index[ref] = (round(float(row["Mid X (mm)"]), 6), round(float(row["Mid Y (mm)"]), 6),
                      row["Layer"], round(float(row["Rotation (deg CCW)"]), 6),
                      row["Value"], row["Package"])
    return index


def compare(actual, expected, label):
    issues = []
    for key in sorted(set(actual) | set(expected), key=str):
        if key not in expected:
            issues.append(f"{label} {key!r} is not derived from the raw KiCad exports")
        elif key not in actual:
            issues.append(f"{label} {key!r} is absent from the assembly output")
        elif actual[key] != expected[key]:
            issues.append(f"{label} {key!r} {actual[key]!r} differs from exact released "
                          f"{expected[key]!r}")
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assembly", required=True, type=pathlib.Path)
    parser.add_argument("--bom", required=True, type=pathlib.Path)
    parser.add_argument("--pos", required=True, type=pathlib.Path)
    parser.add_argument("--board", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--population", default="A")
    args = parser.parse_args()
    issues = []
    folder = args.assembly / args.population
    bom_lines, fitted = 0, 0
    try:
        parts = make_assembly.read_bom(args.bom)
        derived_bom = bom_index(dicts(make_assembly.grouped_bom(parts), make_assembly.BOM_HEADERS))
        derived_cpl = centroid_index(dicts(
            make_assembly.centroid(make_assembly.read_pos(args.pos), set(parts)),
            make_assembly.CENTROID_HEADERS))
        released_bom = bom_index(rows(folder / "bom.csv"))
        released_cpl = centroid_index(rows(folder / "centroid.csv"))
        bom_lines, fitted = len(released_bom), len(released_cpl)
        issues.extend(compare(released_bom, derived_bom, "BOM line"))
        issues.extend(compare(released_cpl, derived_cpl, "centroid"))
        released_refs = {ref for _, names in released_bom.values() for ref in names}
        if released_refs != set(released_cpl):
            issues.append(f"BOM designator set {sorted(released_refs ^ set(released_cpl))!r} differs "
                          f"from exact released centroid designator set")
    except (OSError, KeyError, ValueError) as exc:
        issues.append(str(exc))
    result = {
        "passed": not issues,
        "issues": issues,
        "board_sha256": hashlib.sha256(args.board.read_bytes()).hexdigest(),
        "population": args.population,
        "bom_lines": bom_lines,
        "fitted": fitted,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
