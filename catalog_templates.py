"""
Parametric Catalog Templates - Deterministic macro generator for standard industrial parts.
"""
import math
import re

def match_catalog_template(prompt: str) -> str:
    p = prompt.lower()

    # 1. T-Slot / V-Slot Structural Rail (2020, 2040, 4040)
    if ("2040" in p or "2020" in p or "4040" in p or "t-slot" in p or "v-slot" in p or "extrusion" in p) and ("rail" in p or "profile" in p or "beam" in p or "structural" in p):
        w = 40.0 if "2040" in p else (40.0 if "4040" in p else 20.0)
        h = 20.0 if "2040" in p else (40.0 if "4040" in p else 20.0)
        l = 120.0
        m_l = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:long|length)", p)
        if m_l: l = float(m_l.group(1))

        return f"""params = {{
    "width": {w},
    "height": {h},
    "length": {l},
    "slot_open": 6.0,
    "slot_internal": 10.0,
    "slot_depth": 4.5,
    "core_bore": 4.2
}}
w = params["width"]
h = params["height"]
l = params["length"]
so = params["slot_open"]
si = params["slot_internal"]
sd = params["slot_depth"]
cb = params["core_bore"]

# Solid base body
body = cq.Workplane("XY").box(w, h, l)

# Center core through-bore
core = cq.Workplane("XY").workplane(offset=-l/2.0 - 1.0).circle(cb / 2.0).extrude(l + 2.0)

# Top and Bottom slots along X-faces
pts_top_bot = [(0.0, h / 2.0), (0.0, -h / 2.0)]
t_tb = cq.Workplane("XY").workplane(offset=-l/2.0 - 1.0).pushPoints(pts_top_bot).rect(so, sd * 2.0).extrude(l + 2.0)
pts_cav_tb = [(0.0, h / 2.0 - sd / 2.0), (0.0, -h / 2.0 + sd / 2.0)]
cav_tb = cq.Workplane("XY").workplane(offset=-l/2.0 - 1.0).pushPoints(pts_cav_tb).rect(si, sd).extrude(l + 2.0)

# Side slots along Y-faces
pts_sides = [(w / 2.0, 0.0), (-w / 2.0, 0.0)]
t_s = cq.Workplane("XY").workplane(offset=-l/2.0 - 1.0).pushPoints(pts_sides).rect(sd * 2.0, so).extrude(l + 2.0)
pts_cav_s = [(w / 2.0 - sd / 2.0, 0.0), (-w / 2.0 + sd / 2.0, 0.0)]
cav_s = cq.Workplane("XY").workplane(offset=-l/2.0 - 1.0).pushPoints(pts_cav_s).rect(sd, si).extrude(l + 2.0)

result = body.cut(core).cut(t_tb).cut(cav_tb).cut(t_s).cut(cav_s)
"""

    # 2. GT2 Timing Belt Pulley (Revolved Single-Solid Hub with Tooth Cuts)
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
fl_d = max(params["flange_dia"], pitch_dia + 3.0)
fl_t = params["flange_thick"]
bw = params["belt_width"]
total_h = fl_t * 2.0 + bw

r_bore = params["bore_dia"] / 2.0
r_hub = pitch_dia / 2.0
r_fl = fl_d / 2.0

pts = [
    (r_bore, 0.0),
    (r_fl, 0.0),
    (r_fl, fl_t),
    (r_hub, fl_t),
    (r_hub, fl_t + bw),
    (r_fl, fl_t + bw),
    (r_fl, total_h),
    (r_bore, total_h)
]
body = cq.Workplane("XZ").polyline(pts).close().revolve()

pts_teeth = [((r_hub) * math.cos(2 * math.pi * i / n), (r_hub) * math.sin(2 * math.pi * i / n)) for i in range(n)]
teeth_cut = (
    cq.Workplane("XY")
    .workplane(offset=fl_t - 0.1)
    .pushPoints(pts_teeth)
    .circle(0.65)
    .extrude(bw + 0.2)
)

result = body.cut(teeth_cut)
"""

    # 3. NEMA Stepper Motor Mount Plate
    if "nema" in p or "stepper" in p or ("motor" in p and "mount" in p):
        is_nema23 = "23" in p
        size = 60.0 if is_nema23 else 44.0
        pitch = 47.14 if is_nema23 else 31.0
        pilot = 38.1 if is_nema23 else 22.0
        screw = 5.0 if is_nema23 else 3.5

        return f"""params = {{
    "plate_length": {size + 24.0},
    "plate_width": {size + 6.0},
    "thickness": 5.0,
    "pilot_dia": {pilot},
    "hole_pitch": {pitch},
    "screw_dia": {screw}
}}
pl = params["plate_length"]
pw = params["plate_width"]
t = params["thickness"]
s = params["hole_pitch"] / 2.0

result = MechanicalBuilder.prismatic_plate(
    length=pl,
    width=pw,
    thickness=t,
    center_bore=params["pilot_dia"],
    bolt_pattern={{"spacing_x": params["hole_pitch"], "spacing_y": params["hole_pitch"], "dia": params["screw_dia"]}},
    relief_slots=[{{"width": 5.5, "length": 14.0, "pts": [(-pw * 0.3, pl / 2.0 - 10.0), (pw * 0.3, pl / 2.0 - 10.0)]}}],
    corner_radius=3.0
)
"""

    # 4. Lathe Thumbwheel / Knurled Knob
    if "thumbwheel" in p or "knurled" in p or "knob" in p or "handwheel" in p:
        return """params = {
    "outer_dia": 55.0,
    "thickness": 14.0,
    "bore_dia": 12.0,
    "scallop_count": 8,
    "scallop_dia": 7.5
}
result = MechanicalBuilder.turned_concentric(
    steps=[{"dia": params["outer_dia"], "height": params["thickness"]}],
    bore=params["bore_dia"],
    radial_features={"count": int(params["scallop_count"]), "dia": params["scallop_dia"]}
)
"""

    # 5. Pipe / Tube Flange
    if "flange" in p:
        od, bore = 90.0, 30.0
        m_od = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:outer|dia)", p)
        if m_od: od = float(m_od.group(1))
        m_b = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:bore|inner)", p)
        if m_b: bore = float(m_b.group(1))

        return f"""params = {{
    "outer_dia": {od},
    "thickness": 10.0,
    "bore_dia": {bore},
    "pcd": {(od + bore) / 2.0},
    "bolt_count": 4,
    "bolt_dia": 8.0
}}
result = MechanicalBuilder.turned_concentric(
    steps=[{{"dia": params["outer_dia"], "height": params["thickness"]}}],
    bore=params["bore_dia"],
    bolt_circle={{"count": int(params["bolt_count"]), "pcd": params["pcd"], "dia": params["bolt_dia"]}}
)
"""

    # 6. Extruded Cooling Heatsink
    if "heatsink" in p or "heat sink" in p:
        return """params = {
    "base_width": 60.0,
    "base_length": 60.0,
    "base_thick": 4.0,
    "fin_height": 22.0,
    "fin_thick": 1.8,
    "fin_count": 6
}
bw, bl, bt = params["base_width"], params["base_length"], params["base_thick"]
fh, ft = params["fin_height"], params["fin_thick"]
n = int(params["fin_count"])

base = cq.Workplane("XY").box(bw, bl, bt, centered=(True, True, False))
pitch = (bl - ft) / (n - 1)
fins = cq.Workplane("XY")
for i in range(n):
    y_pos = -bl / 2.0 + ft / 2.0 + i * pitch
    fin = cq.Workplane("XY").workplane(offset=bt).center(0, y_pos).box(bw, ft, fh, centered=(True, True, False))
    fins = fins.union(fin)

result = base.union(fins)
"""

    # 7. Heavy-Duty L-Bracket
    if "bracket" in p or "angle" in p:
        return """params = {
    "length": 60.0,
    "width": 50.0,
    "wall_height": 50.0,
    "thickness": 5.0,
    "base_hole": 6.0,
    "wall_hole": 16.0
}
t = params["thickness"]
l, h, w = params["length"], params["wall_height"], params["width"]
pts = [(0.0, 0.0), (l, 0.0), (l, t), (t, t), (t, h), (0.0, h)]

result = MechanicalBuilder.profile_extruded(
    pts=pts,
    length=w,
    holes=[
        {"face": ">Z", "offset": (l * 0.7, 0.0), "dia": params["base_hole"]},
        {"face": ">X", "offset": (0.0, h * 0.6), "dia": params["wall_hole"]}
    ]
)
"""

    return None
