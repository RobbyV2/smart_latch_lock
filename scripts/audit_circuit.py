#!/usr/bin/env python3
# stub: netlist nets, component values, and footprints against the released design ; fill the tables below
"""Cross-check the KiCad netlist against the released nets, values, and footprints."""

import argparse
import hashlib
import json
import pathlib
import xml.etree.ElementTree as ET

EXPECTED_NETS = {}
EXPECTED_VALUES = {}
EXPECTED_FOOTPRINTS = {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--netlist", required=True, type=pathlib.Path)
    parser.add_argument("--board", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    issues = []
    root = ET.parse(args.netlist).getroot()
    nets = {net.get("name"): {(node.get("ref"), node.get("pin"))
                              for node in net.findall("node")}
            for net in root.findall("./nets/net")}
    components = {comp.get("ref"): comp for comp in root.findall("./components/comp")}

    for name, expected in EXPECTED_NETS.items():
        observed = nets.get(name, set())
        if observed != set(expected):
            issues.append(f"net {name} nodes {sorted(observed)!r} differ from exact released "
                          f"{sorted(expected)!r}")
    for ref, expected in EXPECTED_VALUES.items():
        observed = components[ref].findtext("value", "") if ref in components else None
        if observed != expected:
            issues.append(f"{ref} value {observed!r} differs from exact released {expected!r}")
    for ref, expected in EXPECTED_FOOTPRINTS.items():
        observed = components[ref].findtext("footprint", "") if ref in components else None
        if observed != expected:
            issues.append(f"{ref} footprint {observed!r} differs from exact released {expected!r}")

    result = {
        "passed": not issues,
        "issues": issues,
        "board_sha256": hashlib.sha256(args.board.read_bytes()).hexdigest(),
        "component_count": len(components),
        "net_count": len(nets),
        "expected_net_count": len(EXPECTED_NETS),
        "expected_value_count": len(EXPECTED_VALUES),
        "expected_footprint_count": len(EXPECTED_FOOTPRINTS),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
