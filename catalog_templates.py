"""
Parametric catalog templates for mechanical standards.
Provides instant (<1.5s), zero-LLM deterministic generation for nutbolt.ai
"""
import math
import re
import cadquery as cq
from cad_builder import BuilderError, MechanicalBuilder, _clean, _cut, _cyl, _fuse, _num, _int, _wp, V

mb = MechanicalBuilder()

# --------------------------------------------------------------------------- #
# 1. RS-775 PUMP SUITE GENERATORS
# --------------------------------------------------------------------------- #

def rs775_pump_housing(chamber_dia=52.0, chamber_depth=18.0, wall=3.0, outlet_od=12.0, outlet_id=8.0):
    cd = _num(chamber_dia, "chamber_dia", 30.0, 100.0)
    ch = _num(chamber_depth, "chamber_depth", 10.0, 50.0)
    w = _num(wall, "wall", 2.0, 8.0)
    ood = _num(outlet_od, "outlet_od", 6.0, 25.0)
    oid = min(_num(outlet_id, "outlet_id", 3.0, ood - 2.0), ood - 1.5)
    
    base_t = 4.0
    total_h = ch + base_t
    od = cd + 2 * w
    
    # Main outer body and interior impeller chamber
    body = cq.Workplane("XY").circle(od / 2.0).extrude(total_h)
    cavity = cq.Solid.makeCylinder(cd / 2.0, ch + 2.0, V(0, 0, base_t), V(0, 0, 1))
    
    # Motor mounting face: 17.8mm boss clearance, 7mm shaft pass, 2x M4 at 29mm PCD
    boss_hole = cq.Solid.makeCylinder(17.8 / 2.0, base_t + 2.0, V(0, 0, -1.0), V(0, 0, 1))
    shaft_hole = cq.Solid.makeCylinder(7.0 / 2.0, total_h + 2.0, V(0, 0, -1.0), V(0, 0, 1))
    m4_1 = cq.Solid.makeCylinder(4.5 / 2.0, base_t + 2.0, V(14.5, 0, -1.0), V(0, 0, 1))
    m4_2 = cq.Solid.makeCylinder(4.5 / 2.0, base_t + 2.0, V(-14.5, 0, -1.0), V(0, 0, 1))
    
    # 4x M3 perimeter holes for the suction cap
    pcd = od - 3.5
    f_holes = []
    for ang in (45, 135, 225, 315):
        rad = math.radians(ang)
        x = (pcd / 2.0) * math.cos(rad)
        y = (pcd / 2.0) * math.sin(rad)
        f_holes.append(cq.Solid.makeCylinder(3.2 / 2.0, total_h + 2.0, V(x, y, -1.0), V(0, 0, 1)))
        
    # Tangential discharge outlet pipe
    pipe_len = 22.0
    tangent_y = cd / 2.0 - ood / 2.0 + 1.0
    pipe_z = base_t + ch / 2.0
    pipe_outer = cq.Solid.makeCylinder(ood / 2.0, pipe_len + od / 2.0, V(0, tangent_y, pipe_z), V(1, 0, 0))
    pipe_bore = cq.Solid.makeCylinder(oid / 2.0, pipe_len + od + 4.0, V(-2.0, tangent_y, pipe_z), V(1, 0, 0))
    
    fused = _fuse(body, [pipe_outer])
    tools = [cavity, boss_hole, shaft_hole, pipe_bore, m4_1, m4_2] + f_holes
    return _cut(fused, tools)


def rs775_pump_impeller(diameter=46.0, height=14.0, bore=5.0, vanes=6, base_t=2.5):
    d = _num(diameter, "diameter", 20.0, 95.0)
    h = _num(height, "height", 6.0, 40.0)
    b = _num(bore, "bore", 2.0, 12.0)
    n = _int(vanes, "vanes", 3, 12)
    bt = _num(base_t, "base_t", 1.5, 6.0)
    
    base_plate = cq.Workplane("XY").circle(d / 2.0).extrude(bt)
    hub_d = max(b + 5.0, 11.0)
    hub = cq.Solid.makeCylinder(hub_d / 2.0, h, V(0, 0, 0), V(0, 0, 1))
    
    blade_h = h - bt
    r_in = hub_d / 2.0 + 0.5
    r_out = d / 2.0 - 0.5
    v_parts = []
    
    for i in range(n):
        ang = 2.0 * math.pi * i / n
        pts = []
        for s in range(11):
            t = s / 10.0
            r = r_in + (r_out - r_in) * t
            a = ang + (0.55 * t * t)
            pts.append((r * math.cos(a), r * math.sin(a)))
        for s in reversed(range(11)):
            t = s / 10.0
            r = r_in + (r_out - r_in) * t
            a = ang + (0.55 * t * t) + (2.0 / r)
            pts.append((r * math.cos(a), r * math.sin(a)))
            
        blade = (cq.Workplane("XY").workplane(offset=bt)
                 .polyline(pts).close().extrude(blade_h)).val()
        v_parts.append(blade)
        
    solid = _fuse(base_plate, [hub] + v_parts)
    return _cut(solid, [_cyl(b / 2.0, h + 4.0, 0, 0, -2.0, (0, 0, 1))])


def rs775_pump_cap(outer_dia=58.0, thickness=3.0, inlet_od=14.0, inlet_id=10.0, inlet_len=22.0):
    od = _num(outer_dia, "outer_dia", 35.0, 110.0)
    t = _num(thickness, "thickness", 2.0, 8.0)
    iod = _num(inlet_od, "inlet_od", 6.0, 30.0)
    iid = min(_num(inlet_id, "inlet_id", 3.0, iod - 2.0), iod - 1.5)
    L = _num(inlet_len, "inlet_len", 8.0, 50.0)
    
    disk = cq.Workplane("XY").circle(od / 2.0).extrude(t)
    pipe = cq.Solid.makeCylinder(iod / 2.0, L, V(0, 0, t), V(0, 0, 1))
    pipe_bore = cq.Solid.makeCylinder(iid / 2.0, L + t + 4.0, V(0, 0, -2.0), V(0, 0, 1))
    
    f_holes = []
    pcd = od - 3.5
    for ang in (45, 135, 225, 315):
        rad = math.radians(ang)
        x = (pcd / 2.0) * math.cos(rad)
        y = (pcd / 2.0) * math.sin(rad)
        f_holes.append(cq.Solid.makeCylinder(3.2 / 2.0, t + 4.0, V(x, y, -2.0), V(0, 0, 1)))
        
    body = _fuse(disk, [pipe])
    return _cut(body, [pipe_bore] + f_holes)

# --------------------------------------------------------------------------- #
# 2. EXISTING MECHANICAL CATALOG
# --------------------------------------------------------------------------- #

def spur_gear(module=0.91, teeth=15, thickness=15.0, bore=5.0):
    m = _num(module, "module", 0.3, 10.0)
    z = _int(teeth, "teeth", 6, 120)
    th = _num(thickness, "thickness", 2.0, 100.0)
    b = _num(bore, "bore", 0.0, 50.0)
    
    pitch_dia = m * z
    addendum = 1.0 * m
    dedendum = 1.25 * m
    da = pitch_dia + 2 * addendum
    df = max(pitch_dia - 2 * dedendum, 2.0)
    
    root_cyl = cq.Workplane("XY").circle(df / 2.0).extrude(th)
    tooth_w = (math.pi * m) / 2.0
    tooth_h = addendum + dedendum
    
    teeth_solids = []
    for i in range(z):
        angle = 360.0 * i / z
        t = (cq.Workplane("XY")
             .transformed(rotate=(0, 0, angle))
             .workplane(offset=0)
             .center(0, pitch_dia / 2.0)
             .rect(tooth_w, tooth_h)
             .extrude(th)).val()
        teeth_solids.append(t)
        
    solid = _fuse(root_cyl, teeth_solids)
    if b > 0.5:
        solid = _cut(solid, [_cyl(b / 2.0, th + 2.0, 0, 0, -1.0, (0, 0, 1))])
    return solid


def gear_rack(module=0.91, teeth=70, base_height=5.0, width=15.0):
    m = _num(module, "module", 0.3, 10.0)
    z = _int(teeth, "teeth", 5, 200)
    bh = _num(base_height, "base_height", 2.0, 50.0)
    w = _num(width, "width", 2.0, 100.0)
    
    pitch = math.pi * m
    total_len = z * pitch
    addendum = 1.0 * m
    dedendum = 1.25 * m
    h_tooth = addendum + dedendum
    total_h = bh + h_tooth
    
    pts = [(0.0, 0.0), (total_len, 0.0), (total_len, bh)]
    half_top = (pitch / 4.0) * 0.7
    half_bot = (pitch / 4.0) * 1.3
    
    for i in range(z - 1, -1, -1):
        x_center = (i + 0.5) * pitch
        pts.extend([
            (x_center + half_bot, bh),
            (x_center + half_top, total_h),
            (x_center - half_top, total_h),
            (x_center - half_bot, bh)
        ])
    pts.append((0.0, bh))
    
    return cq.Workplane("XZ").polyline(pts).close().extrude(w)


def gt2_pulley(teeth=20, bore=5.0, width=7.0):
    z = _int(teeth, "teeth", 10, 80)
    b = _num(bore, "bore", 2.0, 20.0)
    w = _num(width, "width", 4.0, 30.0)
    pitch_dia = z * 2.0 / math.pi
    od = pitch_dia - 0.508
    body = cq.Workplane("XY").circle(od / 2.0).extrude(w)
    flange = cq.Workplane("XY").circle(od / 2.0 + 1.5).extrude(1.0).val()
    fused = _fuse(body, [flange])
    return _cut(fused, [_cyl(b / 2.0, w + 2.0, 0, 0, -1.0, (0, 0, 1))])


def l_bracket(length=40.0, width=40.0, height=40.0, thickness=4.0, hole_dia=5.0):
    l = _num(length, "length", 10.0, 200.0)
    w = _num(width, "width", 10.0, 200.0)
    h = _num(height, "height", 10.0, 200.0)
    t = _num(thickness, "thickness", 1.5, 20.0)
    hd = _num(hole_dia, "hole_dia", 1.0, 20.0)
    
    pts = [(0, 0), (l, 0), (l, t), (t, t), (t, h), (0, h)]
    body = cq.Workplane("XZ").polyline(pts).close().extrude(w)
    h1 = cq.Solid.makeCylinder(hd / 2.0, t + 2.0, V(l / 2.0, w / 2.0, -1.0), V(0, 0, 1))
    h2 = cq.Solid.makeCylinder(hd / 2.0, t + 2.0, V(-1.0, w / 2.0, h / 2.0), V(1, 0, 0))
    return _cut(body, [h1, h2])

# --------------------------------------------------------------------------- #
# 3. TEMPLATES REGISTRY & PARSER
# --------------------------------------------------------------------------- #

TEMPLATES = {
    "rs775_pump_housing": (rs775_pump_housing, {"chamber_dia": 52.0, "chamber_depth": 18.0, "wall": 3.0, "outlet_od": 12.0, "outlet_id": 8.0}),
    "rs775_pump_impeller": (rs775_pump_impeller, {"diameter": 46.0, "height": 14.0, "bore": 5.0, "vanes": 6, "base_t": 2.5}),
    "rs775_pump_cap": (rs775_pump_cap, {"outer_dia": 58.0, "thickness": 3.0, "inlet_od": 14.0, "inlet_id": 10.0, "inlet_len": 22.0}),
    "spur_gear": (spur_gear, {"module": 0.91, "teeth": 15, "thickness": 15.0, "bore": 5.0}),
    "gear_rack": (gear_rack, {"module": 0.91, "teeth": 70, "base_height": 5.0, "width": 15.0}),
    "gt2_pulley": (gt2_pulley, {"teeth": 20, "bore": 5.0, "width": 7.0}),
    "l_bracket": (l_bracket, {"length": 40.0, "width": 40.0, "height": 40.0, "thickness": 4.0, "hole_dia": 5.0})
}

CATALOG_FUNCS = {k: v[0] for k, v in TEMPLATES.items()}

def _grab(text, patterns, cast=float, default=None):
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return cast(m.group(1))
            except Exception:
                pass
    return default

def match_catalog_template(prompt):
    p = prompt.lower()
    
    # RS-775 Pump Suite matching
    if ("pump" in p or "water" in p) and ("impeller" in p or "vane" in p or "rotor" in p):
        d = dict(TEMPLATES["rs775_pump_impeller"][1])
        d["diameter"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*(?:dia|outer|od)"], float, d["diameter"])
        d["height"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*(?:height|tall|thick)"], float, d["height"])
        d["bore"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*(?:bore|shaft)"], float, d["bore"])
        return "rs775_pump_impeller", d

    if ("pump" in p or "water" in p) and ("cap" in p or "cover" in p or "suction" in p or "lid" in p):
        d = dict(TEMPLATES["rs775_pump_cap"][1])
        d["outer_dia"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*(?:dia|outer|od)"], float, d["outer_dia"])
        d["thickness"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*(?:thick|thickness)"], float, d["thickness"])
        d["inlet_od"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*od\s*inlet"], float, d["inlet_od"])
        return "rs775_pump_cap", d

    if "pump" in p or ("motor" in p and ("housing" in p or "casing" in p)):
        d = dict(TEMPLATES["rs775_pump_housing"][1])
        d["chamber_dia"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*(?:chamber|inner\s*dia|id)"], float, d["chamber_dia"])
        d["chamber_depth"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*(?:depth|chamber\s*depth)"], float, d["chamber_depth"])
        return "rs775_pump_housing", d

    # Mechanical standard parts matching
    if "rack" in p:
        d = dict(TEMPLATES["gear_rack"][1])
        d["teeth"] = _grab(p, [r"(\d+)\s*(?:teeth|t\b)"], int, d["teeth"])
        d["module"] = _grab(p, [r"module\s*(\d+(?:\.\d+)?)", r"m\s*=\s*(\d+(?:\.\d+)?)"], float, d["module"])
        d["width"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*width"], float, d["width"])
        return "gear_rack", d

    if "spur" in p or "pinion" in p or "gear" in p:
        d = dict(TEMPLATES["spur_gear"][1])
        d["teeth"] = _grab(p, [r"(\d+)\s*(?:teeth|t\b)"], int, d["teeth"])
        d["module"] = _grab(p, [r"module\s*(\d+(?:\.\d+)?)"], float, d["module"])
        d["thickness"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*(?:face|thick|height)"], float, d["thickness"])
        d["bore"] = _grab(p, [r"(\d+(?:\.\d+)?)\s*mm\s*bore"], float, d["bore"])
        return "spur_gear", d

    if "pulley" in p:
        return "gt2_pulley", dict(TEMPLATES["gt2_pulley"][1])

    if "bracket" in p or "l-bracket" in p:
        return "l-bracket", dict(TEMPLATES["l_bracket"][1])

    return None

def render_script(name, params):
    lines = ["params = {"]
    for k, v in params.items():
        lines.append(f'    "{k}": {v!r},')
    lines.append("}")
    args = ", ".join(f'{k}=params["{k}"]' for k in params.keys())
    lines.append(f"result = catalog.{name}({args})")
    return "\n".join(lines) + "\n"

def build_system_prompt():
    return "You are nutbolt.ai mechanical CAD agent."
