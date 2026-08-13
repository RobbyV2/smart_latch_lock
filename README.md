# Triangle Flywheel Balancer

This repository holds the KiCad hardware design for the triangle flywheel balancer board. The board is a 4-layer rigid PCB with a 1.6 mm finished thickness. The schematic, the board, the part libraries, and the fabrication scripts live here. The design is not complete, so the specifications below list only the values that are fixed.

<table>
<tr>
<td><img src="3d/top.png" alt="Top view of the board" width="100%"></td>
<td><img src="3d/bottom.png" alt="Bottom view of the board" width="100%"></td>
<td><img src="3d/iso.png" alt="Angled view of the board" width="100%"></td>
</tr>
</table>

## Specifications

| Item | Value |
|---|---|
| Board size | TBD |
| Copper layers | 4 |
| Finished thickness | 1.6 mm |
| Surface finish | TBD |

Read `docs/design.md` for the full stack table and the via inventory.

## Repository layout

- `hw/` holds the KiCad schematic, the board, the design rules, and the stack manifest.
- `lib/` holds the symbols, the footprints, and the 3D models.
- `scripts/` holds the release script, the panel tools, and the validation scripts.
- `fab/` holds the fabrication data, written by `scripts/release.sh`.
- `docs/` holds the design specification and the vendor order gate.
- `3d/` holds the 3D build script, the three renders, and the viewer page.

## Build the 3D output
```
python3 3d/build.py
```

## Build the fabrication tree
```
TFB_DRY_RUN=1 scripts/release.sh hw/triangle_flywheel_balancer.kicad_pcb
```
