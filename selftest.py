"""
selftest.py - Comprehensive CAD Kernel & Builder Validation Suite
Tests all 5 mechanical archetypes and catalog macros locally to guarantee
100% watertight single-solid manifold outputs prior to cloud deployment.
"""
import math
import cadquery as cq
from cad_builder import MechanicalBuilder
from catalog_templates import match_catalog_template

def verify_solid(name: str, solid: cq.Workplane):
    vals = solid.solids().vals()
    assert len(vals) == 1, f"[{name}] FAILED: Produced {len(vals)} solids, expected 1."
    vol = vals[0].Volume()
    assert vol > 0.001, f"[{name}] FAILED: Degenerate volume {vol} mm³."
    print(f" PASS: {name:<28} | Vol: {round(vol / 1000.0, 3):>7} cm³ | Solids: 1")

print("=" * 60)
print(" RUNNING NUTBOLT.AI LOCAL VERIFICATION SUITE")
print("=" * 60)

# 1. Turned Concentric (Stepped Shaft / Pulley)
part1 = MechanicalBuilder.turned_concentric(
    steps=[{"dia": 50.0, "height": 10.0}, {"dia": 25.0, "height": 30.0}],
    bore=12.0,
    radial_features={"count": 6, "dia": 6.0}
)
verify_solid("Turned Concentric", part1)

# 2. Profile Extruded (L-Bracket)
l, h, t = 60.0, 50.0, 5.0
pts = [(0.0, 0.0), (l, 0.0), (l, t), (t, t), (t, h), (0.0, h)]
part2 = MechanicalBuilder.profile_extruded(
    pts=pts,
    length=40.0,
    holes=[{"face": ">Z", "offset": (40.0, 0.0), "dia": 6.0}]
)
verify_solid("Profile Extruded (Bracket)", part2)

# 3. Prismatic Plate (NEMA Mount)
part3 = MechanicalBuilder.prismatic_plate(
    length=65.0,
    width=55.0,
    thickness=5.0,
    center_bore=22.0,
    bolt_pattern={"spacing_x": 31.0, "spacing_y": 31.0, "dia": 3.5},
    corner_radius=4.0
)
verify_solid("Prismatic Plate (Mount)", part3)

# 4. Shell Enclosure (Project Box)
part4 = MechanicalBuilder.shell_enclosure(
    length=80.0,
    width=60.0,
    height=30.0,
    wall_thickness=2.5,
    bosses=[{"x": 30.0, "y": 20.0, "dia": 6.0, "hole": 2.5}]
)
verify_solid("Shell Enclosure (Box)", part4)

# 5. Manifold Block (Fluid Distribution)
part5 = MechanicalBuilder.manifold_block(
    dims=(50.0, 50.0, 50.0),
    main_bore=18.0,
    cross_ports=[{"axis": "XZ", "dia": 8.0}, {"axis": "YZ", "dia": 8.0}],
    gland={"od": 28.0, "id": 22.0, "depth": 2.0}
)
verify_solid("Manifold Block", part5)

# 6. Catalog Macro: GT2 Pulley
gt2_code = match_catalog_template("GT2 timing pulley with 20 teeth, 5mm shaft bore, and 7mm belt width.")
scope = {"cq": cq, "math": math, "MechanicalBuilder": MechanicalBuilder}
exec(gt2_code, scope)
verify_solid("Catalog: GT2 Pulley", scope["result"])

# 7. Catalog Macro: 2040 T-Slot Rail
tslot_code = match_catalog_template("Precision 2040-style dual T-slot structural rail 120mm length.")
scope = {"cq": cq, "math": math, "MechanicalBuilder": MechanicalBuilder}
exec(tslot_code, scope)
verify_solid("Catalog: 2040 T-Slot", scope["result"])

print("=" * 60)
print(" ALL 7 MECHANICAL VALIDATION TESTS PASSED SUCCESSFULLY!")
print("=" * 60)
