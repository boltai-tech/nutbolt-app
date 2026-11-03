"""
cad_builder.py - manifold-safe archetype builder for nutbolt.ai

Design rules:
  * Turned parts are ONE revolve of ONE closed profile (no stacked unions on touching faces).
  * Prismatic parts are ONE extrusion of ONE closed profile / box.
  * Every subtractive feature is a tool that sticks out >= 1 mm past the faces it cuts.
  * Any additive feature overlaps the base volume, never just touches it.
"""
import math
import cadquery as cq

V = cq.Vector

MAX_DIM = 2000.0
MAX_POINTS = 400
MAX_PATTERN = 48
MAX_LIST = 12

ARCHETYPES = (
    "turned_concentric",
    "profile_extruded",
    "prismatic_plate",
    "shell_enclosure",
    "manifold_block",
)

class BuilderError(ValueError):
    """Readable construction error (also fed back to the LLM during self-healing)."""

def _num(v, name, lo, hi):
    try:
        x = float(v)
    except Exception:
        raise BuilderError(f"{name} must be a number, got {v!r}")
    if not math.isfinite(x):
        raise BuilderError(f"{name} must be finite")
    return min(max(x, lo), hi)

def _int(v, name, lo, hi):
    return int(round(_num(v, name, lo, hi)))

def _clean(shape):
    try:
        return shape.clean()
    except Exception:
        return shape

def _wp(shape):
    return cq.Workplane("XY").newObject([shape])

def _shape(body):
    return body.val() if isinstance(body, cq.Workplane) else body

def _cut(body, tools):
    tools = [t for t in tools if t is not None]
    if not tools:
        return body if isinstance(body, cq.Workplane) else _wp(body)
    try:
        out = _shape(body).cut(*tools)
    except Exception as e:
        raise BuilderError(f"boolean cut failed ({type(e).__name__}: {e})")
    return _wp(_clean(out))

def _fuse(body, parts):
    parts = [p for p in parts if p is not None]
    if not parts:
        return body
    try:
        out = _shape(body).fuse(*parts)
    except Exception as e:
        raise BuilderError(f"boolean union failed ({type(e).__name__}: {e})")
    return _wp(_clean(out))

def _cyl(r, length, x, y, z, d):
    return cq.Solid.makeCylinder(r, length, V(x, y, z), V(*d))

def _dedupe(pts):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9:
            out.append((float(p[0]), float(p[1])))
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    return out

def _axis_of(h, default="Z"):
    face = h.get("face")
    if face:
        face = str(face).strip()
        if len(face) != 2 or face[0] not in "<>" or face[1].upper() not in "XYZ":
            raise BuilderError(f"face must be one of >X <X >Y <Y >Z <Z, got {face!r}")
        return face[1].upper(), ("+" if face[0] == ">" else "-"), h.get("depth")
    axis = str(h.get("axis", default)).upper()
    if axis not in ("X", "Y", "Z"):
        raise BuilderError(f"axis must be X, Y or Z, got {axis!r}")
    return axis, str(h.get("side", "+")), h.get("depth")

def _ab(h, axis):
    if "a" in h or "b" in h:
        return _num(h.get("a", 0.0), "a", -MAX_DIM, MAX_DIM), _num(h.get("b", 0.0), "b", -MAX_DIM, MAX_DIM)
    g = lambda k: _num(h.get(k, 0.0), k, -MAX_DIM, MAX_DIM)
    return {"Z": (g("x"), g("y")), "X": (g("y"), g("z")), "Y": (g("x"), g("z"))}[axis]

def _hole_tool(bb, axis, a, b, dia, side="+", depth=None):
    r = max(dia, 0.1) / 2.0
    if axis == "Z":
        lo, hi, org, d = bb.zmin, bb.zmax, (lambda t: (a, b, t)), (0, 0, 1)
    elif axis == "X":
        lo, hi, org, d = bb.xmin, bb.xmax, (lambda t: (t, a, b)), (1, 0, 0)
    else:
        lo, hi, org, d = bb.ymin, bb.ymax, (lambda t: (a, t, b)), (0, 1, 0)
    span = hi - lo
    if depth is None:
        start, length = lo - 1.0, span + 2.0
    else:
        dep = _num(depth, "depth", 0.1, span)
        if side == "+":
            start, length = hi - dep, dep + 1.0
        else:
            start, length = lo - 1.0, dep + 1.0
    return _cyl(r, length, *org(start), d)

def _slot_tool(bb, axis, a, b, length, width, angle):
    width = max(width, 0.2)
    length = max(length, width + 0.01)
    if axis == "Z":
        pl, span = cq.Plane(origin=(0, 0, bb.zmin - 1.0), xDir=(1, 0, 0), normal=(0, 0, 1)), bb.zlen
    elif axis == "X":
        pl, span = cq.Plane(origin=(bb.xmin - 1.0, 0, 0), xDir=(0, 1, 0), normal=(1, 0, 0)), bb.xlen
    else:
        pl, span = cq.Plane(origin=(0, bb.ymax + 1.0, 0), xDir=(1, 0, 0), normal=(0, -1, 0)), bb.ylen
    return cq.Workplane(pl).center(a, b).slot2D(length, width, angle).extrude(span + 2.0).val()

def _pattern_points(bp):
    if not isinstance(bp, dict) or not bp:
        return [], 0.0, 0.0, 0.0
    kind = str(bp.get("type", "pcd")).lower()
    dia = _num(bp.get("dia", 5.0), "bolt dia", 0.2, MAX_DIM)
    cb_d = _num(bp.get("cbore_dia", 0.0), "cbore_dia", 0.0, MAX_DIM)
    cb_h = _num(bp.get("cbore_depth", 0.0), "cbore_depth", 0.0, MAX_DIM)
    pts = []
    if kind == "pcd":
        n = _int(bp.get("count", 4), "count", 1, MAX_PATTERN)
        r = _num(bp.get("pcd", 40.0), "pcd", 1.0, MAX_DIM) / 2.0
        a0 = math.radians(_num(bp.get("start_angle", 0.0), "start_angle", -360.0, 360.0))
        pts = [(r * math.cos(a0 + 2 * math.pi * i / n), r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n)]
    elif kind in ("grid", "rect"):
        nx = _int(bp.get("nx", 2), "nx", 1, 12)
        ny = _int(bp.get("ny", 2), "ny", 1, 12)
        dx = _num(bp.get("dx", 30.0), "dx", 0.1, MAX_DIM)
        dy = _num(bp.get("dy", dx), "dy", 0.1, MAX_DIM)
        pts = [((i - (nx - 1) / 2.0) * dx, (j - (ny - 1) / 2.0) * dy) for i in range(nx) for j in range(ny)]
    elif kind == "points":
        for p in list(bp.get("points", []))[:MAX_PATTERN]:
            pts.append((_num(p.get("x", 0.0), "x", -MAX_DIM, MAX_DIM), _num(p.get("y", 0.0), "y", -MAX_DIM, MAX_DIM)))
    else:
        raise BuilderError(f"bolt_pattern type must be pcd, grid, rect or points, got {kind!r}")
    return pts[:MAX_PATTERN], dia, cb_d, cb_h

class MechanicalBuilder:
    def turned_concentric(self, steps, bore=0.0, keyway=None, bolt_circle=None, radial_features=None):
        if not isinstance(steps, (list, tuple)) or not steps:
            raise BuilderError("turned_concentric needs a non-empty `steps` list")
        bore0 = _num(bore, "bore", 0.0, MAX_DIM)
        rows, z = [], 0.0
        for i, s in enumerate(list(steps)[:12]):
            if not isinstance(s, dict):
                raise BuilderError(f"steps[{i}] must be a dict with d and h")
            d = _num(s.get("d"), f"steps[{i}].d", 1.0, MAX_DIM)
            dt = _num(s.get("d_top", d), f"steps[{i}].d_top", 1.0, MAX_DIM)
            h = _num(s.get("h"), f"steps[{i}].h", 0.2, MAX_DIM)
            b = _num(s.get("bore", bore0), f"steps[{i}].bore", 0.0, MAX_DIM)
            b = min(b, min(d, dt) - 1.0)
            if b < 0.5:
                b = 0.0
            rows.append({"z0": z, "z1": z + h, "rb": d / 2.0, "rt": dt / 2.0, "rin": b / 2.0})
            z += h
        H = z

        outer, inner = [], []
        for r in rows:
            outer += [(r["rb"], r["z0"]), (r["rt"], r["z1"])]
        for r in reversed(rows):
            inner += [(r["rin"], r["z1"]), (r["rin"], r["z0"])]
        pts = _dedupe(outer + inner)
        try:
            body = cq.Workplane("XZ").polyline(pts).close().revolve(360.0, (0, 0, 0), (0, 1, 0))
        except Exception as e:
            raise BuilderError(f"revolve failed ({type(e).__name__}: {e})")

        tools = []
        rin_max = max(r["rin"] for r in rows)
        if keyway and rin_max > 0:
            w = _num(keyway.get("width", 4.0), "keyway.width", 0.5, rin_max * 2)
            dep = _num(keyway.get("depth", 2.0), "keyway.depth", 0.2, MAX_DIM)
            host = next(r for r in rows if r["rin"] == rin_max)
            dep = min(dep, (min(host["rb"], host["rt"]) - rin_max) * 0.6)
            if dep > 0.2:
                tools.append(cq.Solid.makeBox(rin_max + dep, w, H + 2.0, V(0, -w / 2.0, -1.0)))

        if bolt_circle:
            pts_b, dia, _, _ = _pattern_points({**bolt_circle, "type": "pcd"})
            rad = _num(bolt_circle.get("pcd", 40.0), "pcd", 1.0, MAX_DIM) / 2.0
            reach = [r for r in rows if max(r["rb"], r["rt"]) > rad - dia / 2.0]
            if reach:
                z_top = reach[-1]["z1"]
                for (x, y) in pts_b:
                    tools.append(_cyl(dia / 2.0, z_top + 2.0, x, y, -1.0, (0, 0, 1)))

        rf = radial_features or {}
        if rf:
            idx = _int(rf.get("step", 0), "radial_features.step", 0, len(rows) - 1)
            r = rows[idx]
            r_out = max(r["rb"], r["rt"])
            n = _int(rf.get("count", 12), "count", 2, MAX_PATTERN)
            depth = _num(rf.get("depth", 1.5), "depth", 0.1, r_out * 0.5)
            width = _num(rf.get("width", 3.0), "width", 0.2, 2 * math.pi * r_out / n * 0.8)
            below_smaller = idx == 0 or max(rows[idx - 1]["rb"], rows[idx - 1]["rt"]) < r_out
            above_smaller = idx == len(rows) - 1 or max(rows[idx + 1]["rb"], rows[idx + 1]["rt"]) < r_out
            z_lo = r["z0"] - (1.0 if below_smaller else 0.0)
            z_hi = r["z1"] + (1.0 if above_smaller else 0.0)
            kind = str(rf.get("type", "teeth")).lower()
            base = cq.Workplane("XY").workplane(offset=z_lo)
            if kind == "scallops":
                rc = r_out + width / 2.0 - depth
                tool = base.polarArray(rc, 0, 360, n).circle(width / 2.0).extrude(z_hi - z_lo).val()
            else:
                radial = depth + 2.0
                rc = r_out - depth + radial / 2.0
                tool = base.polarArray(rc, 0, 360, n).rect(radial, width).extrude(z_hi - z_lo).val()
            tools.append(tool)

        return _cut(body, tools)

    def profile_extruded(self, pts, length, workplane="XZ", holes=None, slots=None):
        plane = str(workplane).upper()
        if plane not in ("XY", "XZ", "YZ"):
            raise BuilderError("workplane must be XY, XZ or YZ")
        try:
            clean_pts = _dedupe([(float(p[0]), float(p[1])) for p in list(pts)[:MAX_POINTS]])
        except Exception:
            raise BuilderError("pts must be a list of (x, y) pairs")
        if len(clean_pts) < 3:
            raise BuilderError("pts needs at least 3 distinct points")
        L = _num(length, "length", 0.5, MAX_DIM)
        try:
            body = cq.Workplane(plane).polyline(clean_pts).close().extrude(L / 2.0, both=True)
        except Exception as e:
            raise BuilderError(f"profile extrude failed ({type(e).__name__}: {e})")

        bb = _shape(body).BoundingBox()
        tools = []
        for h in list(holes or [])[:24]:
            axis, side, depth = _axis_of(h)
            a, b = _ab(h, axis)
            tools.append(_hole_tool(bb, axis, a, b, _num(h.get("dia", 5.0), "hole dia", 0.2, MAX_DIM), side, depth))
        for s in list(slots or [])[:MAX_LIST]:
            axis, _, _ = _axis_of(s)
            a, b = _ab(s, axis)
            tools.append(_slot_tool(
                bb, axis, a, b,
                _num(s.get("length", 20.0), "slot length", 0.5, MAX_DIM),
                _num(s.get("width", 5.0), "slot width", 0.2, MAX_DIM),
                _num(s.get("angle", 0.0), "slot angle", -360.0, 360.0),
            ))
        return _cut(body, tools)

    def prismatic_plate(self, length, width, thickness, center_bore=0.0, bolt_pattern=None,
                        relief_slots=None, corner_radius=0.0):
        L = _num(length, "length", 1.0, MAX_DIM)
        W = _num(width, "width", 1.0, MAX_DIM)
        T = _num(thickness, "thickness", 0.3, MAX_DIM)
        body = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
        cr = min(_num(corner_radius, "corner_radius", 0.0, MAX_DIM), min(L, W) / 2.0 - 0.5)
        if cr > 0.05:
            try:
                body = body.edges("|Z").fillet(cr)
            except Exception as e:
                raise BuilderError(f"corner fillet failed ({type(e).__name__}: {e})")

        tools = []
        cb = _num(center_bore, "center_bore", 0.0, MAX_DIM)
        if cb > 0.1:
            cb = min(cb, min(L, W) - 2.0)
            tools.append(_cyl(cb / 2.0, T + 2.0, 0, 0, -1.0, (0, 0, 1)))

        pts, dia, cb_d, cb_h = _pattern_points(bolt_pattern)
        for (x, y) in pts:
            tools.append(_cyl(dia / 2.0, T + 2.0, x, y, -1.0, (0, 0, 1)))
            if cb_d > dia and cb_h > 0.1:
                depth = min(cb_h, T - 0.5)
                tools.append(_cyl(cb_d / 2.0, depth + 1.0, x, y, T - depth, (0, 0, 1)))

        bb = _shape(body).BoundingBox()
        for s in list(relief_slots or [])[:MAX_LIST]:
            tools.append(_slot_tool(
                bb, "Z",
                _num(s.get("x", 0.0), "slot x", -MAX_DIM, MAX_DIM),
                _num(s.get("y", 0.0), "slot y", -MAX_DIM, MAX_DIM),
                _num(s.get("length", 20.0), "slot length", 0.5, MAX_DIM),
                _num(s.get("width", 5.0), "slot width", 0.2, MAX_DIM),
                _num(s.get("angle", 0.0), "slot angle", -360.0, 360.0),
            ))
        return _cut(body, tools)

    def shell_enclosure(self, length, width, height, wall_thickness, bosses=None, cutouts=None):
        L = _num(length, "length", 10.0, MAX_DIM)
        W = _num(width, "width", 10.0, MAX_DIM)
        H = _num(height, "height", 5.0, MAX_DIM)
        t = min(_num(wall_thickness, "wall_thickness", 0.4, MAX_DIM), min(L, W) / 2.0 - 1.0, H / 2.0)
        outer = cq.Workplane("XY").box(L, W, H, centered=(True, True, False))
        cavity = cq.Solid.makeBox(L - 2 * t, W - 2 * t, H - t + 1.0, V(-(L - 2 * t) / 2.0, -(W - 2 * t) / 2.0, t))
        body = _cut(outer, [cavity])

        boss_solids, boss_holes = [], []
        for b in list(bosses or [])[:MAX_LIST]:
            od = _num(b.get("od", 8.0), "boss od", 1.0, MAX_DIM)
            idia = min(_num(b.get("id", 3.0), "boss id", 0.0, MAX_DIM), od - 1.0)
            bh = _num(b.get("height", H - t - 2.0), "boss height", 1.0, H - t)
            c = str(b.get("corner", "")).upper()
            if c:
                x = (1 if "E" in c else -1) * (L / 2.0 - t - od / 2.0 + 0.6)
                y = (1 if "N" in c else -1) * (W / 2.0 - t - od / 2.0 + 0.6)
            else:
                x = _num(b.get("x", 0.0), "boss x", -MAX_DIM, MAX_DIM)
                y = _num(b.get("y", 0.0), "boss y", -MAX_DIM, MAX_DIM)
            boss_solids.append(_cyl(od / 2.0, bh + 1.0, x, y, t - 1.0, (0, 0, 1)))
            if idia > 0.3:
                boss_holes.append(_cyl(idia / 2.0, t + bh + 1.0 - t * 0.5, x, y, t * 0.5, (0, 0, 1)))
        if boss_solids:
            body = _fuse(body, boss_solids)
        body = _cut(body, boss_holes)

        tools = []
        for c in list(cutouts or [])[:MAX_LIST]:
            face = str(c.get("face", ">X")).strip()
            u = _num(c.get("u", 0.0), "cutout u", -MAX_DIM, MAX_DIM)
            v = _num(c.get("v", H / 2.0), "cutout v", -MAX_DIM, MAX_DIM)
            circ = str(c.get("shape", "rect")).lower() == "circle"
            w = _num(c.get("w", 10.0), "cutout w", 0.5, MAX_DIM)
            h = _num(c.get("h", 6.0), "cutout h", 0.5, MAX_DIM)
            dia = _num(c.get("dia", 8.0), "cutout dia", 0.5, MAX_DIM)
            n = t + 2.0
            if face in (">X", "<X"):
                x0 = (L / 2.0 - t - 1.0) if face == ">X" else (-L / 2.0 - 1.0)
                tools.append(_cyl(dia / 2.0, n, x0, u, v, (1, 0, 0)) if circ
                             else cq.Solid.makeBox(n, w, h, V(x0, u - w / 2.0, v - h / 2.0)))
            elif face in (">Y", "<Y"):
                y0 = (W / 2.0 - t - 1.0) if face == ">Y" else (-W / 2.0 - 1.0)
                tools.append(_cyl(dia / 2.0, n, u, y0, v, (0, 1, 0)) if circ
                             else cq.Solid.makeBox(w, n, h, V(u - w / 2.0, y0, v - h / 2.0)))
            elif face == "<Z":
                tools.append(_cyl(dia / 2.0, n, u, v, -1.0, (0, 0, 1)) if circ
                             else cq.Solid.makeBox(w, h, n, V(u - w / 2.0, v - h / 2.0, -1.0)))
            else:
                raise BuilderError("cutout face must be one of >X <X >Y <Y <Z")
        return _cut(body, tools)

    def manifold_block(self, dims, main_bore, cross_ports=None, gland=None):
        try:
            dx, dy, dz = [_num(v, "dims", 5.0, MAX_DIM) for v in dims]
        except (TypeError, ValueError):
            raise BuilderError("dims must be (x, y, z)")
        body = cq.Workplane("XY").box(dx, dy, dz)
        rb = _num(main_bore, "main_bore", 0.5, min(dy, dz) - 2.0) / 2.0
        tools = [_cyl(rb, dx + 2.0, -dx / 2.0 - 1.0, 0, 0, (1, 0, 0))]

        for p in list(cross_ports or [])[:MAX_LIST]:
            axis = str(p.get("axis", "Z")).upper()
            if axis not in ("Y", "Z"):
                raise BuilderError("cross_port axis must be Y or Z")
            r = _num(p.get("dia", 6.0), "port dia", 0.5, MAX_DIM) / 2.0
            pos = _num(p.get("pos", 0.0), "port pos", -dx / 2.0 + r + 1.0, dx / 2.0 - r - 1.0)
            half = (dz if axis == "Z" else dy) / 2.0
            depth = p.get("depth")
            length = (half + 1.0) if depth is None else _num(depth, "port depth", 0.5, half * 2.0 - 1.0) + 1.0
            side = str(p.get("side", "+"))
            for sgn in ((1, -1) if side == "both" else (1 if side != "-" else -1,)):
                start = sgn * (half + 1.0)
                if axis == "Z":
                    tools.append(_cyl(r, length, pos, 0, start, (0, 0, -sgn)))
                else:
                    tools.append(_cyl(r, length, pos, start, 0, (0, -sgn, 0)))

        if gland:
            face = str(gland.get("face", ">X"))
            idia = max(_num(gland.get("id", rb * 2 + 4.0), "gland id", 1.0, MAX_DIM), rb * 2 + 2.0)
            odia = min(max(_num(gland.get("od", idia + 3.0), "gland od", 1.0, MAX_DIM), idia + 2.0), min(dy, dz) - 2.0)
            gd = _num(gland.get("depth", 2.0), "gland depth", 0.3, dx / 2.0)
            if odia > idia + 0.5:
                x_face = dx / 2.0 if face == ">X" else -dx / 2.0
                x0 = x_face - gd if face == ">X" else x_face - 1.0
                ring = _cyl(odia / 2.0, gd + 1.0, x0, 0, 0, (1, 0, 0)).cut(
                    _cyl(idia / 2.0, gd + 3.0, x0 - 1.0, 0, 0, (1, 0, 0)))
                tools.append(ring)
        return _cut(body, tools)
