"""Structural & Extrusion Profiles (T-Slot, V-Slot, Channels, Brackets)"""
import re

def match(prompt: str) -> str:
    p = prompt.lower()

    # 1. T-Slot / V-Slot Structural Aluminum Extrusion (2020, 2040, 4040)
    if ("t-slot" in p or "v-slot" in p or "2040" in p or "2020" in p or "4040" in p or "extrusion" in p) and ("rail" in p or "profile" in p or "beam" in p or "structural" in p or "bar" in p):
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
w, h, l = params["width"], params["height"], params["length"]
so, si, sd, cb = params["slot_open"], params["slot_internal"], params["slot_depth"], params["core_bore"]

body = cq.Workplane("XY").box(w, h, l)
core = cq.Workplane("XY").workplane(offset=-l/2 - 1).circle(cb / 2.0).extrude(l + 2)

# Top & Bottom Slots
t_tb = cq.Workplane("XY").workplane(offset=-l/2 - 1).pushPoints([(0, h/2), (0, -h/2)]).rect(so, sd*2).extrude(l + 2)
cav_tb = cq.Workplane("XY").workplane(offset=-l/2 - 1).pushPoints([(0, h/2 - sd/2), (0, -h/2 + sd/2)]).rect(si, sd).extrude(l + 2)

# Side Slots
t_s = cq.Workplane("XY").workplane(offset=-l/2 - 1).pushPoints([(w/2, 0), (-w/2, 0)]).rect(sd*2, so).extrude(l + 2)
cav_s = cq.Workplane("XY").workplane(offset=-l/2 - 1).pushPoints([(w/2 - sd/2, 0), (-w/2 + sd/2, 0)]).rect(sd, si).extrude(l + 2)

result = body.cut(core).cut(t_tb).cut(cav_tb).cut(t_s).cut(cav_s)
"""

    # 2. Structural U-Channel / C-Channel Beam
    if "u-channel" in p or "c-channel" in p or ("channel" in p and "beam" in p):
        return """params = {
    "width": 80.0,
    "flange_height": 40.0,
    "thickness": 6.0,
    "length": 120.0,
    "mount_hole": 8.0
}
w, h, t, l = params["width"], params["flange_height"], params["thickness"], params["length"]
pts = [(0,0), (w,0), (w,h), (w-t,h), (w-t,t), (t,t), (t,h), (0,h)]
body = cq.Workplane("XZ").polyline(pts).close().extrude(l / 2.0, both=True)
holes = cq.Workplane("XY").workplane(offset=-t - 1).pushPoints([(w/2, -l*0.25), (w/2, l*0.25)]).circle(params["mount_hole"] / 2.0).extrude(t * 3)
result = body.cut(holes)
"""

    # 3. Heavy-Duty Gusseted / 90-Degree L-Bracket
    if "bracket" in p or "angle iron" in p or "l-shape" in p or "corner gusset" in p:
        return """params = {
    "width": 50.0,
    "base_length": 60.0,
    "wall_height": 50.0,
    "thickness": 5.0,
    "base_hole": 6.0,
    "wall_hole": 16.0
}
t = params["thickness"]
pts = [(0,0), (params["base_length"],0), (params["base_length"],t), (t,t), (t,params["wall_height"]), (0,params["wall_height"])]
body = cq.Workplane("XZ").polyline(pts).close().extrude(params["width"] / 2.0, both=True)
base_cut = cq.Workplane("XY").workplane(offset=-t - 1).pushPoints([(params["base_length"] * 0.7, -params["width"] * 0.25), (params["base_length"] * 0.7, params["width"] * 0.25)]).circle(params["base_hole"] / 2.0).extrude(t * 3)
wall_cut = cq.Workplane("YZ").workplane(offset=-t - 1).center(0, params["wall_height"] * 0.6).circle(params["wall_hole"] / 2.0).extrude(t * 3)
result = body.cut(base_cut).cut(wall_cut)
"""

    # 4. Hinge / Clevis Pivot Bracket
    if "clevis" in p or "pivot bracket" in p or "hinge" in p:
        return """params = {
    "length": 70.0,
    "width": 40.0,
    "height": 35.0,
    "wall_thick": 5.0,
    "pin_hole": 10.0,
    "slot_width": 20.0
}
l, w, h, t = params["length"], params["width"], params["height"], params["wall_thick"]
sw, ph = params["slot_width"], params["pin_hole"]
body = cq.Workplane("XY").box(l, w, h)
center_slot = cq.Workplane("XY").workplane(offset=0).rect(l + 2, sw).extrude(h)
pin_bore = cq.Workplane("YZ").workplane(offset=-w/2 - 1).center(0, h*0.2).circle(ph / 2.0).extrude(w + 2)
base_mount = cq.Workplane("XY").workplane(offset=-h/2 - 1).pushPoints([(-l*0.35, 0), (l*0.35, 0)]).circle(3.5).extrude(h/2)
result = body.cut(center_slot).cut(pin_bore).cut(base_mount)
"""

    return None
