import hashlib, json, pathlib, re

NAME = "triangle_flywheel_balancer"
ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_COPPER = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
INNER = re.compile(r"In(\d+)\.Cu")


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def load_manifest(path):
    return json.loads(pathlib.Path(path).read_text())


def copper_layers(manifest):
    names = tuple((manifest.get("layer_stack") or {}).get("copper_layers") or DEFAULT_COPPER)
    count = len(names)
    layers = []
    for name in names:
        inner = INNER.fullmatch(name)
        if name == "F.Cu":
            layers.append(("F_Cu.gtl", "Copper,L1,Top"))
        elif name == "B.Cu":
            layers.append(("B_Cu.gbl", f"Copper,L{count},Bot"))
        elif inner:
            index = int(inner.group(1))
            layers.append((f"In{index}_Cu.g{index}", f"Copper,L{index + 1},Inr"))
        else:
            raise ValueError(f"unrecognized copper layer {name}")
    return tuple(layers)


def drill_specs(manifest):
    count = len(copper_layers(manifest))
    return (("PTH", f"Plated,1,{count},PTH"), ("NPTH", f"NonPlated,1,{count},NPTH"))


def file_function(path):
    match = re.search(r"TF.FileFunction,([^*%\r\n]+)", pathlib.Path(path).read_text(errors="replace"))
    return match.group(1) if match else None
