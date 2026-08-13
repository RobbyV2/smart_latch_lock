#!/usr/bin/env python3
# stub: schematic BOM against PCB footprint identity, datasheets, pad geometry, and 3D models ; fill the tables below
"""Fail closed on release-critical source identity and the exact released land geometry."""

import argparse
import csv
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "panel"))
import sexp

FIELDS = ("LCSC Part", "Manufacturer", "MPN")
PARTS = {}
PARTS = {ref: dict(zip(FIELDS, values)) for ref, values in PARTS.items()}
EXPECTED_FOOTPRINTS = {}
EXPECTED_DATASHEETS = {}
EXPECTED_PAD_GEOMETRY = {}
EXPECTED_MODELS = {}


def unq(value):
    return sexp.unq(value) if isinstance(value, str) else value


def properties(node):
    return {unq(item[1]): unq(item[2]) for item in sexp.kids(node, "property") if len(item) >= 3}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pad_geometry(node):
    result = set()
    for item in sexp.kids(node, "pad"):
        at, size, drill = sexp.kid(item, "at"), sexp.kid(item, "size"), sexp.kid(item, "drill")
        angle = float(at[3]) if at is not None and len(at) >= 4 else 0.0
        hole = float(drill[1]) if drill is not None and len(drill) >= 2 else None
        result.add((unq(item[1]), unq(item[2]), round(float(at[1]), 6), round(float(at[2]), 6),
                    round(angle, 6), round(float(size[1]), 6), round(float(size[2]), 6),
                    None if hole is None else round(hole, 6)))
    return result


def resolve(text, board, lib):
    path = pathlib.Path(text.replace("${KIPRJMOD}", str(board.resolve().parent)))
    return path.resolve() if path.is_absolute() else (lib / path).resolve()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True, type=pathlib.Path)
    parser.add_argument("--bom", required=True, type=pathlib.Path)
    parser.add_argument("--lib", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    issues, models = [], {}

    rows = {row["Designator"]: row for row in csv.DictReader(args.bom.open(newline=""))}
    for ref, expected in PARTS.items():
        row = rows.get(ref)
        if row is None:
            issues.append(f"schematic BOM lacks {ref}")
            continue
        for field, value in expected.items():
            if row.get(field, "").strip() != value:
                issues.append(f"schematic {ref} {field} {row.get(field, '')!r} differs from exact "
                              f"released {value!r}")

    byref = {}
    for node in sexp.parse(args.board.read_text()):
        if sexp.tag(node) == "footprint":
            props = properties(node)
            if "Reference" in props:
                byref[props["Reference"]] = (node, props)
    for ref, expected in PARTS.items():
        item = byref.get(ref)
        if item is None:
            issues.append(f"PCB lacks footprint {ref}")
            continue
        for field, value in expected.items():
            if item[1].get(field, "") != value:
                issues.append(f"PCB {ref} {field} {item[1].get(field, '')!r} differs from exact "
                              f"released {value!r}")
    for ref, expected in EXPECTED_FOOTPRINTS.items():
        item = byref.get(ref)
        if item is not None and unq(item[0][1]) != expected:
            issues.append(f"{ref} footprint {unq(item[0][1])!r} differs from exact released "
                          f"{expected!r}")
    for ref, expected in EXPECTED_DATASHEETS.items():
        item = byref.get(ref)
        if item is not None and item[1].get("Datasheet", "") != expected:
            issues.append(f"{ref} datasheet {item[1].get('Datasheet', '')!r} differs from exact "
                          f"released {expected!r}")
    for ref, expected in EXPECTED_PAD_GEOMETRY.items():
        item = byref.get(ref)
        if item is not None and pad_geometry(item[0]) != set(expected):
            issues.append(f"{ref} pad geometry differs from the exact released land pattern")
    for ref, (declared, digest) in EXPECTED_MODELS.items():
        item = byref.get(ref)
        if item is None:
            continue
        paths = [unq(model[1]) for model in sexp.kids(item[0], "model") if len(model) >= 2]
        if paths != [declared]:
            issues.append(f"{ref} model paths {paths!r} differ from exact released {[declared]!r}")
            continue
        path = resolve(declared, args.board, args.lib)
        if not path.is_file():
            issues.append(f"{ref} model {path} is absent")
            continue
        observed = sha256(path)
        models[ref] = {"path": declared, "sha256": observed}
        if observed != digest:
            issues.append(f"{ref} model SHA-256 {observed} differs from exact released {digest}")

    result = {
        "passed": not issues,
        "issues": issues,
        "board_sha256": sha256(args.board),
        "critical_parts": PARTS,
        "exact_footprints": EXPECTED_FOOTPRINTS,
        "exact_datasheets": EXPECTED_DATASHEETS,
        "exact_pad_geometry": {ref: sorted(values, key=str)
                               for ref, values in EXPECTED_PAD_GEOMETRY.items()},
        "models": models,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
