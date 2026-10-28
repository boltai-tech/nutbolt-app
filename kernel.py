import os
import re
import ast
import requests
import cadquery as cq
from cadquery import exporters

SYSTEM_PROMPT = """You are a Principal Computational CAD & Mechanical Design Engineer specializing in OpenCASCADE and CadQuery Python.
Translate natural language specifications into a valid, watertight, single-body manifold CadQuery 3D model.

CRITICAL FEATURE RETENTION:
1. Wrap all key dimensions at the very top in a dictionary named `params`.
2. Assign the final CadQuery object to a variable named `result`.
3. Do NOT import cadquery (it is pre-injected in runtime execution scope as `cq`).
4. Output ONLY raw executable Python code. No markdown fences, no conversational commentary.
5. SINGLE SOLID CONTINUITY:
   - Must remain ONE single connected solid body.
   - Build base first, union secondary features, cut/hole last.
"""

# Cached models verified dynamically from Google API
CACHED_MODELS = []

def get_live_models(key: str) -> list:
    global CACHED_MODELS
    if CACHED_MODELS:
        return CACHED_MODELS

    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("models", [])
            # Filter models that support content generation
            usable = []
            for m in data:
                methods = m.get("supportedGenerationMethods", [])
                name = m.get("name", "").replace("models/", "")
                if "generateContent" in methods:
                    usable.append(name)

            # Prioritize Flash models, then general models
            priority = ["3.8-flash", "3.6-flash", "3.5-flash-lite", "3.1-flash-lite", "flash"]
            sorted_models = []
            for p in priority:
                for u in usable:
                    if p in u and u not in sorted_models:
                        sorted_models.append(u)
            for u in usable:
                if u not in sorted_models:
                    sorted_models.append(u)

            if sorted_models:
                print(f"[Dynamic Model Discovery] Found {len(sorted_models)} active models: {sorted_models[:4]}")
                CACHED_MODELS = sorted_models
                return CACHED_MODELS
    except Exception as e:
        print(f"[Dynamic Model Discovery Error]: {e}")

    # Fallback to standard 2026 active endpoints if discovery fails
    return ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

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
    if "geneva" in p:
        return """params = {
    "outer_dia": 70.0,
    "thickness": 6.0,
    "bore_dia": 8.0,
    "slot_w": 4.0,
    "slot_len": 22.0
}
wheel = cq.Workplane("XY").circle(params["outer_dia"] / 2).extrude(params["thickness"])
wheel = wheel.faces(">Z").workplane().hole(params["bore_dia"])
for angle in [0, 90, 180, 270]:
    slot = cq.Workplane("XY").rect(params["slot_w"], params["slot_len"]).extrude(params["thickness"]).translate((0, (params["outer_dia"]/2) - (params["slot_len"]/2), 0)).rotate((0,0,0), (0,0,1), angle)
    wheel = wheel.cut(slot)
result = wheel
"""
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
    return """params = {
    "outer_dia": 60.0,
    "thickness": 8.0,
    "bore_dia": 10.0
}
base = cq.Workplane("XY").circle(params["outer_dia"] / 2).extrude(params["thickness"])
result = base.faces(">Z").workplane().hole(params["bore_dia"])
"""

def execute_llm_cascade(prompt_text: str, is_audit: bool = False) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        print("[AI Engine] GEMINI_API_KEY environment variable is missing.")
        return "" if is_audit else fallback_generator(prompt_text)

    models = get_live_models(key)
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}

    user_msg = prompt_text if is_audit else f"Engineering Request: {prompt_text}\nOutput raw executable CadQuery Python code only."
    sys_instruction = "You are a senior CAD engineer. Audit this user prompt and output a refined, precise technical specification with dimensions." if is_audit else SYSTEM_PROMPT

    payload = {
        "contents": [{
            "parts": [
                {"text": sys_instruction},
                {"text": user_msg}
            ]
        }],
        "generationConfig": {
            "temperature": 0.2 if is_audit else 0.1,
            "maxOutputTokens": 1024 if is_audit else 2048
        }
    }

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"].strip()
                    if is_audit:
                        print(f"[Audit Success] Using model {model}")
                        return text
                    clean_code = re.sub(r"^```python\s*|^```\s*|```$", "", text, flags=re.MULTILINE)
                    if validate_and_compile(clean_code):
                        print(f"[Synthesis Success] Generated solid via model {model}")
                        return clean_code
            else:
                print(f"[{model}] Status {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"[{model}] Request failed: {e}")

    return "" if is_audit else fallback_generator(prompt_text)

def call_gemini(prompt: str) -> str:
    return execute_llm_cascade(prompt, is_audit=False)

def audit_gemini(prompt: str) -> str:
    res = execute_llm_cascade(prompt, is_audit=True)
    return res if res else f"Refined specification: {prompt} with precision tolerances and standard fillets."
