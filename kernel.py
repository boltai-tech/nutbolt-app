import os
import re
import ast
import json
import math
import requests
import cadquery as cq
from cadquery import exporters

SYSTEM_PROMPT = """You are a Principal CAD Engineer writing CadQuery Python scripts.
Generate a single-body, watertight 3D solid.

STRICT RULES:
1. Declare parameters at the top:
params = {
    "width": 50.0,
    "height": 60.0,
    "thickness": 5.0
}
2. Assign final geometry to `result`.
3. Output ONLY raw executable Python code. No markdown (no ```python), no comments.
4. GEOMETRY RULES (NO FLOATING PARTS):
   - NEVER use multiple .box() calls with .translate(). That creates floating disconnected slabs.
   - For L-Brackets, U-Channels, and Angles: Draw a single 2D closed profile on Workplane("XZ") using .polyline([...]).close().extrude(width).
   - For Plates, Flanges, Cylinders: Start with a single .box() or .circle().extrude().
   - Cut holes directly on faces using .faces(">Z").workplane().pushPoints([...]).hole(d) or .faces(">Y").workplane().hole(d).
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
        except Exception:
            val = v
        lines.append(f'    "{k}": {val},')
    lines.append("}")
    new_block = "\n".join(lines)
    return re.sub(r"params\s*=\s*\{[^}]*\}", new_block, code_str, count=1)

def execute_and_verify(code_str: str):
    scope = {"cq": cq, "math": math}
    exec(code_str, scope)
    res = scope.get("result")
    if res is None:
        raise ValueError("Missing 'result' variable")
    val = res.val()
    if val is None or val.Volume() <= 0.001:
        raise ValueError("Empty volume")
    return res

def compile_to_files(code_str: str, session_id: str):
    try:
        res = execute_and_verify(code_str)
        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)
        stl_path = os.path.join(out_dir, "part.stl")
        step_path = os.path.join(out_dir, "part.step")

        exporters.export(res, stl_path, exporters.ExportTypes.STL, tolerance=0.2, angularTolerance=0.2)
        exporters.export(res, step_path, exporters.ExportTypes.STEP)

        val = res.val()
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

    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    payload = {
        "contents": [{"parts": [{"text": SYSTEM_PROMPT}, {"text": f"Build CAD model for: {prompt}"}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 800}
    }

    for model in ["gemini-2.5-flash", "gemini-1.5-flash"]:
        url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){model}:generateContent?key={key}"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=8)
            if resp.status_code == 200:
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                clean = re.sub(r"^```python\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
                execute_and_verify(clean)
                return clean
        except Exception as e:
            print(f"[{model} skipped]: {e}")

    return fallback_generator(prompt)

def fallback_generator(prompt: str) -> str:
    p = prompt.lower()
    if "bracket" in p or "l-shape" in p:
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
    "center_bore": 20.0,
    "mount_hole": 5.0
}
pts = [(-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-20.0, 20.0)]
result = (
    cq.Workplane("XY").box(params["width"], params["length"], params["thickness"])
    .faces(">Z").workplane().hole(params["center_bore"])
    .faces(">Z").workplane().pushPoints(pts).hole(params["mount_hole"])
)
"""
