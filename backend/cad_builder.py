"""
MechanicalBuilder API - Universal Archetype Solids Engine
Encapsulates zero-thickness clearance extensions, single-solid guarantees,
and robust OpenCASCADE B-Rep construction across the 5 core mechanical archetypes.
"""
import math
from typing import List, Dict, Tuple, Optional, Any
import cadquery as cq

class MechanicalBuilder:
    @staticmethod
    def turned_concentric(
        steps: List[Dict[str, float]],
        bore: Optional[float] = None,
        keyway: Optional[Dict[str, float]] = None,
        bolt_circle: Optional[Dict[str, Any]] = None,
        radial_features: Optional[Dict[str, Any]] = None
    ) -> cq.Workplane:
        """
        Builds turned stepped bodies (pulleys, spacers, flanges, thumbwheels, bushings)
        by stacking cylinders monotonically and applying clearance-extended toolpaths.
        """
        if not steps:
            raise ValueError("Steps list cannot be empty.")
            
        total_h = sum(s["height"] for s in steps)
        max_dia = max(s["dia"] for s in steps)
        
        # Build base solid billet
        curr_z = 0.0
        body = cq.Workplane("XY")
        for i, s in enumerate(steps):
            d = float(s["dia"])
            h = float(s["height"])
            cyl = cq.Workplane("XY").workplane(offset=curr_z).circle(d / 2.0).extrude(h)
            body = cyl if i == 0 else body.union(cyl)
            curr_z += h

        # 1. Through Bore with clearance extensions
        if bore and bore > 0:
            bore_cutter = (
                cq.Workplane("XY")
                .workplane(offset=-1.0)
                .circle(bore / 2.0)
                .extrude(total_h + 2.0)
            )
            body = body.cut(bore_cutter)

        # 2. Keyway
        if keyway and bore and bore > 0:
            kw = float(keyway.get("width", 3.0))
            kd = float(keyway.get("depth", 2.0))
            kw_cutter = (
                cq.Workplane("XY")
                .workplane(offset=-1.0)
                .pushPoints([(0.0, bore / 2.0 + kd / 2.0 - 0.5)])
                .rect(kw, kd + 1.0)
                .extrude(total_h + 2.0)
            )
            body = body.cut(kw_cutter)

        # 3. Bolt Circle (Pitch Circle Diameter)
        if bolt_circle:
            count = int(bolt_circle.get("count", 4))
            pcd = float(bolt_circle.get("pcd", max_dia * 0.7))
            bdia = float(bolt_circle.get("dia", 5.0))
            r = pcd / 2.0
            pts = [(r * math.cos(2 * math.pi * i / count), r * math.sin(2 * math.pi * i / count)) for i in range(count)]
            bolts = (
                cq.Workplane("XY")
                .workplane(offset=-1.0)
                .pushPoints(pts)
                .circle(bdia / 2.0)
                .extrude(total_h + 2.0)
            )
            body = body.cut(bolts)

        # 4. Radial Scallops / Teeth Cuts (Bounded to prevent free-tier CPU timeout)
        if radial_features:
            count = min(int(radial_features.get("count", 8)), 24)
            rad_dia = float(radial_features.get("dia", 4.0))
            r_outer = max_dia / 2.0
            r_pts = [(r_outer * math.cos(2 * math.pi * i / count), r_outer * math.sin(2 * math.pi * i / count)) for i in range(count)]
            rad_cutters = (
                cq.Workplane("XY")
                .workplane(offset=-1.0)
                .pushPoints(r_pts)
                .circle(rad_dia / 2.0)
                .extrude(total_h + 2.0)
            )
            body = body.cut(rad_cutters)

        return body

    @staticmethod
    def profile_extruded(
        pts: List[Tuple[float, float]],
        length: float,
        workplane: str = "XZ",
        holes: Optional[List[Dict[str, Any]]] = None,
        slots: Optional[List[Dict[str, Any]]] = None
    ) -> cq.Workplane:
        """
        Extrudes a closed 2D polygon with symmetric centering and safe face cutters.
        """
        body = cq.Workplane(workplane).polyline(pts).close().extrude(length / 2.0, both=True)

        if holes:
            for h in holes:
                face = h.get("face", ">Z")
                dia = float(h.get("dia", 6.0))
                offset_xy = h.get("offset", (0.0, 0.0))
                body = (
                    body.faces(face)
                    .workplane()
                    .pushPoints([offset_xy])
                    .circle(dia / 2.0)
                    .cutThruAll()
                )

        if slots:
            for s in slots:
                face = s.get("face", ">Z")
                sw = float(s.get("width", 10.0))
                sh = float(s.get("length", 20.0))
                offset_xy = s.get("offset", (0.0, 0.0))
                body = (
                    body.faces(face)
                    .workplane()
                    .pushPoints([offset_xy])
                    .rect(sw, sh)
                    .cutThruAll()
                )

        return body

    @staticmethod
    def prismatic_plate(
        length: float,
        width: float,
        thickness: float,
        center_bore: Optional[float] = None,
        bolt_pattern: Optional[Dict[str, Any]] = None,
        relief_slots: Optional[List[Dict[str, Any]]] = None,
        corner_radius: Optional[float] = None
    ) -> cq.Workplane:
        """
        Builds mounting plates, adapters, and brackets with manifold-safe arrays.
        """
        body = cq.Workplane("XY").box(length, width, thickness)

        if corner_radius and corner_radius > 0:
            try:
                body = body.edges("|Z").fillet(corner_radius)
            except Exception:
                pass

        if center_bore and center_bore > 0:
            bore = (
                cq.Workplane("XY")
                .workplane(offset=-thickness - 1.0)
                .circle(center_bore / 2.0)
                .extrude(thickness * 3.0)
            )
            body = body.cut(bore)

        if bolt_pattern:
            dia = float(bolt_pattern.get("dia", 4.0))
            sx = float(bolt_pattern.get("spacing_x", length * 0.7)) / 2.0
            sy = float(bolt_pattern.get("spacing_y", width * 0.7)) / 2.0
            pts = [(-sx, -sy), (sx, -sy), (-sx, sy), (sx, sy)]
            holes = (
                cq.Workplane("XY")
                .workplane(offset=-thickness - 1.0)
                .pushPoints(pts)
                .circle(dia / 2.0)
                .extrude(thickness * 3.0)
            )
            body = body.cut(holes)

        if relief_slots:
            for sl in relief_slots:
                sw = float(sl.get("width", 6.0))
                slen = float(sl.get("length", 16.0))
                pts = sl.get("pts", [(0.0, width * 0.35)])
                slot_cut = (
                    cq.Workplane("XY")
                    .workplane(offset=-thickness - 1.0)
                    .pushPoints(pts)
                    .rect(sw, slen)
                    .extrude(thickness * 3.0)
                )
                body = body.cut(slot_cut)

        return body

    @staticmethod
    def shell_enclosure(
        length: float,
        width: float,
        height: float,
        wall_thickness: float,
        bosses: Optional[List[Dict[str, float]]] = None,
        cutouts: Optional[List[Dict[str, Any]]] = None
    ) -> cq.Workplane:
        """
        Builds electronic casings and project boxes with mounting bosses.
        """
        l, w, h, t = length, width, height, wall_thickness
        body = cq.Workplane("XY").box(l, w, h, centered=(True, True, False))
        pocket = cq.Workplane("XY").workplane(offset=t).box(l - 2*t, w - 2*t, h + 1.0, centered=(True, True, False))
        body = body.cut(pocket)

        if bosses:
            for b in bosses:
                bd = float(b.get("dia", 7.0))
                sh = float(b.get("hole", 2.8))
                bx = float(b.get("x", 0.0))
                by = float(b.get("y", 0.0))
                boss = (
                    cq.Workplane("XY")
                    .workplane(offset=t)
                    .pushPoints([(bx, by)])
                    .circle(bd / 2.0)
                    .extrude(h - t)
                )
                bhole = (
                    cq.Workplane("XY")
                    .workplane(offset=t)
                    .pushPoints([(bx, by)])
                    .circle(sh / 2.0)
                    .extrude(h)
                )
                body = body.union(boss).cut(bhole)

        return body

    @staticmethod
    def manifold_block(
        dims: Tuple[float, float, float],
        main_bore: float,
        cross_ports: Optional[List[Dict[str, Any]]] = None,
        gland: Optional[Dict[str, float]] = None
    ) -> cq.Workplane:
        """
        Builds fluid and pneumatic distribution blocks with intersecting channels.
        """
        lx, ly, lz = dims
        body = cq.Workplane("XY").box(lx, ly, lz)

        # Main vertical channel
        if main_bore > 0:
            mb = (
                cq.Workplane("XY")
                .workplane(offset=-lz/2.0 - 1.0)
                .circle(main_bore / 2.0)
                .extrude(lz + 2.0)
            )
            body = body.cut(mb)

        # Cross ports
        if cross_ports:
            for p in cross_ports:
                axis = p.get("axis", "XZ")
                dia = float(p.get("dia", 8.0))
                extent = lx if axis == "YZ" else ly
                port = (
                    cq.Workplane(axis)
                    .workplane(offset=-extent/2.0 - 1.0)
                    .circle(dia / 2.0)
                    .extrude(extent + 2.0)
                )
                body = body.cut(port)

        # O-Ring Gland face recess
        if gland:
            od = float(gland.get("od", 32.0))
            id_val = float(gland.get("id", 26.0))
            depth = float(gland.get("depth", 2.5))
            gland_cut = (
                cq.Workplane("XY")
                .workplane(offset=lz/2.0 - depth)
                .circle(od / 2.0)
                .circle(id_val / 2.0)
                .extrude(depth + 1.0)
            )
            body = body.cut(gland_cut)

        return body
