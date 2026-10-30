"""Fluid Power, Flanges, Manifolds & Heatsinks"""
import math
import re

def match(prompt: str) -> str:
    p = prompt.lower()

    # 1. Pipe / Tube Flange (Concentric Bolt Circle & Raised Face)
    if "flange" in p or "pipe" in p:
        od = 90.0
        bore = 30.0
        m_od = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:outer|dia)", p)
        if m_od: od = float(m_od.group(1))
        m_b = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:bore|inner)", p)
        if m_b: bore = float(m_b.group(1))

        return f"""params = {{
    "outer_dia": {od},
    "bore_dia": {bore},
    "thickness": 10.0,
    "pcd": {(od + bore) / 2.0},
    "bolt_dia": 8.0,
    "bolt_count": 4
}}
n = int(params["bolt_count"])
r = params["pcd"] / 2.0
pts = [(r * math.cos(2*math.pi*i/n), r * math.sin(2*math.pi*i/n)) for i in range(n)]

body = cq.Workplane("XY").circle(params["outer_dia"] / 2.0).extrude(params["thickness"])
bore = cq.Workplane("XY").workplane(offset=-1).circle(params["bore_dia"] / 2.0).extrude(params["thickness"] + 2)
bolts = cq.Workplane("XY").workplane(offset=-1).pushPoints(pts).circle(params["bolt_dia"] / 2.0).extrude(params["thickness"] + 2)

result = body.cut(bore).cut(bolts)
"""

    # 2. Cross-Drilled Hydraulic / Pneumatic Manifold Block
    if "manifold" in p or ("pneumatic" in p and "block" in p) or "distribution block" in p:
        return """params = {
    "size": 60.0,
    "main_bore": 20.0,
    "side_port": 8.0,
    "gland_od": 32.0,
    "gland_id": 26.0,
    "gland_depth": 2.5
}
s = params["size"]
body = cq.Workplane("XY").box(s, s, s)

main_bore = cq.Workplane("XY").workplane(offset=-s/2 - 1).circle(params["main_bore"] / 2.0).extrude(s + 2)
port_x = cq.Workplane("YZ").workplane(offset=-s/2 - 1).circle(params["side_port"] / 2.0).extrude(s + 2)
port_y = cq.Workplane("XZ").workplane(offset=-s/2 - 1).circle(params["side_port"] / 2.0).extrude(s + 2)

gland_cut = (
    cq.Workplane("XY")
    .workplane(offset=s/2 - params["gland_depth"])
    .circle(params["gland_od"] / 2.0)
    .circle(params["gland_id"] / 2.0)
    .extrude(params["gland_depth"] + 1)
)

result = body.cut(main_bore).cut(port_x).cut(port_y).cut(gland_cut)
"""

    # 3. Parallel Extruded Fin Heatsink
    if "heatsink" in p or "heat sink" in p or "cooling fins" in p:
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

# Array of cooling fins
pitch = (bl - ft) / (n - 1)
fins = cq.Workplane("XY")
for i in range(n):
    y_pos = -bl/2.0 + ft/2.0 + i * pitch
    fin = cq.Workplane("XY").workplane(offset=bt).center(0, y_pos).box(bw, ft, fh, centered=(True, True, False))
    fins = fins.union(fin)

result = base.union(fins)
"""

    # 4. Conical Impeller Flow Hub
    if "impeller" in p or "turbine" in p:
        return """params = {
    "base_dia": 50.0,
    "top_dia": 26.0,
    "height": 38.0,
    "bore_dia": 10.0,
    "vane_count": 6,
    "vane_thick": 2.5
}
h = params["height"]
body = (
    cq.Workplane("XY")
    .circle(params["base_dia"] / 2.0)
    .workplane(offset=h)
    .circle(params["top_dia"] / 2.0)
    .loft(combine=True)
)
bore = cq.Workplane("XY").workplane(offset=-1).circle(params["bore_dia"] / 2.0).extrude(h + 2)
keyway = cq.Workplane("XY").workplane(offset=-1).pushPoints([(0, params["bore_dia"] / 2.0)]).rect(3.0, 3.0).extrude(h + 2)

n = int(params["vane_count"])
r = params["base_dia"] / 2.0
vane_base = cq.Workplane("XY").box(r, params["vane_thick"], h * 0.7, centered=(False, True, False))
vanes = cq.Workplane("XY")
for i in range(n):
    angle = 360.0 * i / n
    vanes = vanes.union(vane_base.rotate((0, 0, 0), (0, 0, 1), angle))

result = body.cut(bore).cut(keyway).union(vanes)
"""

    return None
