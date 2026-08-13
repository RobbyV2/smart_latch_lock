#!/usr/bin/env python3
"""Fail closed on any release defect before the fabrication package is adopted."""
import argparse, json, math, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from product import NAME, copper_layers, drill_specs, file_function, load_manifest, sha256

AUDITS = (
    ("drc_audit", "DRC audit"),
    ("erc_audit", "ERC audit"),
    ("stack_audit", "stack audit"),
    ("circuit_audit", "circuit audit"),
    ("geometry_audit", "geometry audit"),
    ("source_contract_audit", "source contract audit"),
    ("assembly_audit", "assembly audit"),
)


def audit_summary(path, board_sha, name, required=None):
    report = json.loads(path.read_text())
    issues = list(report.get("issues", []))
    if not report.get("passed") and not issues:
        issues.append(f"{name} did not pass")
    if report.get("board_sha256") != board_sha:
        issues.append(f"{name} is not bound to the released board SHA-256")
    if required is not None:
        required(report, issues)
    return report, issues, {
        "passed": not issues,
        "issues": issues,
        "report": f"reports/{path.name}",
        "sha256": sha256(path),
    }


def summarize(path, board_sha, name, data, key):
    try:
        _, issues, data[key] = audit_summary(path, board_sha, name)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        data[key] = {"passed": False, "issues": [str(exc)]}
        return [f"{name} is missing or invalid: {exc}"]
    return [f"{name}: {issue}" for issue in issues]


def fabrication(fab, manifest):
    issues = []
    copper = copper_layers(manifest)
    artifacts = {f"{NAME}-{suffix}": function for suffix, function in copper}
    artifacts.update({f"{NAME}-{stem}.drl": function for stem, function in drill_specs(manifest)})
    for name, function in sorted(artifacts.items()):
        path = fab / name
        if not path.is_file():
            issues.append(f"fabrication artifact {name} is missing from {fab}")
            continue
        observed = file_function(path)
        if observed != function:
            issues.append(f"{name} FileFunction {observed} differs from exact released {function}")
    released = (manifest.get("layer_stack") or {}).get("finished_thickness_mm")
    thickness = None
    job_path = fab / f"{NAME}-job.gbrjob"
    try:
        job = json.loads(job_path.read_text())
        listed = [item for item in job.get("FilesAttributes", [])
                  if str(item.get("FileFunction", "")).startswith("Copper,")]
        if len(listed) != len(copper):
            issues.append(f"gerber job copper layer count {len(listed)} differs from "
                          f"exact released {len(copper)}")
        thickness = job.get("GeneralSpecs", {}).get("BoardThickness")
        if not isinstance(released, (int, float)):
            issues.append(f"stack manifest finished thickness {released!r} is not a number")
        elif not isinstance(thickness, (int, float)) or not math.isclose(
                float(thickness), float(released), abs_tol=1e-6):
            issues.append(f"gerber job thickness {thickness} differs from "
                          f"exact released {round(float(released), 6)}")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        issues.append(f"gerber job {job_path.name} is missing or invalid: {exc}")
    return issues, {
        "artifacts": sorted(artifacts),
        "copper_layer_count": len(copper),
        "finished_thickness_mm": round(float(thickness), 6) if isinstance(thickness, (int, float)) else None,
    }


def vendor_approval(path, board_sha):
    if path is None:
        return ["missing"]
    try:
        approval = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"unreadable: {exc}"]
    issues = []
    if approval.get("approved") is not True:
        issues.append("not approved")
    if approval.get("board_sha256") != board_sha:
        issues.append("not bound to the released board SHA-256")
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True, type=pathlib.Path)
    parser.add_argument("--manifest", required=True, type=pathlib.Path)
    parser.add_argument("--fab", required=True, type=pathlib.Path)
    parser.add_argument("--drc-audit", required=True, type=pathlib.Path)
    parser.add_argument("--erc-audit", required=True, type=pathlib.Path)
    parser.add_argument("--stack-audit", required=True, type=pathlib.Path)
    parser.add_argument("--circuit-audit", required=True, type=pathlib.Path)
    parser.add_argument("--geometry-audit", required=True, type=pathlib.Path)
    parser.add_argument("--source-contract-audit", required=True, type=pathlib.Path)
    parser.add_argument("--assembly-audit", required=True, type=pathlib.Path)
    parser.add_argument("--stock-audit", required=True, type=pathlib.Path)
    parser.add_argument("--vendor-approval", type=pathlib.Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    board_sha = sha256(args.board)
    hard, blockers, data = [], [], {}
    if args.board.stem != NAME:
        hard.append(f"released board stem {args.board.stem} differs from exact released {NAME}")

    fab_issues, data["fabrication"] = fabrication(args.fab, manifest)
    hard.extend(fab_issues)
    for key, label in AUDITS:
        hard.extend(summarize(getattr(args, key), board_sha, label, data, key))

    try:
        _, stock_issues, data["stock_audit"] = audit_summary(
            args.stock_audit, board_sha, "stock audit")
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        stock_issues = [str(exc)]
        data["stock_audit"] = {"passed": False, "issues": stock_issues}
    if stock_issues:
        blockers.append("stock_audit")
    approval_issues = vendor_approval(args.vendor_approval, board_sha)
    data["vendor_approval"] = {"passed": not approval_issues, "issues": approval_issues}
    if approval_issues:
        blockers.append("vendor_approval")

    first_article_orderable = not args.dry_run and not hard and not blockers
    data.update({
        "passed": not hard and not blockers,
        "issues": hard + [f"blocker: {code}" for code in blockers],
        "board_sha256": board_sha,
        "manifest_sha256": sha256(args.manifest),
        "dry_run": args.dry_run,
        "hard_failures": hard,
        "release_blockers": blockers,
        "release_class": "FIRST_ARTICLE" if first_article_orderable else "REVIEW",
        "orderable": first_article_orderable,
        "first_article_orderable": first_article_orderable,
        "production_orderable": False,
    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(json.dumps(data, indent=2, sort_keys=True))
    return 1 if hard or (blockers and not args.dry_run) else 0


if __name__ == "__main__":
    raise SystemExit(main())
