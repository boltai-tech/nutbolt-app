"""
catalog_templates.py - parametric hardware + prompt router + few-shot corpus.
"""
import math
import re
import cadquery as cq

from cad_builder import BuilderError, MechanicalBuilder, _clean, _cut, _cyl, _fuse, _num, _int, _wp, V

mb = MechanicalBuilder()

def involute_gear_points(module, teeth, pressure_angle=20.0):
    z = int(teeth)
    m = float(module)
    a = math.radians(pressure_angle)
    rp = m * z / 2.0
    rb = rp * math.cos(a)
    ra = rp + m
    rf = max(rp - 1.25 * m, 0.3 * rp)

    def t_at(r):
        return math.sqrt(max((r / rb) ** 2 - 1.0, 0.0))

    def phi(t):
        return t - math.atan(t)

    t_p, t_a = t_at(rp), t_at(ra)
    t0 = t_at(rf) if rf > rb else 0.0
    half = math.pi / (2.0 * z)
    samples = [t0 + (t_a - t0) * k / 6.0 for k in range(7)]

    def theta_right(t):
        return -half + (phi(t) - phi(t_p))

    pts = []
    for i in range(z):
        c = 2.0 * math.pi * i / z
        tooth = []
        if rf < rb:
            tooth.append((rf, c + theta_right(0.0)))
        for t in samples:
            tooth.append((rb * math.sqrt(1 + t * t), c + theta_right(t)))
        tooth.append((ra, c))
        for t in reversed(samples):
            tooth.append((rb * math.sqrt(1 + t * t), c - theta_right(t)))
        if rf < rb:
            tooth.append((rf, c - theta_right(0.0)))
        pts += tooth
        left_root = c - theta_right(0.0 if rf < rb else t0)
        nxt_root = c + 2.0 * math.pi / z + theta_right(0.0 if rf < rb else t0)
        pts.append((rf, (left_root + nxt_root) / 2.0))
    return [(r * math.cos(th), r * math.sin(th)) for r, th in pts]

def gt2_tooth_points(teeth, od):
    n = int(teeth)
    ro = od / 2.0
    gd, gw = 0.75, 0.6
    ga = min(gw / ro, math.pi / n * 0.8)
    ts = (-1.0, -0.8, -0.5, 0.0, 0.5, 0.8, 1.0)
    pts = []
    for i in range(n):
        c = 2.0 * math.pi * i / n
        for t in ts:
            r = ro - gd * math.sqrt(max(1.0 - t * t, 0.0))
            th = c + t * ga
            pts.append((r * math.cos(th), r * math.sin(th)))
    return pts

def heatsink_profile(base_w, base_t, fin_h, fins, fin_t):
    n = max(2, int(fins))
    pitch = (base_w - fin_t) / (n - 1)
    if pitch <= fin_t + 0.5:
        n = max(2, int((base_w - fin_t) // (fin_t + 1.0)) + 1)
        pitch = (base_w - fin_t) / (n - 1)
    pts = [(-base_w / 2.0, 0.0), (base_w / 2.0, 0.0)]
    top = base_t + fin_h
    for i in reversed(range(n)):
        xc = -base_w / 2.0 + fin_t / 2.0 + i * pitch
        xr, xl = xc + fin_t / 2.0, xc - fin_t / 2.0
        pts += [(xr, top)] if i == n - 1 else [(xr, base_t), (xr, top)]
        pts.append((xl, top))
        if i > 0:
            pts.append((xl, base_t))
    return pts

def pillow_profile(length, base_t, radius, zc):
    pts = [(-length / 2.0, 0.0), (length / 2.0, 0.0), (length / 2.0, base_t), (radius, base_t), (radius, zc)]
    steps = 24
    for k in range(1, steps + 1):
        ang = math.pi * k / steps
        pts.append((radius * math.cos(ang), zc + radius * math.sin(ang)))
    pts += [(-radius, base_t), (-length / 2.0, base_t)]
    return pts

_T_SLOT = [(-3.1, 11.0), (3.1, 11.0), (3.1, 8.2), (4.4, 8.2), (4.4, 4.6), (-4.4, 4.6), (-4.4, 8.2), (-3.1, 8.2)]

def tslot_cutter_points(side, cx, cy):
    out = []
    for (x, y) in _T_SLOT:
        for _ in range(side):
            x, y = -y, x
        out.append((x + cx, y + cy))
    return out

# --- CATALOG IMPLEMENTATIONS ---

def gear_rack(module=0.91, teeth=70, base_height=5.0, face_width=15.0, pressure_angle=20.0):
    m = _num(module, "module", 0.2, 20.0)
    n = _int(teeth, "teeth", 4, 100)
    hb = _num(base_height, "base_height", 1.0, 200.0)
    w = _num(face_width, "face_width", 1.0, 500.0)
    a = math.radians(pressure_angle)

    p = math.pi * m
    ha = m
    hf = 1.25 * m
    tp = p / 2.0
    w_tip = max(0.08, tp / 2.0 - ha * math.tan(a))
    w_root = min(p / 2.0 - 0.05, tp / 2.0 + hf * math.tan(a))

    L = n * p
    pts = [(0.0, 0.0), (L, 0.0), (L, hb)]
    for i in reversed(range(n)):
        xc = (i + 0.5) * p
        pts.append((xc + w_root, hb))
        pts.append((xc + w_tip, hb + hf + ha))
        pts.append((xc - w_tip, hb + hf + ha))
        pts.append((xc - w_root, hb))
    pts.append((0.0, hb))

    return cq.Workplane("XY").polyline(pts).close().extrude(w)

def tslot_extrusion(profile_w=20.0, profile_h=20.0, length=500.0):
    nx = _int(round(_num(profile_w, "profile_w", 20, 80) / 20.0), "nx", 1, 4)
    ny = _int(round(_num(profile_h, "profile_h", 20, 80) / 20.0), "ny", 1, 4)
    L = _num(length, "length", 10.0, 3000.0)
    body = cq.Workplane("XY").box(nx * 20.0, ny * 20.0, L, centered=(True, True, False))
    tools = []
    for ix in range(nx):
        for iy in range(ny):
            cx, cy = (ix - (nx - 1) / 2.0) * 20.0, (iy - (ny - 1) / 2.0) * 20.0
            tools.append(_cyl(2.1, L + 2.0, cx, cy, -1.0, (0, 0, 1)))
            outward = {0: iy == ny - 1, 1: ix == 0, 2: iy == 0, 3: ix == nx - 1}
            for side, on_edge in outward.items():
                if on_edge:
                    tools.append(
                        cq.Workplane("XY").workplane(offset=-1.0)
                        .polyline(tslot_cutter_points(side, cx, cy)).close().extrude(L + 2.0).val()
                    )
    return _cut(body, tools)

def gt2_pulley(teeth=20, bore=5.0, belt_width=6.0, hub_height=7.0):
    n = _int(teeth, "teeth", 12, 80)
    pd = n * 2.0 / math.pi
    od = pd - 0.254
    bw = _num(belt_width, "belt_width", 3.0, 20.0)
    bore = _num(bore, "bore", 1.0, od - 3.0)
    fl_d = od + 2.4
    hub_d = min(bore + 6.0, od * 0.9)
    hub_h = _num(hub_height, "hub_height", 0.0, 30.0)
    ft = 1.0
    teeth_prism = (cq.Workplane("XY").workplane(offset=ft / 2.0)
                   .polyline(gt2_tooth_points(n, od)).close().extrude(bw + ft)).val()
    flange_lo = cq.Solid.makeCylinder(fl_d / 2.0, ft, V(0, 0, 0), V(0, 0, 1))
    flange_hi = cq.Solid.makeCylinder(fl_d / 2.0, ft, V(0, 0, ft + bw), V(0, 0, 1))
    parts = [flange_lo, flange_hi]
    if hub_h > 0.5:
        parts.append(cq.Solid.makeCylinder(hub_d / 2.0, hub_h + 0.5, V(0, 0, 2 * ft + bw - 0.5), V(0, 0, 1)))
    body = _fuse(_wp(teeth_prism), parts)
    return _cut(body, [_cyl(bore / 2.0, 2 * ft + bw + hub_h + 2.0, 0, 0, -1.0, (0, 0, 1))])

def spur_gear(module=0.91, teeth=15, thickness=15.0, bore=5.0):
    m = _num(module, "module", 0.2, 12.0)
    n = _int(teeth, "teeth", 10, 120)
    t = _num(thickness, "thickness", 1.0, 200.0)
    root_d = (m * n - 2.5 * m)
    bore = _num(bore, "bore", 0.0, max(root_d - 4.0, 1.0))
    body = cq.Workplane("XY").polyline(involute_gear_points(m, n)).close().extrude(t)
    if bore > 0.5:
        return _cut(body, [_cyl(bore / 2.0, t + 2.0, 0, 0, -1.0, (0, 0, 1))])
    return body

_NEMA = {
    14: dict(face=35.2, pilot=22.0, spacing=26.0, hole=3.0, plate=4.0),
    17: dict(face=42.3, pilot=22.0, spacing=31.0, hole=3.4, plate=5.0),
    23: dict(face=56.4, pilot=38.1, spacing=47.14, hole=5.1, plate=6.0),
}

def nema_mount(frame=17, thickness=5.0, corner_radius=3.0):
    spec = _NEMA.get(int(frame), _NEMA[17])
    return mb.prismatic_plate(
        length=spec["face"], width=spec["face"], thickness=thickness,
        center_bore=spec["pilot"] + 0.5,
        bolt_pattern={"type": "rect", "dx": spec["spacing"], "dy": spec["spacing"], "dia": spec["hole"]},
        corner_radius=corner_radius,
    )

def pillow_block_608(length=60.0, base_thickness=8.0, mount_hole=5.5):
    od, bw = 22.0, 7.0
    L = _num(length, "length", 50.0, 200.0)
    bt = _num(base_thickness, "base_thickness", 4.0, 30.0)
    R = od / 2.0 + 6.0
    zc = bt + 8.0
    W = bw + 8.0
    body = cq.Workplane("XZ").polyline(pillow_profile(L, bt, R, zc)).close().extrude(W / 2.0, both=True)
    tools = [
        _cyl(od / 2.0 + 0.05, bw, 0, -bw / 2.0, zc, (0, 1, 0)),
        _cyl((od - 4.0) / 2.0, W + 2.0, 0, -W / 2.0 - 1.0, zc, (0, 1, 0)),
    ]
    hx = L / 2.0 - 6.5
    for sx in (-1, 1):
        tools.append(_cyl(_num(mount_hole, "mount_hole", 2.0, 12.0) / 2.0, bt + 2.0, sx * hx, 0, -1.0, (0, 0, 1)))
    return _cut(body, tools)

_DN = {
    15: (95, 65, 4, 14, 16, 21.3), 20: (105, 75, 4, 14, 18, 26.9), 25: (115, 85, 4, 14, 18, 33.7),
    32: (140, 100, 4, 19, 18, 42.4), 40: (150, 110, 4, 19, 18, 48.3), 50: (165, 125, 4, 19, 20, 60.3),
    65: (185, 145, 4, 19, 20, 76.1), 80: (200, 160, 8, 19, 20, 88.9), 100: (220, 180, 8, 19, 20, 114.3),
}

def pipe_flange(dn=50, neck_height=15.0):
    key = min(_DN, key=lambda k: abs(k - int(dn)))
    od, pcd, n, hole, t, pipe = _DN[key]
    return mb.turned_concentric(
        steps=[{"d": od, "h": t}, {"d": pipe + 16.0, "h": _num(neck_height, "neck_height", 5.0, 60.0)}],
        bore=pipe,
        bolt_circle={"count": n, "pcd": pcd, "dia": hole},
    )

def heatsink(base_w=60.0, base_t=4.0, fin_h=25.0, fins=10, fin_t=2.0, length=40.0):
    bw = _num(base_w, "base_w", 10.0, 400.0)
    bt = _num(base_t, "base_t", 1.0, 30.0)
    fh = _num(fin_h, "fin_h", 3.0, 150.0)
    ft = _num(fin_t, "fin_t", 0.6, 10.0)
    n = _int(fins, "fins", 2, 40)
    L = _num(length, "length", 5.0, 400.0)
    return cq.Workplane("XZ").polyline(heatsink_profile(bw, bt, fh, n, ft)).close().extrude(L / 2.0, both=True)


# --- RS-775 50L/MIN CENTRIFUGAL WATER PUMP SUITE ---

def rs775_pump_housing(chamber_dia=52.0, chamber_depth=18.0, wall=3.0, outlet_od=12.0, outlet_id=8.0):
    cd = _num(chamber_dia, "chamber_dia", 30.0, 100.0)
    ch = _num(chamber_depth, "chamber_depth", 10.0, 50.0)
    w = _num(wall, "wall", 2.0, 8.0)
    ood = _num(outlet_od, "outlet_od", 6.0, 25.0)
    oid = min(_num(outlet_id, "outlet_id", 3.0, ood - 2.0), ood - 1.5)
    
    # Outer body and chamber cavity
    od = cd + 2 * w
    base_t = 4.0
    total_h = ch + base_t
    outer = cq.Workplane("XY").cylinder(total_h, od / 2.0, centered=(True, True, False))
    cavity = cq.Solid.makeCylinder(cd / 2.0, ch + 2.0, V(0, 0, base_t), V(0, 0, 1))
    
    # RS-775 motor pilot boss (17.5mm), shaft bore (7mm), and 2x M4 motor mount holes (29mm PCD)
    boss_hole = cq.Solid.makeCylinder(17.8 / 2.0, base_t + 2.0, V(0, 0, -1.0), V(0, 0, 1))
    shaft_seal = cq.Solid.makeCylinder(9.0 / 2.0, base_t + 2.0, V(0, 0, -1.0), V(0, 0, 1))
    
    m_holes = [
        cq.Solid.makeCylinder(4.4 / 2.0, base_t + 2.0, V(14.5, 0, -1.0), V(0, 0, 1)),
        cq.Solid.makeCylinder(4.4 / 2.0, base_t + 2.0, V(-14.5, 0, -1.0), V(0, 0, 1))
    ]
    
    # 4x M3 perimeter mounting holes for the front cover
    flange_holes = []
    pcd = od - 3.5
    for ang in (45, 135, 225, 315):
        rad = math.radians(ang)
        x = (pcd / 2.0) * math.cos(rad)
        y = (pcd / 2.0) * math.sin(rad)
        flange_holes.append(cq.Solid.makeCylinder(3.2 / 2.0, total_h + 2.0, V(x, y, -1.0), V(0, 0, 1)))

    # Tangential discharge outlet pipe
    pipe_len = 22.0
    tangent_y = cd / 2.0 - ood / 2.0 + 1.0
    pipe_outer = cq.Solid.makeCylinder(ood / 2.0, pipe_len + od / 2.0, V(0, tangent_y, base_t + ch / 2.0), V(1, 0, 0))
    pipe_bore = cq.Solid.makeCylinder(oid / 2.0, pipe_len + od + 4.0, V(-2.0, tangent_y, base_t + ch / 2.0), V(1, 0, 0))

    body = _fuse(outer, [pipe_outer])
    tools = [cavity, boss_hole, shaft_seal, pipe_bore] + m_holes + flange_holes
    return _cut(body, tools)


def rs775_pump_impeller(diameter=46.0, height=14.0, bore=5.0, vanes=6, base_t=2.5):
    d = _num(diameter, "diameter", 20.0, 95.0)
    h = _num(height, "height", 6.0, 40.0)
    b = _num(bore, "bore", 2.0, 12.0)
    n = _int(vanes, "vanes", 3, 12)
    bt = _num(base_t, "base_t", 1.5, 6.0)
    
    # Base disk and central drive hub
    base_plate = cq.Workplane("XY").cylinder(bt, d / 2.0, centered=(True, True, False))
    hub_d = max(b + 5.0, 11.0)
    hub = cq.Solid.makeCylinder(hub_d / 2.0, h, V(0, 0, 0), V(0, 0, 1))
    
    # Curved impeller vanes
    v_thickness = 2.0
    blade_h = h - bt
    v_parts = []
    r_inner = hub_d / 2.0 + 0.5
    r_outer = d / 2.0 - 0.5
    
    for i in range(n):
        ang = 2.0 * math.pi * i / n
        pts = []
        steps = 10
        for s in range(steps + 1):
            t = s / float(steps)
            curr_r = r_inner + (r_outer - r_inner) * t
            curve_ang = ang + (0.55 * t * t)
            pts.append((curr_r * math.cos(curve_ang), curr_r * math.sin(curve_ang)))
        for s in reversed(range(steps + 1)):
            t = s / float(steps)
            curr_r = r_inner + (r_outer - r_inner) * t
            curve_ang = ang + (0.55 * t * t) + (v_thickness / curr_r)
            pts.append((curr_r * math.cos(curve_ang), curr_r * math.sin(curve_ang)))
            
        blade = (cq.Workplane("XY").workplane(offset=bt)
                 .polyline(pts).close().extrude(blade_h)).val()
        v_parts.append(blade)
        
    solid = _fuse(base_plate, [hub] + v_parts)
    # Shaft bore hole
    return _cut(solid, [_cyl(b / 2.0, h + 4.0, 0, 0, -2.0, (0, 0, 1))])


def rs775_pump_cap(outer_dia=58.0, thickness=3.0, inlet_od=14.0, inlet_id=10.0, inlet_len=22.0):
    od = _num(outer_dia, "outer_dia", 35.0, 110.0)
    t = _num(thickness, "thickness", 2.0, 8.0)
    iod = _num(inlet_od, "inlet_od", 6.0, 30.0)
    iid = min(_num(inlet_id, "inlet_id", 3.0, iod - 2.0), iod - 1.5)
    L = _num(inlet_len, "inlet_len", 8.0, 50.0)
    
    cap_disk = cq.Workplane("XY").cylinder(t, od / 2.0, centered=(True, True, False))
    pipe = cq.Solid.makeCylinder(iod / 2.0, L, V(0, 0, t), V(0, 0, 1))
    pipe_bore = cq.Solid.makeCylinder(iid / 2.0, L + t + 2.0, V(0, 0, -1.0), V(0, 0, 1))
    
    flange_holes = []
    pcd = od - 5.5
    for ang in (45, 135, 225, 315):
        rad = math.radians(ang)
        x = (pcd / 2.0) * math.cos(rad)
        y = (pcd / 2.0) * math.sin(rad)
        flange_holes.append(cq.Solid.makeCylinder(3.2 / 2.0, t + 2.0, V(x, y, -1.0), V(0, 0, 1)))
        
    body = _fuse(cap_disk, [pipe])
    return _cut(body, [pipe_bore] + flange_holes)
TEMPLATES = {
    "rs775_pump_housing": (rs775_pump_housing, {"chamber_dia": 52.0, "chamber_depth": 18.0, "wall": 3.0, "outlet_od": 12.0, "outlet_id": 8.0}),
    "rs775_pump_impeller": (rs775_pump_impeller, {"diameter": 46.0, "height": 14.0, "bore": 5.0, "vanes": 6, "base_t": 2.5}),
    "rs775_pump_cap": (rs775_pump_cap, {"outer_dia": 58.0, "thickness": 3.0, "inlet_od": 14.0, "inlet_id": 10.0, "inlet_len": 22.0}),
    "gear_rack": (gear_rack, {"module": 0.91, "teeth": 70, "base_height": 5.0, "face_width": 15.0}),
    "spur_gear": (spur_gear, {"module": 0.91, "teeth": 15, "thickness": 15.0, "bore": 5.0}),
    "tslot_extrusion": (tslot_extrusion, {"profile_w": 20.0, "profile_h": 20.0, "length": 500.0}),
    "gt2_pulley": (gt2_pulley, {"teeth": 20, "bore": 5.0, "belt_width": 6.0, "hub_height": 7.0}),
    "nema_mount": (nema_mount, {"frame": 17, "thickness": 5.0, "corner_radius": 3.0}),
    "pillow_block_608": (pillow_block_608, {"length": 60.0, "base_thickness": 8.0, "mount_hole": 5.5}),
    "pipe_flange": (pipe_flange, {"dn": 50, "neck_height": 15.0}),
    "heatsink": (heatsink, {"base_w": 60.0, "base_t": 4.0, "fin_h": 25.0, "fins": 10, "fin_t": 2.0, "length": 40.0}),
}
CATALOG_FUNCS = {name: fn for name, (fn, _) in TEMPLATES.items()}

_NUM = r"(\d+(?:\.\d+)?)"
_CUSTOM_WORDS = ("chamfer", "countersink", "extra hole", "additional")

def _grab(p, pats, cast=float, default=None):
    for pat in pats:
        m = re.search(pat, p)
        if m:
            try:
                return cast(m.group(1))
            except (TypeError, ValueError):
                continue
    return default

def _mm(p, default):
    v = _grab(p, [_NUM + r"\s*mm\b"], float)
    if v is None:
        c = _grab(p, [_NUM + r"\s*cm\b"], float)
        v = c * 10.0 if c is not None else None
    if v is None:
        m = _grab(p, [_NUM + r"\s*m\b"], float)
        v = m * 1000.0 if m is not None else default
    return v

def match_catalog_template(prompt):
    p = prompt.lower()
    if len(p) > 260 or any(w in p for w in _CUSTOM_WORDS):
        return None

    bore = _grab(p, [_NUM + r"\s*mm\s*(?:bore|shaft|hole)", r"bore\s*(?:dia(?:meter)?)?\s*(?:of|=|:)?\s*" + _NUM], float)

    # 1. Gear Rack
    if "rack" in p:
        d = dict(TEMPLATES["gear_rack"][1])
        d["teeth"] = _grab(p, [r"(\d+)\s*[- ]?(?:teeth|tooth)", r"(\d+)\s*t\b", r"teeth\s*[:=]?\s*(\d+)"], int, d["teeth"])
        d["module"] = _grab(p, [r"module\s*[:=]?\s*" + _NUM, r"\bm\s*=\s*" + _NUM], float, d["module"])
        d["base_height"] = _grab(p, [r"base\s*(?:height)?\s*[:=]?\s*" + _NUM, r"(\d+(?:\.\d+)?)\s*mm\s*(?:base|height)"], float, d["base_height"])
        d["face_width"] = _grab(p, [r"(?:width|face|thickness)\s*[:=]?\s*" + _NUM, r"(\d+(?:\.\d+)?)\s*mm\s*(?:wide|width|face|thickness)"], float, d["face_width"])
        return "gear_rack", d

    # 2. Spur Gear
    if "gear" in p and "rack" not in p and "gearbox" not in p and "gear box" not in p:
        d = dict(TEMPLATES["spur_gear"][1])
        d["module"] = _grab(p, [r"module\s*[:=]?\s*" + _NUM, r"\bm\s*=\s*" + _NUM], float, d["module"])
        d["teeth"] = _grab(p, [r"(\d+)\s*[- ]?(?:teeth|tooth)", r"(\d+)\s*t\b", r"teeth\s*[:=]?\s*(\d+)"], int, d["teeth"])
        d["thickness"] = _grab(p, [_NUM + r"\s*mm\s*(?:thick|thickness|wide|face|height)", r"(?:thickness|height)\s*[:=]?\s*" + _NUM], float, d["thickness"])
        d["bore"] = bore if bore is not None else d["bore"]
        return "spur_gear", d

    # 3. GT2 Pulley
    if "pulley" in p and ("gt2" in p or "timing" in p or "teeth" in p or "tooth" in p):
        d = dict(TEMPLATES["gt2_pulley"][1])
        d["teeth"] = _grab(p, [r"(\d+)\s*[- ]?(?:teeth|tooth)", r"(\d+)\s*t\b", r"teeth\s*[:=]?\s*(\d+)"], int, d["teeth"])
        d["bore"] = bore or d["bore"]
        d["belt_width"] = _grab(p, [_NUM + r"\s*mm\s*(?:belt|wide|width)", r"belt\s*(?:width)?\s*" + _NUM], float, d["belt_width"])
        return "gt2_pulley", d

    # 4. NEMA Mount
    if "nema" in p:
        d = dict(TEMPLATES["nema_mount"][1])
        d["frame"] = _grab(p, [r"nema\s*-?\s*(14|17|23)"], int, 17)
        d["thickness"] = _grab(p, [_NUM + r"\s*mm\s*(?:thick|thickness|plate)", r"thickness\s*[:=]?\s*" + _NUM], float, d["thickness"])
        return "nema_mount", d

    # 5. Pillow Block
    if "pillow" in p or "608" in p:
        return "pillow_block_608", dict(TEMPLATES["pillow_block_608"][1])

    # 6. T-Slot
    if any(k in p for k in ("t-slot", "t slot", "tslot", "v-slot", "vslot", "aluminium extrusion", "aluminum extrusion")) or re.search(r"\b(20|40)(20|40)\b", p):
        d = dict(TEMPLATES["tslot_extrusion"][1])
        m = re.search(r"\b(20|40)(20|40)\b", p)
        if m:
            d["profile_w"], d["profile_h"] = float(m.group(1)), float(m.group(2))
        d["length"] = _mm(p, d["length"])
        return "tslot_extrusion", d

    # 7. Flange
    if "flange" in p and ("pipe" in p or re.search(r"\bdn\s*-?\s*\d+", p) or "pn16" in p or "pn10" in p or "weld neck" in p):
        d = dict(TEMPLATES["pipe_flange"][1])
        d["dn"] = _grab(p, [r"dn\s*-?\s*(\d+)"], int, d["dn"])
        return "pipe_flange", d

    # 8. Heatsink
    if "heatsink" in p or "heat sink" in p:
        d = dict(TEMPLATES["heatsink"][1])
        d["fins"] = _grab(p, [r"(\d+)\s*fins?"], int, d["fins"])
        d["fin_h"] = _grab(p, [_NUM + r"\s*mm\s*(?:tall|high|fin)", r"fin\s*height\s*[:=]?\s*" + _NUM], float, d["fin_h"])
        m = re.search(_NUM + r"\s*[x×]\s*" + _NUM, p)
        if m:
            d["base_w"], d["length"] = float(m.group(1)), float(m.group(2))
        return "heatsink", d

    return None

def render_script(name, params):
    defaults = TEMPLATES[name][1]
    merged = {}
    for k, dv in defaults.items():
        v = params.get(k, dv)
        merged[k] = int(v) if isinstance(dv, int) and not isinstance(dv, bool) else float(v)
    lines = ["params = {"] + [f'    "{k}": {v!r},' for k, v in merged.items()] + ["}"]
    call = ", ".join(f'{k}=params["{k}"]' for k in merged)
    lines.append(f"result = catalog.{name}({call})")
    return "\n".join(lines) + "\n"

API_SPEC = '''API (already in scope, do NOT import anything):
catalog.gear_rack(module=0.91, teeth=14, base_height=5.0, face_width=15.0)
catalog.spur_gear(module=0.91, teeth=15, thickness=15.0, bore=5.0)
catalog.gt2_pulley(teeth=20, bore=5.0, belt_width=6.0, hub_height=7.0)
catalog.tslot_extrusion(profile_w=20.0, profile_h=20.0, length=500.0)
mb.turned_concentric(...)
mb.profile_extruded(...)
mb.prismatic_plate(...)
mb.shell_enclosure(...)
mb.manifold_block(...)'''

def build_system_prompt():
    return (
        "You write nutbolt.ai part scripts. Output ONLY the script: no markdown fences, no prose, no comments.\n"
        "Rules: first statement `params = {...}`. Last statement `result = catalog.<name>(...)` or `result = mb.<archetype>(...)`.\n\n"
        + API_SPEC
    )


