import os
import re
import ast
import json
import requests
import cadquery as cq
from cadquery import exporters

SYSTEM_PROMPT = """You are a Principal Computational CAD Kernel Engineer.
Generate production-grade, mathematically watertight CadQuery Python code.

MANDATORY RULES:
1. Always declare parameters at the top inside a single dictionary:
params = {
    "key_name": 10.0
}
2. The final geometry MUST be assigned to the variable named `result`.
3. Output ONLY raw executable Python code. No markdown fences, no explanatory text.
4. WATERTIGHT SINGLE-BODY MANIFOLD RULES:
   - NEVER create multiple separate solids and position them with manual .translate() calls (this causes floating, detached slabs).
   - Angle Brackets / L-Shapes / Channels:
     Draw the 2D cross-section profile on Workplane("XZ") or Workplane("XY") using:
     .polyline([(x0, y0), (x1, y1), ...]).close().extrude(thickness_or_width)
   - Prismatic / Cylindrical parts:
     Create base solid with .box(L, W, H, centered=True) or .circle(R).extrude(H).
   - Hole cutting:
     Select distinct faces unambiguously using:
     .faces(">Z").workplane().pushPoints([...]).hole(dia)
     .faces(">Y").workplane().pushPoints([...]).hole(dia)
     .faces("<Z").workplane().pushPoints([...]).hole(dia)
5. Keep topology minimal, robust, and fully connected.
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
        except (ValueError, TypeError):
            val = v
        lines.append(f'    "{k}": {val},')
    lines.append("}")
    new_params_block = "\n".join(lines)
    return re.sub(r"params\s*=\s*\{.*?\n\}", new_params_block, code_str, count=1, flags=re.DOTALL)

def execute_and_verify(code_str: str):
    scope = {"cq": cq}
    exec(code_str, scope)
    res = scope.get("result")
    if res is None:
        raise ValueError("Code did not set variable 'result'")
    val = res.val()
    if val is None or val.Volume() <= 0.001:
        raise ValueError("Solid geometry is empty or non-manifold")
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
        print(f"[CAD Engine Error]: {e}")
        return None, None, None

def call_gemini(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return fallback_generator(prompt)

    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    payload = {
        "contents": [
            {"parts": [{"text": SYSTEM_PROMPT}, {"text": f"Engineering Request: {prompt}\nCadQuery Python:"}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 800
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=8)
        if resp.status_code == 200:
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            clean = re.sub(r"^```python\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
            execute_and_verify(clean)
            return clean
    except Exception as e:
        print(f"[Gemini 2.5 synthesis bypassed: {e}]")

    return fallback_generator(prompt)

def fallback_generator(prompt: str) -> str:
    p = prompt.lower()
    if "bracket" in p or "l-shape" in p:
        return """params = {
    "base_length": 60.0,
    "wall_height": 50.0,
    "width": 50.0,
    "thickness": 5.0,
    "base_hole_dia": 6.0,
    "face_hole_dia": 20.0
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
    .pushPoints([(params["wall_height"]/2, 0.0)])
    .hole(params["face_hole_dia"])
    .faces("<Z").workplane()
    .pushPoints([(params["base_length"]*0.65, -params["width"]*0.25), (params["base_length"]*0.65, params["width"]*0.25)])
    .hole(params["base_hole_dia"])
)
"""
    if "flange" in p:
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
    "size": 60.0,
    "thick": 4.0,
    "pilot": 24.0,
    "pitch": 31.0,
    "motor_hole": 3.5,
    "base_hole": 5.0
}
p = params["pitch"]/2
motor_pts = [(p, p), (-p, p), (-p, -p), (p, -p)]
base_pts = [(-22.5, -20.0), (22.5, -20.0)]
result = (
    cq.Workplane("XY").box(params["size"], params["size"], params["thick"])
    .faces(">Z").workplane().hole(params["pilot"])
    .faces(">Z").workplane().pushPoints(motor_pts).hole(params["motor_hole"])
    .faces(">Z").workplane().pushPoints(base_pts).hole(params["base_hole"])
)
"""
