import ast
import math
import os
import re

import cadquery as cq
from cadquery import exporters
import requests

SYSTEM_PROMPT = """You are a Principal CAD Engineer writing CadQuery Python scripts.
Output ONLY executable Python code. No markdown fences, no comments.

RULES:
1. First statement must be params = {...}
2. Final object must be assigned to result.
3. Use only valid CadQuery Python.
4. For L-brackets, U-channels, angles, and bent profiles:
   - draw one closed 2D polygon on Workplane("XZ") using .polyline([...]).close().extrude()
   - never emit disconnected floating slabs or multiple independent .box() pieces with .translate()
5. For plates, flanges, spacers, sleeves, washers:
   - use one closed profile or one .box() or one .circle().extrude()
6. Holes must be cut with .faces(">Z").workplane().pushPoints([...]).hole(d) or .faces("<Y").workplane().hole(d)
7. Return only Python code, nothing else.
"""

def extract_params_from_code(code_str: str) -> dict:
    try:
        tree = ast.parse(code_str)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "params":
                        return ast.literal_eval(node.value)
    except Exception:
        pass
    return {}

def inject_params(code_str: str, new_params: dict) -> str:
    lines = ["params = {"]
    for k, v in new_params.items():
        try:
            val = float(v)
            if float(val).is_integer():
                val = int(val)
        except Exception:
            val = v
        lines.append(f'    "{k}": {val},')
    lines.append("}")
    new_block = "\n".join(lines)
    return re.sub(r"params\s*=\s*\{[^}]*\}", new_block, code_str, count=1)

def compile_to_files(code_str: str, session_id: str):
    try:
        scope = {"cq": cq, "math": math}
        exec(code_str, scope)
        res = scope.get("result")
        if res is None:
            return None, None, None

        val = res.val()
        if val is None or val.Volume() <= 0.001:
            return None, None, None

        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)
        stl_path = os.path.join(out_dir, "part.stl")
        step_path = os.path.join(out_dir, "part.step")

        exporters.export(res, stl_path, exporters.ExportTypes.STL, tolerance=0.3, angularTolerance=0.3)
        exporters.export(res, step_path, exporters.ExportTypes.STEP)

        bbox = val.BoundingBox()
        telemetry = {
            "volume_cm3": round(val.Volume() / 1000.0, 3),
            "bbox_mm": [round(bbox.xlen, 2), round(bbox.ylen, 2), round(bbox.zlen, 2)]
        }
        return stl_path, step_path, telemetry
    except Exception as e:
        print(f"[Compile Error]: {e}")
        return None, None, None

def call_gemini(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return fallback_generator(prompt)

    models = ["gemini-1.5-flash", "gemini-2.5-flash"]
    last_error = None

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": SYSTEM_PROMPT + "\nPrompt: " + prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 600,
                "responseMimeType": "text/plain"
            }
        }

        if "2.5" in model:
            payload["thinkingConfig"] = {"thinkingBudget": 0}

        try:
            resp = requests.post(url, json=payload, timeout=5.5)
            if resp.status_code != 200:
                last_error = resp.text
                continue

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                continue

            raw = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            clean = re.sub(r"^```python\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
            if "result" in clean and "params" in clean:
                return clean
        except Exception as exc:
            last_error = str(exc)

    print(f"[Gemini fallback]: {last_error or 'No valid model response'}")
    return fallback_generator(prompt)

def fallback_generator(prompt: str) -> str:
    p = prompt.lower()

    if "u-channel" in p or "channel" in p:
        return """params = {
    "width": 80.0,
    "flange_height": 40.0,
    "thickness": 6.0,
    "length": 100.0,
    "hole_dia": 8.0
}
w, h, t = params["width"], params["flange_height"], params["thickness"]
pts = [(0,0), (w,0), (w,h), (w-t,h), (w-t,t), (t,t), (t,h), (0,h)]
result = (
    cq.Workplane("XZ").polyline(pts).close().extrude(params["length"])
    .faces("<Z").workplane()
    .pushPoints([(0, -params["length"]*0.25), (0, params["length"]*0.25)])
    .hole(params["hole_dia"])
)
"""

    if "bushing" in p or "spacer" in p or "sleeve" in p:
        return """params = {
    "outer_dia": 40.0,
    "inner_bore": 16.0,
    "height": 35.0
}
result = (
    cq.Workplane("XY")
    .circle(params["outer_dia"] / 2.0)
    .circle(params["inner_bore"] / 2.0)
    .extrude(params["height"])
)
"""

    if "bracket" in p or "l-shape" in p or "angle" in p:
        return """params = {
    "width": 50.0,
    "base_length": 60.0,
    "wall_height": 50.0,
    "thickness": 5.0,
    "base_hole": 6.0,
    "wall_hole": 20.0
}
pts = [
    (0.0, 0.0),
    (params["base_length"], 0.0),
    (params["base_length"], params["thickness"]),
    (params["thickness"], params["thickness"]),
    (params["thickness"], params["wall_height"]),
    (0.0, params["wall_height"])
]
result = (
    cq.Workplane("XZ")
    .polyline(pts)
    .close()
    .extrude(params["width"])
    .faces("<Y").workplane()
    .pushPoints([(params["wall_height"] * 0.55, 0.0)])
    .hole(params["wall_hole"])
    .faces("<Z").workplane()
    .pushPoints([
        (params["base_length"] * 0.65, -params["width"] * 0.25),
        (params["base_length"] * 0.65, params["width"] * 0.25)
    ])
    .hole(params["base_hole"])
)
"""

    if "flange" in p or "pipe" in p or "cylinder" in p:
        return """params = {
    "outer_dia": 90.0,
    "bore_dia": 30.0,
    "pcd": 65.0,
    "hole_dia": 8.0,
    "thickness": 8.0
}
import math
bolt_pts = [((params["pcd"]/2)*math.cos(i*math.pi/2), (params["pcd"]/2)*math.sin(i*math.pi/2)) for i in range(4)]
result = (
    cq.Workplane("XY").circle(params["outer_dia"]/2).extrude(params["thickness"])
    .faces(">Z").workplane().hole(params["bore_dia"])
    .faces(">Z").workplane().pushPoints(bolt_pts).hole(params["hole_dia"])
)
"""

    return """params = {
    "width": 60.0,
    "length": 60.0,
    "thickness": 5.0,
    "center_bore": 22.0,
    "mount_hole": 3.5,
    "hole_spacing": 31.0
}
s = params["hole_spacing"] / 2.0
pts = [(-s, -s), (s, -s), (s, s), (-s, s)]
result = (
    cq.Workplane("XY").box(params["width"], params["length"], params["thickness"])
    .faces(">Z").workplane().hole(params["center_bore"])
    .faces(">Z").workplane().pushPoints(pts).hole(params["mount_hole"])
)
"""
