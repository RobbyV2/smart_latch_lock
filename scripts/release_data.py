#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import math
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "panel"))
import product
import sexp


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def child_value(node, name, default=None):
    item = sexp.kid(node, name)
    if not item or len(item) < 2:
        return default
    return sexp.unq(item[1]) if isinstance(item[1], str) else item[1]


def stackup(args):
    manifest = product.load_manifest(args.manifest)
    expected = [suffix.rsplit(".", 1)[0].replace("_", ".")
                for suffix, _ in product.copper_layers(manifest)]
    tree = sexp.parse(args.board.read_text())
    setup = sexp.kid(tree, "setup")
    source = sexp.kid(setup, "stackup") if setup else None
    if source is None:
        raise SystemExit("board has no stackup")
    rows = []
    for item in sexp.kids(source, "layer"):
        name = sexp.unq(item[1])
        kind = child_value(item, "type", "")
        if kind != "copper" and not name.startswith("dielectric "):
            continue
        thickness = float(child_value(item, "thickness", -1))
        if thickness <= 0:
            raise SystemExit(f"stack layer {name} lacks positive thickness")
        rows.append({"layer": name, "type": kind, "thickness_mm": round(thickness, 6),
                     "material": child_value(item, "material", "")})
    copper = [row["layer"] for row in rows if row["type"] == "copper"]
    total = round(sum(row["thickness_mm"] for row in rows), 6)
    declared = round(float(child_value(sexp.kid(tree, "general"), "thickness", -1)), 6)
    if copper != expected:
        raise SystemExit(f"board copper layers {copper} differs from exact released {expected}")
    if len(rows) != 2 * len(expected) - 1:
        raise SystemExit(f"stackup row count {len(rows)} differs from exact released {2 * len(expected) - 1}")
    if not math.isclose(total, declared, abs_tol=1e-6):
        raise SystemExit(f"stackup thickness {total} differs from exact released {declared}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("order", "layer", "type", "thickness_mm", "material"))
        writer.writeheader()
        for order, row in enumerate(rows, 1):
            writer.writerow({"order": order, **row})


def inventory(args):
    root = args.root.resolve()
    inventory_path = root / "reports" / "artifact-inventory.json"
    excluded = {inventory_path}
    files = [path for path in root.rglob("*") if path.is_file() and path not in excluded]
    records = [{"path": str(path.relative_to(root)), "bytes": path.stat().st_size,
                "sha256": sha256(path)} for path in sorted(files)]
    by_top = {}
    for item in records:
        row = by_top.setdefault(item["path"].split("/", 1)[0], {"files": 0, "bytes": 0})
        row["files"] += 1
        row["bytes"] += item["bytes"]
    data = {
        "root": os.path.relpath(root, REPO),
        "files_excluding_inventory": len(records),
        "bytes_excluding_inventory": sum(item["bytes"] for item in records),
        "by_top_directory": by_top,
        "files": records,
    }
    release_path = root / "reports" / "release.json"
    if release_path.is_file():
        release = json.loads(release_path.read_text())
        data.update({key: release[key]
                     for key in ("orderable", "first_article_orderable", "production_orderable")
                     if key in release})
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    stack = commands.add_parser("stackup")
    stack.add_argument("--board", required=True, type=pathlib.Path)
    stack.add_argument("--manifest", required=True, type=pathlib.Path)
    stack.add_argument("--out", required=True, type=pathlib.Path)
    stack.set_defaults(handler=stackup)
    index = commands.add_parser("inventory")
    index.add_argument("--root", required=True, type=pathlib.Path)
    index.set_defaults(handler=inventory)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
