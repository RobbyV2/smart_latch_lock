#!/usr/bin/env python3
"""Derive the stack manifest from a frozen board."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate_stacks import SCHEMA, board_copper_layers, board_thickness, sha256


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True, type=pathlib.Path)
    parser.add_argument("--rules", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    text = args.board.read_text()
    manifest = {
        "schema": SCHEMA,
        "board": args.board.name,
        "rules": args.rules.name,
        "layer_stack": {
            "copper_layers": board_copper_layers(text),
            "finished_thickness_mm": board_thickness(text),
        },
        "source_hashes": {
            "board_sha256": sha256(args.board),
            "rules_sha256": sha256(args.rules),
        },
        "allowed_drc_markers": {},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
