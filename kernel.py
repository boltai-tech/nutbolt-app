import os
import re
import ast
import requests
import cadquery as cq
from cadquery import exporters

SYSTEM_PROMPT = """You are a Principal Computational CAD & Mechanical Design Engineer specializing in OpenCASCADE and CadQuery Python.
Translate natural language specifications into a valid, watertight, single-body manifold CadQuery 3D model.

CRITICAL FEATURE RETENTION:
1. Wrap all key dimensions at the very top in a dictionary named `params`. Example:
   params = {
       "length": 100.0,
       "width": 60.0,
       "thickness": 8.0,
       "center_bore": 25.0
   }
2. Assign the final CadQuery object to a variable named `result`.
3. Do NOT import cadquery (it is pre-injected in runtime execution scope as `cq`).
4. Output ONLY raw executable Python code. No markdown fences, no conversational commentary.
5. SINGLE SOLID CONTINUITY:
   - The output must always remain ONE single connected solid body.
   - Build from the primary base mass first, add features via .union(), and perform subtractions/holes (.cut()) last.
6. OPENCASCADE STABILITY:
   - CSG only. Avoid zero-thickness tangencies and manifold collisions.
"""

def extract_params_from_code(code_str: str) -> dict:
    try:
        tree = ast.parse(code_str)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "params":
                        return ast.literal_eval(node.value)
    except Exception as e:
        print(f"[AST Parse Warning]: {e}")
    return {}

def inject_params(code_str: str, new_params: dict) -> str:
    pattern = r"params\s*=\s*\{[^\}]*\}"
    formatted = "params = {\n" + ",\n".join(f'    "{k}": {v}' for k, v in new_params.items()) + "\n}"
    return re.sub(pattern, formatted, code_str, count=1)

def validate_and_compile(code_str: str) -> bool:
    exec_scope = {"cq": cq}
    try:
        exec(code_str, exec_scope)
        res = exec_scope.get("result")
        return res is not None
    except Exception as e:
        print(f"[CadQuery Compilation Error]: {e}")
        return False

def compile_to_files(code_str: str, session_id: str):
    exec_scope = {"cq": cq}
    try:
        exec(code_str, exec_scope)
        res = exec_scope.get("result")
        if res is None:
            return None, None, None

        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)

        stl_path = os.path.join(out_dir, "part.stl")
        step_path = os.path.join(out_dir, "part.step")

        exporters.export(res, stl_path, exporters.ExportTypes.STL, tolerance=0.1, angularTolerance=0.1)
        exporters.export(res, step_path, exporters.ExportTypes.STEP)

        val = res.val()
        vol_cm3 = round(val.Volume() / 1000.0, 3)
        bbox = val.BoundingBox()
        bbox_dims = [round(bbox.xlen, 2), round(bbox.ylen, 2), round(bbox.zlen, 2)]

        telemetry = {
            "volume_cm3": vol_cm3,
            "bbox_mm": bbox_dims
        }

        return stl_path, step_path, telemetry
    except Exception as e:
        print(f"[Compile Export Error]: {e}")
        return None, None, None

def fallback_generator(prompt: str) -> str:
    p = prompt.lower()
    
    # Rectangular plate / mounting plate
    if "plate" in p or "mount" in p or "rectangular" in p:
        return """params = {
    "length": 100.0,
    "width": 60.0,
    "thickness": 8.0,
    "center_bore": 25.0,
    "hole_dia": 6.0,
    "inset": 10.0
}
base = cq.Workplane("XY").box(params["length"], params["width"], params["thickness"])
base = base.faces(">Z").workplane().hole(params["center_bore"])
pts = [
    (params["length"]/2 - params["inset"], params["width"]/2 - params["inset"]),
    (-params["length"]/2 + params["inset"], params["width"]/2 - params["inset"]),
    (params["length"]/2 - params["inset"], -params["width"]/2 + params["inset"]),
    (-params["length"]/2 + params["inset"], -params["width"]/2 + params["inset"])
]
base = base.faces(">Z").workplane().pushPoints(pts).hole(params["hole_dia"])
result = base
"""

    # Bracket / L-shape
    if "bracket" in p or "l-shape" in p:
        return """params = {
    "width": 50.0,
    "height": 60.0,
    "thickness": 5.0,
    "pilot_dia": 22.0
}
base = cq.Workplane("XY").box(params["width"], params["width"], params["thickness"])
vert = cq.Workplane("XZ").transformed(offset=(0, params["width"]/2, params["height"]/2)).box(params["width"], params["thickness"], params["height"])
body = base.union(vert)
body = body.faces(">Y").workplane().hole(params["pilot_dia"])
result = body
"""

    # Flange
    if "flange" in p:
        return """params = {
    "outer_dia": 90.0,
    "thickness": 12.0,
    "bore_dia": 40.0,
    "bolt_dia": 8.0,
    "pcd": 68.0
}
base = cq.Workplane("XY").circle(params["outer_dia"] / 2).extrude(params["thickness"])
base = base.faces(">Z").workplane().hole(params["bore_dia"])
base = base.faces(">Z").workplane().polarArray(params["pcd"] / 2, 0, 360, 6).hole(params["bolt_dia"])
result = base
"""

    # Default Shaft / Hub
    return """params = {
    "outer_dia": 60.0,
    "thickness": 10.0,
    "bore_dia": 12.0
}
base = cq.Workplane("XY").circle(params["outer_dia"] / 2).extrude(params["thickness"])
base = base.faces(">Z").workplane().hole(params["bore_dia"])
result = base
"""

def call_gemini(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        print("[AI Synthesis] GEMINI_API_KEY is missing on Render.")
        return fallback_generator(prompt)

    payload = {
        "contents": [{
            "parts": [
                {"text": SYSTEM_PROMPT},
                {"text": f"Engineering Request: {prompt}\nOutput raw executable CadQuery Python code only."}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": key
    }

    # Verified modern model endpoints
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest"
    ]

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"]
                    clean_code = re.sub(r"^```python\s*|^```\s*|```$", "", text.strip(), flags=re.MULTILINE)
                    if validate_and_compile(clean_code):
                        print(f"[AI Synthesis Success] Generated unique model using {model}!")
                        return clean_code
                    else:
                        print(f"[{model}] Generated code failed CAD compilation.")
            else:
                print(f"[{model}] HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            print(f"[{model}] Error: {e}")

    print("[AI Synthesis] Models unavailable, using dynamic fallback for prompt.")
    return fallback_generator(prompt)
