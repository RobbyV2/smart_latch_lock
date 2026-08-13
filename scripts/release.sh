#!/usr/bin/env bash
set -Eeuo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
ROOT=${TFB_ROOT:-$(cd "$HERE/.." && pwd -P)}
INPUT=${TFB_BOARD:-${1:-}}
OUT=${TFB_RELEASE_OUT:-$ROOT/.release-build}
FAB=${TFB_FAB_DIR:-$ROOT/fab}
MANIFEST=${TFB_STACK_MANIFEST:-}
APPROVAL=${TFB_VENDOR_APPROVAL:-}
SKIP_STOCK=${TFB_SKIP_LIVE_STOCK:-0}
DRY_RUN=${TFB_DRY_RUN:-0}
K=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
PY=${PYTHON:-python3}
KPY=${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3}
NAME=triangle_flywheel_balancer

die() { echo "FAIL  $*" >&2; exit 1; }
kc() { "$K" "$@" 2> >(grep -v '^Fontconfig warning' >&2); }
case "$DRY_RUN" in 0|1) ;; *) die "TFB_DRY_RUN must be 0 or 1" ;; esac
case "$SKIP_STOCK" in 0|1) ;; *) die "TFB_SKIP_LIVE_STOCK must be 0 or 1" ;; esac
[ -n "$INPUT" ] || die "board path argument or TFB_BOARD is required"
[ -f "$INPUT" ] || die "missing board $INPUT"
INPUT=$(cd "$(dirname "$INPUT")" && printf '%s/%s\n' "$PWD" "$(basename "$INPUT")")
SRC_DIR=$(dirname "$INPUT")
SRC_STEM=$(basename "$INPUT" .kicad_pcb)
[ -n "$MANIFEST" ] || MANIFEST="$SRC_DIR/stack-manifest.json"
[ -f "$MANIFEST" ] || die "reviewed stack manifest is required: $MANIFEST"
MANIFEST=$(cd "$(dirname "$MANIFEST")" && printf '%s/%s\n' "$PWD" "$(basename "$MANIFEST")")
MANIFEST_DIR=$(dirname "$MANIFEST")
for ext in kicad_pcb kicad_pro kicad_sch; do
  [ -f "$SRC_DIR/$SRC_STEM.$ext" ] || die "missing companion $SRC_DIR/$SRC_STEM.$ext"
done

mkdir -p "$OUT/stage/project" "$OUT/stage/lib" "$OUT/fab" "$OUT/reports" "$OUT/assembly"
OUT=$(cd "$OUT" && pwd -P)
mkdir -p "$FAB"
FAB=$(cd "$FAB" && pwd -P)
inside() { case "$2" in "$1"/*) echo yes ;; *) echo no ;; esac; }
[ "$(inside "$ROOT" "$OUT")" = yes ] || die "build directory must remain below $ROOT: $OUT"
[ "$(inside "$ROOT" "$FAB")" = yes ] || die "fab directory must remain below $ROOT: $FAB"
[ "$(inside "$OUT" "$FAB")" = no ] || die "fab directory must not sit inside the build directory: $FAB"
[ "$(inside "$FAB" "$OUT")" = no ] || die "build directory must not sit inside the fab directory: $OUT"
for dir in "$OUT/stage/project" "$OUT/stage/lib" "$OUT/fab" "$OUT/reports" "$OUT/assembly"; do
  find "$dir" -mindepth 1 -depth -delete
done
mkdir -p "$OUT/fab/gerbers"
for ext in kicad_pcb kicad_pro kicad_sch; do
  cp "$SRC_DIR/$SRC_STEM.$ext" "$OUT/stage/project/$NAME.$ext"
done
for table in fp-lib-table sym-lib-table; do
  [ ! -f "$SRC_DIR/$table" ] || cp "$SRC_DIR/$table" "$OUT/stage/project/$table"
done
RULES=$($PY -c 'import json,sys; print(json.load(open(sys.argv[1])).get("rules") or "")' "$MANIFEST")
if [ -n "$RULES" ]; then
  [ -f "$MANIFEST_DIR/$RULES" ] || die "manifest rules missing: $MANIFEST_DIR/$RULES"
  cp "$MANIFEST_DIR/$RULES" "$OUT/stage/project/$NAME.kicad_dru"
fi
cp "$MANIFEST" "$OUT/stage/project/stack-manifest.json"
if [ -d "$ROOT/lib" ]; then
  cp -R "$ROOT/lib/." "$OUT/stage/lib/"
fi

BRD="$OUT/stage/project/$NAME.kicad_pcb"
SCH="$OUT/stage/project/$NAME.kicad_sch"
STACK="$OUT/stage/project/stack-manifest.json"
RAW_BOM="$OUT/stage/raw-bom.csv"
POS="$OUT/stage/centroid.csv"
GERB="$OUT/fab/gerbers"

SOURCES=("$INPUT" "$SRC_DIR/$SRC_STEM.kicad_sch" "$SRC_DIR/$SRC_STEM.kicad_pro" "$MANIFEST")
[ -z "$RULES" ] || SOURCES+=("$MANIFEST_DIR/$RULES")
"$PY" -c 'import hashlib,json,os,pathlib,sys
root=sys.argv[1]
data={os.path.relpath(p,root):hashlib.sha256(open(p,"rb").read()).hexdigest() for p in sys.argv[3:]}
pathlib.Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
pathlib.Path(sys.argv[2]).write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")' \
  "$ROOT" "$OUT/reports/source-sha256.json" "${SOURCES[@]}"
BOARD_SHA=$(shasum -a 256 "$BRD" | cut -d' ' -f1)
echo "0  source $BOARD_SHA"

echo "1  drc, erc, netlist"
set +e
( cd "$OUT/stage/project" && kc pcb drc --severity-all --exit-code-violations \
    --schematic-parity --format json -o "$OUT/reports/drc.json" "$BRD" )
DRC_RC=$?
set -e
case "$DRC_RC" in 0|5) ;; *) die "kicad-cli DRC exited $DRC_RC" ;; esac
[ "$BOARD_SHA" = "$(shasum -a 256 "$BRD" | cut -d' ' -f1)" ] || die "DRC mutated the staged board"
"$PY" - "$OUT/reports/drc.json" "$OUT/reports/drc-audit.json" "$BOARD_SHA" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
active = [item for item in report.get("violations", []) if not item.get("excluded")]
unconnected = report.get("unconnected_items", [])
parity = report.get("schematic_parity", [])
issues = []
if active: issues.append(f"{len(active)} active DRC violation(s)")
if unconnected: issues.append(f"{len(unconnected)} unconnected item(s)")
if parity: issues.append(f"{len(parity)} schematic parity issue(s)")
result = {"passed": not issues, "issues": issues, "board_sha256": sys.argv[3]}
out = pathlib.Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(1 if issues else 0)
PY
"$PY" "$HERE/stack/validate_stacks.py" --board "$BRD" --manifest "$STACK" \
  --drc "$OUT/reports/drc.json" --out "$OUT/reports/stack-audit.json"
"$KPY" "$HERE/validate_geometry.py" --board "$BRD" --out "$OUT/reports/geometry.json"
[ "$BOARD_SHA" = "$(shasum -a 256 "$BRD" | cut -d' ' -f1)" ] || die "validation mutated the staged board"
set +e
kc sch erc --severity-all --exit-code-violations --format json -o "$OUT/reports/erc.json" "$SCH"
ERC_RC=$?
set -e
case "$ERC_RC" in 0|5) ;; *) die "kicad-cli ERC exited $ERC_RC" ;; esac
[ -s "$OUT/reports/erc.json" ] || die "ERC report missing"
"$PY" - "$OUT/reports/erc.json" "$OUT/reports/erc-audit.json" "$BOARD_SHA" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
pending = [report]
active = []
while pending:
    node = pending.pop()
    active.extend(item for item in node.get("violations", []) if not item.get("excluded"))
    pending.extend(node.get("sheets", []))
issues = [f"{len(active)} active ERC issue(s)"] if active else []
result = {"passed": not issues, "issues": issues, "board_sha256": sys.argv[3]}
out = pathlib.Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(1 if issues else 0)
PY
kc sch export netlist --format kicadxml -o "$OUT/reports/netlist.xml" "$SCH"
"$PY" "$HERE/audit_circuit.py" --netlist "$OUT/reports/netlist.xml" --board "$BRD" \
  --out "$OUT/reports/circuit-audit.json"

echo "2  manufacturing data"
LAYERS=$("$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); import product
manifest = product.load_manifest(sys.argv[2])
copper = [suffix.rsplit(".", 1)[0].replace("_", ".") for suffix, _ in product.copper_layers(manifest)]
print(",".join(copper + ["F.Paste", "B.Paste", "F.Mask", "B.Mask", "F.Silkscreen", "B.Silkscreen", "Edge.Cuts"]))' \
  "$HERE" "$STACK")
kc pcb export gerbers -o "$GERB" -l "$LAYERS" --subtract-soldermask --check-zones "$BRD"
kc pcb export drill -o "$GERB" --format excellon --excellon-units mm --excellon-separate-th "$BRD"
kc pcb export ipcd356 -o "$OUT/fab/netlist.ipc" "$BRD"
kc sch export bom -o "$RAW_BOM" \
  --fields 'Reference,Value,Footprint,${QUANTITY},LCSC Part,Manufacturer,MPN,DNP' \
  --labels 'Designator,Value,Footprint,Quantity,LCSC Part,Manufacturer,MPN,DNP' \
  --exclude-dnp "$SCH"
kc pcb export pos -o "$POS" --format csv --units mm --side both --exclude-dnp "$BRD"
"$PY" "$HERE/validate_source_contract.py" --board "$BRD" --bom "$RAW_BOM" \
  --lib "$OUT/stage/lib" --out "$OUT/reports/source-contract.json"

echo "3  stackup data"
"$PY" "$HERE/release_data.py" stackup --board "$BRD" --manifest "$STACK" \
  --out "$OUT/fab/stackup.csv"
cp "$STACK" "$OUT/fab/stack-manifest.json"

echo "4  assembly populations"
"$PY" "$HERE/make_assembly.py" --bom "$RAW_BOM" --pos "$POS" --out-dir "$OUT/assembly"
"$PY" "$HERE/audit_assembly.py" --assembly "$OUT/assembly" --bom "$RAW_BOM" --pos "$POS" \
  --board "$BRD" --out "$OUT/reports/assembly-audit.json"
if [ "$SKIP_STOCK" != 1 ]; then
  "$PY" "$HERE/audit_stock.py" --assembly "$OUT/assembly" --board "$BRD" --out "$OUT/reports/stock-audit.json"
else
  [ "$DRY_RUN" = 1 ] || die "live stock audit cannot be skipped for a production release"
  "$PY" - "$OUT/reports/stock-audit.json" "$BOARD_SHA" <<'PY'
import datetime, json, pathlib, sys
result = {
    "checked_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "passed": False,
    "issues": ["live stock audit was skipped"],
    "board_sha256": sys.argv[2],
    "parts": [],
}
out = pathlib.Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
PY
fi

echo "5  release assertions"
validate=("$PY" "$HERE/validate_release.py" --board "$BRD" --manifest "$STACK" --fab "$GERB" \
  --drc-audit "$OUT/reports/drc-audit.json" \
  --erc-audit "$OUT/reports/erc-audit.json" \
  --stack-audit "$OUT/reports/stack-audit.json" \
  --circuit-audit "$OUT/reports/circuit-audit.json" \
  --geometry-audit "$OUT/reports/geometry.json" \
  --source-contract-audit "$OUT/reports/source-contract.json" \
  --assembly-audit "$OUT/reports/assembly-audit.json" \
  --stock-audit "$OUT/reports/stock-audit.json" \
  --out "$OUT/reports/release.json")
[ -z "$APPROVAL" ] || validate+=(--vendor-approval "$APPROVAL")
[ "$DRY_RUN" = 0 ] || validate+=(--dry-run)
"${validate[@]}"

echo "6  adopt into $(basename "$FAB")"
NEW="$OUT/adopt"
mkdir -p "$NEW"
find "$NEW" -mindepth 1 -depth -delete
cp -R "$OUT/fab/." "$NEW/"
mkdir -p "$NEW/reports"
find "$OUT/reports" -maxdepth 1 -type f \( -name '*.json' -o -name '*.csv' \) \
  -exec cp {} "$NEW/reports/" \;
cp -R "$OUT/assembly" "$NEW/assembly"
find "$NEW" -type f \( -name '*.kicad_prl' -o -name '*.pyc' -o -name '.DS_Store' \) -delete
find "$NEW" -type d -name '__pycache__' -depth -delete
"$PY" - "$NEW" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
allowed = {
    ".csv", ".drl", ".g1", ".g2", ".g3", ".g4", ".g5", ".g6", ".gbl", ".gbo", ".gbp",
    ".gbrjob", ".gbs", ".gm1", ".gtl", ".gto", ".gtp", ".gts", ".ipc", ".json",
}
bad = [str(path.relative_to(root)) for path in root.rglob("*")
       if path.is_file() and path.suffix.lower() not in allowed]
if bad:
    raise SystemExit("FAIL: forbidden release artifacts: " + ", ".join(sorted(bad)))
PY
for required in gerbers netlist.ipc stackup.csv stack-manifest.json \
                assembly/A/bom.csv assembly/A/centroid.csv \
                reports/release.json reports/source-sha256.json reports/drc.json \
                reports/drc-audit.json reports/erc.json reports/erc-audit.json \
                reports/stack-audit.json reports/geometry.json reports/circuit-audit.json \
                reports/source-contract.json reports/assembly-audit.json \
                reports/stock-audit.json; do
  [ -e "$NEW/$required" ] || die "adoption tree incomplete: $required"
done
"$PY" "$HERE/release_data.py" inventory --root "$NEW"
[ -s "$NEW/reports/artifact-inventory.json" ] || die "adoption inventory missing"

PREV="$FAB.previous.$$"
[ ! -d "$FAB" ] || mv "$FAB" "$PREV"
if ! mv "$NEW" "$FAB"; then
  [ ! -d "$PREV" ] || mv "$PREV" "$FAB"
  die "adoption swap failed; $(basename "$FAB") left untouched"
fi
[ ! -e "$PREV" ] || find "$PREV" -depth -delete
find "$OUT" -depth -delete

echo "PASS  release package adopted into $(basename "$FAB")"
