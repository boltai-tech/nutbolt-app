"""Electronic Project Enclosures, PCB Standoffs & Vent Grilles"""
import re

def match(prompt: str) -> str:
    p = prompt.lower()

    if "enclosure" in p or "box" in p or "housing" in p or "case" in p:
        l = 100.0
        w = 70.0
        h = 35.0
        m_l = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:length|long)", p)
        if m_l: l = float(m_l.group(1))
        m_w = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:width|wide)", p)
        if m_w: w = float(m_w.group(1))

        return f"""params = {{
    "length": {l},
    "width": {w},
    "height": {h},
    "wall_thick": 3.0,
    "boss_dia": 7.0,
    "screw_hole": 2.8
}}
l, w, h, t = params["length"], params["width"], params["height"], params["wall_thick"]
bd, sh = params["boss_dia"], params["screw_hole"]

# Main outer tub
body = cq.Workplane("XY").box(l, w, h, centered=(True, True, False))
pocket = cq.Workplane("XY").workplane(offset=t).box(l - 2*t, w - 2*t, h, centered=(True, True, False))

# 4 Corner mounting bosses with screw pilot holes
cx = l/2.0 - t - bd/2.0
cy = w/2.0 - t - bd/2.0
corner_pts = [(-cx, -cy), (cx, -cy), (-cx, cy), (cx, cy)]

bosses = cq.Workplane("XY").workplane(offset=t).pushPoints(corner_pts).circle(bd / 2.0).extrude(h - t)
holes = cq.Workplane("XY").workplane(offset=t).pushPoints(corner_pts).circle(sh / 2.0).extrude(h)

result = body.cut(pocket).union(bosses).cut(holes)
"""

    return None
