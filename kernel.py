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
       "outer_dia": 60.0,
       "thickness": 6.0,
       "bore_dia": 8.0
   }
2. Assign the final CadQuery object to a variable named `result`.
3. Do NOT import cadquery (it is pre-injected in runtime execution scope as `cq`).
4. Output ONLY raw executable Python code. No markdown fences, no conversational commentary.
5. SINGLE SOLID CONTINUITY:
   - The output must always remain ONE single connected solid body.
   - Build from the primary base mass first, add features via .union(), and perform subtractions/holes (.cut()) last.
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
    if "bracket" in p or "l-shape" in p:
        return """params = {
    "width": 50.0,
    "height": 60.0,
    "thickness": 4.0,
    "hole_dia": 12.0
}
base = cq.Workplane("XY").box(params["width"], params["width"], params["thickness"])
vert = cq.Workplane("XZ").transformed(offset=(0, params["width"]/2, params["height"]/2)).box(params["width"], params["thickness"], params["height"])
result = base.union(vert)
result = result.faces(">Z").workplane().hole(params["hole_dia"])
"""
    if "geneva" in p:
        return """params = {
    "outer_dia": 70.0,
    "thickness": 6.0,
    "bore_dia": 8.0,
    "slot_w": 4.0
}
wheel = cq.Workplane("XY").circle(params["outer_dia"] / 2).extrude(params["thickness"])
wheel = wheel.faces(">Z").workplane().hole(params["bore_dia"])
for angle in [0, 90, 180, 270]:
    slot = cq.Workplane("XY").rect(params["slot_w"], params["outer_dia"] / 2).extrude(params["thickness"]).translate((0, params["outer_dia"] / 4, 0)).rotate((0,0,0), (0,0,1), angle)
    wheel = wheel.cut(slot)
result = wheel
"""
    return """params = {
    "outer_dia": 60.0,
    "thickness": 6.0,
    "bore_dia": 8.0,
    "key_w": 2.0,
    "key_h": 1.0
}
base = cq.Workplane("XY").circle(params["outer_dia"] / 2).extrude(params["thickness"])
base = base.faces(">Z").workplane().hole(params["bore_dia"])
key = cq.Workplane("XY").rect(params["key_w"], params["bore_dia"] + params["key_h"] * 2).extrude(params["thickness"])
result = base.cut(key)
"""

def call_gemini(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        print("[AI Synthesis] CRITICAL: GEMINI_API_KEY environment variable is empty.")
        return fallback_generator(prompt)

    payload = {
        "contents": [{
            "parts": [
                {"text": SYSTEM_PROMPT},
                {"text": f"Engineering Request: {prompt}\nOutput ONLY executable Python code."}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048
        }
    }

    # Pass the key in BOTH the header and the URL query param for universal auth support
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": key
    }

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash"
    ]

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
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
                print(f"[{model}] API Status {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            print(f"[{model}] Request failed: {e}")

    print("[AI Synthesis] Gemini generation unsuccessful, serving intelligent fallback.")
    return fallback_generator(prompt)
