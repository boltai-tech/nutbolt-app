"""Power Transmission (Gears, GT2 Pulleys, Couplers, Geneva Mechanism)"""
import math
import re

def match(prompt: str) -> str:
    p = prompt.lower()

    # 1. GT2 Timing Belt Pulley
    if "gt2" in p or ("timing" in p and "pulley" in p) or ("belt" in p and "pulley" in p):
        teeth = 20
        bore = 5.0
        belt = 7.0
        m_t = re.search(r"(\d+)\s*(?:t|tooth|teeth)", p)
        if m_t: teeth = int(m_t.group(1))
        m_b = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:bore|shaft)", p)
        if m_b: bore = float(m_b.group(1))
        m_w = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:width|belt)", p)
        if m_w: belt = float(m_w.group(1))

        return f"""params = {{
    "teeth": {teeth},
    "bore_dia": {bore},
    "belt_width": {belt},
    "flange_dia": 18.0,
    "flange_thick": 1.2
}}
n = int(params["teeth"])
pitch = 2.0
pitch_dia = (n * pitch) / math.pi
root_dia = pitch_dia - 0.764
fl_d = max(params["flange_dia"], pitch_dia + 3.0)
fl_t = params["flange_thick"]
bw = params["belt_width"]
total_h = fl_t * 2.0 + bw

# 1. Solid cylinder encompassing the entire outer diameter and flanges
body = cq.Workplane("XY").circle(fl_d / 2.0).extrude(total_h)

# 2. Central shaft bore
bore = cq.Workplane("XY").workplane(offset=-1).circle(params["bore_dia"] / 2.0).extrude(total_h + 2.0)

# 3. Cut the belt recess between the top and bottom flanges
groove = (
    cq.Workplane("XY")
    .workplane(offset=fl_t)
    .circle((fl_d + 4.0) / 2.0)
    .circle(root_dia / 2.0)
    .extrude(bw)
)

# 4. Cut the 20 tooth grooves into the pitch diameter
pts = [( (pitch_dia/2.0) * math.cos(2*math.pi*i/n), (pitch_dia/2.0) * math.sin(2*math.pi*i/n) ) for i in range(n)]
teeth_cut = (
    cq.Workplane("XY")
    .workplane(offset=fl_t - 0.5)
    .pushPoints(pts)
    .circle(0.65)
    .extrude(bw + 1.0)
)

result = body.cut(bore).cut(groove).cut(teeth_cut)
"""

    # 2. Parametric Spur Gear / Pinion
    if "gear" in p or "pinion" in p:
        teeth = 16
        m_t = re.search(r"(\d+)\s*(?:t|tooth|teeth)", p)
        if m_t: teeth = int(m_t.group(1))

        return f"""params = {{
    "teeth": {teeth},
    "module": 2.0,
    "face_width": 12.0,
    "bore_dia": 8.0,
    "keyway_width": 2.5
}}
m = params["module"]
n = int(params["teeth"])
pitch_dia = m * n
outer_dia = pitch_dia + 2.0 * m
root_dia = pitch_dia - 2.5 * m
w = params["face_width"]

body = cq.Workplane("XY").circle(outer_dia / 2.0).extrude(w)
bore = cq.Workplane("XY").workplane(offset=-1).circle(params["bore_dia"] / 2.0).extrude(w + 2)
keyway = cq.Workplane("XY").workplane(offset=-1).pushPoints([(0, params["bore_dia"] / 2.0)]).rect(params["keyway_width"], 3.0).extrude(w + 2)

r = (pitch_dia + root_dia) / 4.0
pts = [(r * math.cos(2*math.pi*i/n), r * math.sin(2*math.pi*i/n)) for i in range(min(n, 20))]
tooth_cuts = cq.Workplane("XY").workplane(offset=-1).pushPoints(pts).circle(m * 0.78).extrude(w + 2)

result = body.cut(bore).cut(keyway).cut(tooth_cuts)
"""

    # 3. Rigid Flanged Shaft Coupler
    if "coupler" in p or "coupling" in p or "shaft collar" in p:
        return """params = {
    "outer_dia": 32.0,
    "length": 40.0,
    "bore_1": 8.0,
    "bore_2": 10.0,
    "clamp_screw": 3.2
}
od, l = params["outer_dia"], params["length"]
b1, b2 = params["bore_1"], params["bore_2"]

body = cq.Workplane("XY").circle(od / 2.0).extrude(l)
bore1 = cq.Workplane("XY").workplane(offset=-1).circle(b1 / 2.0).extrude(l/2.0 + 1)
bore2 = cq.Workplane("XY").workplane(offset=l/2.0).circle(b2 / 2.0).extrude(l/2.0 + 1)
set_screws = (
    cq.Workplane("YZ")
    .workplane(offset=-od/2 - 1)
    .pushPoints([(0, l*0.25), (0, l*0.75)])
    .circle(params["clamp_screw"] / 2.0)
    .extrude(od + 2)
)
result = body.cut(bore1).cut(bore2).cut(set_screws)
"""

    # 4. Ergonomic Lathe Thumbwheel / Knurled Grip Knob
    if "thumbwheel" in p or "knurled" in p or "handwheel" in p or "knob" in p:
        return """params = {
    "outer_dia": 55.0,
    "thickness": 14.0,
    "bore_dia": 12.0,
    "scallop_count": 8,
    "scallop_radius": 3.8
}
od, th, bd = params["outer_dia"], params["thickness"], params["bore_dia"]
n = int(params["scallop_count"])
sr = params["scallop_radius"]
r = od / 2.0

pts = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
body = cq.Workplane("XY").circle(r).extrude(th)
bore = cq.Workplane("XY").workplane(offset=-1).circle(bd / 2.0).extrude(th + 2)
scallops = cq.Workplane("XY").workplane(offset=-1).pushPoints(pts).circle(sr).extrude(th + 2)
result = body.cut(bore).cut(scallops)
"""

    # 5. Geneva Drive Mechanism Indexing Wheel
    if "geneva" in p or "indexing wheel" in p:
        return """params = {
    "outer_dia": 80.0,
    "thickness": 8.0,
    "bore_dia": 12.0,
    "slot_width": 6.0,
    "lock_radius": 22.0
}
od, th = params["outer_dia"], params["thickness"]
r = od / 2.0
body = cq.Workplane("XY").circle(r).extrude(th)
bore = cq.Workplane("XY").workplane(offset=-1).circle(params["drive_bore"] / 2.0).extrude(th + 2)
slot_x = cq.Workplane("XY").workplane(offset=-1).rect(od + 2, params["slot_width"]).extrude(th + 2)
slot_y = cq.Workplane("XY").workplane(offset=-1).rect(params["slot_width"], od + 2).extrude(th + 2)

lock_pts = [(r * math.cos(math.pi/4 + i * math.pi/2), r * math.sin(math.pi/4 + i * math.pi/2)) for i in range(4)]
locks = cq.Workplane("XY").workplane(offset=-1).pushPoints(lock_pts).circle(params["lock_radius"]).extrude(th + 2)
result = body.cut(bore).cut(slot_x).cut(slot_y).cut(locks)
"""

    return None
