#!/usr/bin/env python3
# stub: released footprint positions, controlled route lengths, and net clearances ; fill the tables below
"""Fail closed on the released placement, routed path lengths, and net copper clearances."""

import argparse
import hashlib
import heapq
import json
import math
import pathlib

import pcbnew

EXPECTED_POSITIONS = {}
EXPECTED_PATHS = {}
NET_CLEARANCES = {}


def mm(value):
    return tuple(round(item, 6) for item in pcbnew.ToMM(value))


def footprint(board, reference):
    matches = [item for item in board.GetFootprints() if item.GetReference() == reference]
    if len(matches) != 1:
        raise ValueError(f"{reference} footprint count is {len(matches)}, not 1")
    return matches[0]


def pad(footprint, number):
    matches = [item for item in footprint.Pads() if item.GetNumber() == number]
    if len(matches) != 1:
        raise ValueError(f"{footprint.GetReference()} pad {number} count is {len(matches)}, not 1")
    return matches[0]


def copper_stack(board):
    inner = [getattr(pcbnew, f"In{index}_Cu")
             for index in range(1, max(board.GetCopperLayerCount() - 1, 1))]
    return [pcbnew.F_Cu, *inner, pcbnew.B_Cu]


def pad_nodes(item, stack):
    return [(layer, mm(item.GetPosition())) for layer in stack if item.IsOnLayer(layer)]


def edge(graph, left, right, weight):
    graph.setdefault(left, []).append((right, weight))
    graph.setdefault(right, []).append((left, weight))


def route_graph(board, net):
    graph, stack = {}, copper_stack(board)
    for item in board.GetTracks():
        if item.GetNetname() != net:
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            if item.TopLayer() not in stack or item.BottomLayer() not in stack:
                raise ValueError(f"{net} via spans layers outside the copper stack")
            first, last = sorted((stack.index(item.TopLayer()), stack.index(item.BottomLayer())))
            column = [(layer, mm(item.GetPosition())) for layer in stack[first:last + 1]]
            for left, right in zip(column, column[1:]):
                edge(graph, left, right, 0.0)
        else:
            layer = item.GetLayer()
            edge(graph, (layer, mm(item.GetStart())), (layer, mm(item.GetEnd())),
                 pcbnew.ToMM(item.GetLength()))
    return graph


def shortest(graph, start, end):
    targets = set(end)
    queue = [(0.0, node) for node in start]
    heapq.heapify(queue)
    seen = set()
    while queue:
        distance, node = heapq.heappop(queue)
        if node in seen:
            continue
        seen.add(node)
        if node in targets:
            return distance
        for neighbor, weight in graph.get(node, []):
            if neighbor not in seen:
                heapq.heappush(queue, (distance + weight, neighbor))
    raise ValueError("no routed copper path")


def point_segment(point, start, end):
    span = (end[0] - start[0], end[1] - start[1])
    length = span[0] ** 2 + span[1] ** 2
    if length == 0:
        return math.dist(point, start)
    along = ((point[0] - start[0]) * span[0] + (point[1] - start[1]) * span[1]) / length
    along = max(0.0, min(1.0, along))
    return math.dist(point, (start[0] + along * span[0], start[1] + along * span[1]))


def crosses(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return ((side(a, b, c) > 0) != (side(a, b, d) > 0)
            and (side(c, d, a) > 0) != (side(c, d, b) > 0))


def segment_distance(a, b, c, d):
    if crosses(a, b, c, d):
        return 0.0
    return min(point_segment(a, c, d), point_segment(b, c, d),
               point_segment(c, a, b), point_segment(d, a, b))


def width(item, layer):
    try:
        return pcbnew.ToMM(item.GetWidth(layer))
    except TypeError:
        return pcbnew.ToMM(item.GetWidth())


def copper_segments(board, stack):
    rows = []
    for item in board.GetTracks():
        layers = {layer for layer in stack if item.IsOnLayer(layer)}
        if isinstance(item, pcbnew.PCB_VIA):
            center = mm(item.GetPosition())
            rows.append((item.GetNetname(), layers, center, center,
                         width(item, item.TopLayer())))
        else:
            rows.append((item.GetNetname(), layers, mm(item.GetStart()), mm(item.GetEnd()),
                         width(item, item.GetLayer())))
    return rows


def clearance(rows, net):
    best = None
    for net_a, layers_a, start_a, end_a, width_a in (row for row in rows if row[0] == net):
        for net_b, layers_b, start_b, end_b, width_b in rows:
            if net_b == net_a or not layers_a & layers_b:
                continue
            gap = round(segment_distance(start_a, end_a, start_b, end_b)
                        - (width_a + width_b) / 2.0, 6)
            if best is None or gap < best[0]:
                best = (gap, net_b)
    if best is None:
        raise ValueError(f"net {net} shares no copper layer with another net")
    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    board = pcbnew.LoadBoard(str(args.board))
    stack = copper_stack(board)
    rows = copper_segments(board, stack) if NET_CLEARANCES else []
    issues, positions, paths, clearances = [], {}, {}, {}

    for reference, expected in EXPECTED_POSITIONS.items():
        try:
            observed = mm(footprint(board, reference).GetPosition())
            positions[reference] = {"observed_mm": list(observed), "released_mm": list(expected)}
            if observed != tuple(expected):
                issues.append(f"{reference} position {observed} differs from exact released "
                              f"{tuple(expected)}")
        except ValueError as exc:
            issues.append(str(exc))

    for net, expected in EXPECTED_PATHS.items():
        try:
            start = pad_nodes(pad(footprint(board, expected["from"][0]), expected["from"][1]), stack)
            end = pad_nodes(pad(footprint(board, expected["to"][0]), expected["to"][1]), stack)
            observed = round(shortest(route_graph(board, net), start, end), 6)
            paths[net] = {"observed_mm": observed, "released_mm": expected["released_mm"],
                          "maximum_mm": expected["maximum_mm"]}
            if observed > expected["maximum_mm"] + 1e-6:
                issues.append(f"{net} routed path {observed} exceeds released maximum "
                              f"{expected['maximum_mm']}")
            if not math.isclose(observed, expected["released_mm"], abs_tol=1e-6):
                issues.append(f"{net} routed path {observed} differs from exact released "
                              f"{expected['released_mm']}")
        except (KeyError, ValueError) as exc:
            issues.append(f"{net}: {exc}")

    for net, minimum in NET_CLEARANCES.items():
        try:
            observed, nearest = clearance(rows, net)
            clearances[net] = {"observed_mm": observed, "minimum_mm": minimum,
                               "nearest_net": nearest}
            if observed < minimum - 1e-6:
                issues.append(f"{net} clearance {observed} to {nearest} is below released minimum "
                              f"{minimum}")
        except ValueError as exc:
            issues.append(str(exc))

    result = {
        "passed": not issues,
        "issues": issues,
        "board_sha256": hashlib.sha256(args.board.read_bytes()).hexdigest(),
        "copper_layer_count": board.GetCopperLayerCount(),
        "positions": positions,
        "paths": paths,
        "clearances": clearances,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
