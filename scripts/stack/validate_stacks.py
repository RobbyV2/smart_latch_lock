#!/usr/bin/env python3
# stub: microvia chain topology through the required design rule snippets ; fill the tables below
"""Fail closed on the released stack manifest, copper layers, and DRC markers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import re
from collections import Counter

SCHEMA = 1
TOL = 1e-6
REQUIRED_RULE_SNIPPETS = ()


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def balanced_blocks(text: str, token: str) -> list[str]:
    blocks: list[str] = []
    cursor = 0
    while True:
        start = text.find(token, cursor)
        if start < 0:
            return blocks
        depth = 0
        quoted = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                continue
            if char == '"':
                quoted = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(text[start:index + 1])
                    cursor = index + 1
                    break
        else:
            raise ValueError(f"unbalanced block beginning {token!r}")


def board_copper_layers(text: str) -> list[str]:
    blocks = balanced_blocks(text, "\n\t(layers")
    if len(blocks) != 1:
        raise ValueError(f"board declares {len(blocks)} layer blocks, not 1")
    return [name for _, name in re.findall(r'\((\d+)\s+"([^"]+)"', blocks[0])
            if name.endswith(".Cu")]


def board_thickness(text: str) -> float:
    blocks = balanced_blocks(text, "\n\t(general")
    if len(blocks) != 1:
        raise ValueError(f"board declares {len(blocks)} general blocks, not 1")
    match = re.search(r"\(thickness\s+([-+0-9.eE]+)\)", blocks[0])
    if match is None:
        raise ValueError("board general block lacks a thickness")
    return round(float(match.group(1)), 6)


def active_markers(report: dict) -> Counter:
    counts: Counter = Counter()
    for violation in report.get("violations", []):
        if not violation.get("excluded", False):
            counts[violation.get("type", "")] += 1
    return counts


def validate(board: pathlib.Path, manifest: pathlib.Path, drc: pathlib.Path) -> dict:
    issues: list[str] = []
    copper: list[str] = []
    thickness = 0.0
    document = json.loads(manifest.read_text())
    if document.get("schema") != SCHEMA:
        issues.append(f"manifest schema {document.get('schema')!r} differs from exact released "
                      f"{SCHEMA}")
    if board.name != document.get("board"):
        issues.append(f"board {board.name!r} differs from exact released "
                      f"{document.get('board')!r}")

    rules = board.parent / document.get("rules", "")
    sources = {"board": board, "rules": rules}
    if document.get("project"):
        sources["project"] = board.parent / document["project"]
    for field, path in sorted(sources.items()):
        expected = document.get("source_hashes", {}).get(f"{field}_sha256")
        if not path.is_file():
            issues.append(f"manifest {field} {path.name!r} is absent from {path.parent}")
            continue
        observed = sha256(path)
        if observed != expected:
            issues.append(f"{field}_sha256 {observed} differs from exact released {expected}")

    try:
        text = board.read_text()
        copper = board_copper_layers(text)
        thickness = board_thickness(text)
        stack = document.get("layer_stack", {})
        if copper != list(stack.get("copper_layers", [])):
            issues.append(f"board copper layers {copper} differ from exact released "
                          f"{stack.get('copper_layers')}")
        declared = stack.get("finished_thickness_mm")
        if declared is None or not math.isclose(thickness, float(declared), abs_tol=TOL):
            issues.append(f"board finished thickness {thickness} differs from exact released "
                          f"{declared}")
    except (OSError, TypeError, ValueError) as exc:
        issues.append(str(exc))

    rules_text = re.sub(r"\s+", " ", rules.read_text()) if rules.is_file() else ""
    for snippet in REQUIRED_RULE_SNIPPETS:
        if re.sub(r"\s+", " ", snippet) not in rules_text:
            issues.append(f"rules file lacks exact {snippet!r}")

    markers = active_markers(json.loads(drc.read_text()))
    allowed = {key: int(value) for key, value in document.get("allowed_drc_markers", {}).items()}
    for kind in sorted(set(markers) | set(allowed)):
        if markers.get(kind, 0) != allowed.get(kind, 0):
            issues.append(f"active DRC marker {kind!r} count {markers.get(kind, 0)} differs from "
                          f"exact released {allowed.get(kind, 0)}")

    return {
        "passed": not issues,
        "issues": issues,
        "board_sha256": sha256(board) if board.is_file() else None,
        "schema": document.get("schema"),
        "copper_layers": copper,
        "finished_thickness_mm": thickness,
        "drc_markers": dict(markers),
        "allowed_drc_markers": allowed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True, type=pathlib.Path)
    parser.add_argument("--manifest", required=True, type=pathlib.Path)
    parser.add_argument("--drc", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    result = validate(args.board, args.manifest, args.drc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
