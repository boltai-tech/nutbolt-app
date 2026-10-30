"""Mechatronics Mounts, Pillow Blocks & Linear Hardware"""
import math
import re

def match(prompt: str) -> str:
    p = prompt.lower()

    # 1. NEMA 17 / NEMA 23 Stepper Motor Mounting Plate with Tension Slots
    if "nema" in p or "stepper motor" in p or "motor mount" in p:
        is_nema23 = "23" in p
        size = 60.0 if is_nema23 else 42.0
        pitch = 47.14 if is_nema23 else 31.0
        pilot = 38.1 if is_nema23 else 22.0
        screw = 5.0 if is_nema23 else 3.5

        return f"""params = {{
    "plate_width": {size + 8.0},
    "plate_length": {size + 24.0},
    "thickness": 5.0,
    "pilot_dia": {pilot},
    "bolt_spacing": {pitch},
    "motor_screw": {screw}
}}
pw, pl, t = params["plate_width"], params["plate_length"], params["thickness"]
s = params["bolt_spacing"] / 2.0

body = cq.Workplane("XY").box(pw, pl, t)
pilot = cq.Workplane("XY").workplane(offset=-t - 1).circle(params["pilot_dia"] / 2.0).extrude(t * 3)
motor_holes = cq.Workplane("XY").workplane(offset=-t - 1).pushPoints([(-s, -s), (s, -s), (-s, s), (s, s)]).circle(params["motor_screw"] / 2.0).extrude(t * 3)

# Belt tensioner adjustment slots
slot_y = pl/2.0 - 10.0
slots = cq.Workplane("XY").workplane(offset=-t - 1).pushPoints([(-pw*0.3, slot_y), (pw*0.3, slot_y)]).rect(5.5, 14.0).extrude(t * 3)

result = body.cut(pilot).cut(motor_holes).cut(slots)
"""

    # 2. Pillow Block Bearing Mount (608 / KP08)
    if "pillow block" in p or ("bearing" in p and ("housing" in p or "mount" in p or "block" in p)):
        bearing_od = 22.0  # standard 608 skate / 3D printer bearing
        if "6200" in p: bearing_od = 30.0

        return f"""params = {{
    "bearing_od": {bearing_od},
    "housing_width": {bearing_od + 24.0},
    "housing_height": {bearing_od + 18.0},
    "thickness": 14.0,
    "mount_hole": 5.0,
    "mount_pitch": {bearing_od + 14.0}
}}
hw, hh, t = params["housing_width"], params["housing_height"], params["thickness"]
bod = params["bearing_od"]
mp = params["mount_pitch"] / 2.0

body = cq.Workplane("XY").box(hw, hh, t)
bore = cq.Workplane("XY").workplane(offset=-t - 1).circle(bod / 2.0).extrude(t * 3)
base_mounts = cq.Workplane("XY").workplane(offset=-t - 1).pushPoints([(-mp, 0), (mp, 0)]).circle(params["mount_hole"] / 2.0).extrude(t * 3)

result = body.cut(bore).cut(base_mounts)
"""

    # 3. T8 Leadscrew Brass Nut Mounting Bracket
    if "leadscrew" in p or "t8" in p or "anti-backlash" in p:
        return """params = {
    "width": 34.0,
    "length": 30.0,
    "height": 28.0,
    "nut_bore": 10.5,
    "flange_pitch": 16.0,
    "nut_screws": 3.5
}
w, l, h = params["width"], params["length"], params["height"]
body = cq.Workplane("XY").box(w, l, h)

# Center pass-through bore
bore = cq.Workplane("XY").workplane(offset=-h/2 - 1).circle(params["nut_bore"] / 2.0).extrude(h + 2)

# 4 nut flange mounting holes
p = params["flange_pitch"] / 2.0
nut_holes = cq.Workplane("XY").workplane(offset=-h/2 - 1).pushPoints([(-p, -p), (p, -p), (-p, p), (p, p)]).circle(params["nut_screws"] / 2.0).extrude(h + 2)

# Gantry mount side holes
gantry_holes = cq.Workplane("XZ").workplane(offset=-l/2 - 1).pushPoints([(-w*0.3, 0), (w*0.3, 0)]).circle(2.5).extrude(l + 2)

result = body.cut(bore).cut(nut_holes).cut(gantry_holes)
"""

    return None
