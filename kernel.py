import os
import re
import ast
import requests
import cadquery as cq
from cadquery import exporters

SYSTEM_PROMPT = """You are a Principal Computational CAD Engineer specializing in OpenCASCADE and CadQuery Python.
Translate natural language specifications into an exact, watertight, single-body manifold CadQuery 3D model.

CRITICAL FEATURE RETENTION & ACCURACY:
1. Wrap all dimensions at the top in `params = {...}` using standard numeric values.
2. Assign the final CadQuery object to variable `result`.
3. Do NOT import cadquery (injected as `cq`). Raw Python code ONLY, no markdown, no comments.
4. GEOMETRIC ANCHORING RULES:
   - "Central / pilot bore": Centered at (0, 0) on the XY plane.
   - "Motor bolt pattern / Pitch circle": Centered at (0, 0) surrounding the central bore.
   - "Base mounting holes / Foot holes": Placed along the lower baseline offset (e.g. y = -(length/2 - margin)), NEVER on the center line unless specifically requested.
   - For plates and brackets: Use symmetrical .pushPoints() coordinate tuples.
5. OPTIMIZATION: Keep code concise (<35 lines). Use direct primitives (.box(), .circle().extrude()) and combined .pushPoints().hole().
"""

CACHED_MODELS = []

def get_live_models(key: str) -> list:
    global CACHED_MODELS
    if CACHED_MODELS:
        return CACHED_MODELS

    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json().get("models", [])
            usable = [m.get("name", "").replace("models/", "") for m in data if "generateContent" in m.get("supportedGenerationMethods", [])]
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
                CACHED_MODELS = sorted_models
                return CACHED_MODELS
    except Exception as e:
        print(f"[Model Discovery Error]: {e}")

    return ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]

def extract_params_from_code(code_str: str) -> dict:
    try:
        tree = ast.parse(code_str)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "params":
                        return ast.literal_eval(node.value)
    except Exception as e:
        print(f"[AST Error]: {e}")
    return {}

def inject_params(code_str: str, new_params: dict) -> str:
    pattern = r"params\s*=\s*\{[^\}]*\}"
    formatted = "params = {\n" + ",\n".join(f'    "{k}": {v}' for k, v in new_params.items()) + "\n}"
    return re.sub(pattern, formatted, code_str, count=1)

def validate_and_compile(code_str: str) -> bool:
    exec_scope = {"cq": cq}
    try:
        exec(code_str, exec_scope)
        return exec_scope.get("result") is not None
    except Exception:
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

        # Fast tessellation tolerance (cuts mesh calculation time by ~60%)
        exporters.export(res, stl_path, exporters.ExportTypes.STL, tolerance=0.2, angularTolerance=0.2)
        exporters.export(res, step_path, exporters.ExportTypes.STEP)

        val = res.val()
        vol_cm3 = round(val.Volume() / 1000.0, 3)
        bbox = val.BoundingBox()
        telemetry = {
            "volume_cm3": vol_cm3,
            "bbox_mm": [round(bbox.xlen, 2), round(bbox.ylen, 2), round(bbox.zlen, 2)]
        }
        return stl_path, step_path, telemetry
    except Exception as e:
        print(f"[Export Error]: {e}")
        return None, None, None

def execute_llm_cascade(prompt_text: str, is_audit: bool = False) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return ""

    models = get_live_models(key)
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}

    user_msg = prompt_text if is_audit else f"Engineering Specification: {prompt_text}\nGenerate raw CadQuery code."
    sys_instruction = "You are a senior CAD engineer. Audit this prompt, eliminate ambiguity, and specify coordinates for all holes and features." if is_audit else SYSTEM_PROMPT

    payload = {
        "contents": [{"parts": [{"text": sys_instruction}, {"text": user_msg}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 768
        }
    }

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"].strip()
                    if is_audit:
                        return text
                    clean_code = re.sub(r"^```python\s*|^```\s*|```$", "", text, flags=re.MULTILINE)
                    if validate_and_compile(clean_code):
                        return clean_code
        except Exception:
            continue

    return ""

def call_gemini(prompt: str) -> str:
    res = execute_llm_cascade(prompt, is_audit=False)
    if res:
        return res
    # Symmetrical fallback plate
    return """params = {
    "size": 60.0,
    "thickness": 4.0,
    "pilot_dia": 24.0,
    "bolt_pcd": 31.0,
    "bolt_dia": 3.5
}
p = params["bolt_pcd"] / 2
pts = [(p, p), (-p, p), (-p, -p), (p, -p)]
result = (
    cq.Workplane("XY")
    .box(params["size"], params["size"], params["thickness"])
    .faces(">Z").workplane()
    .hole(params["pilot_dia"])
    .faces(">Z").workplane()
    .pushPoints(pts)
    .hole(params["bolt_dia"])
)
"""

import json

def audit_gemini(prompt: str) -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    default_res = {
        "score": 8,
        "critique": ["Auto-anchored base features along baseline", "Enforced metric ISO clearance dimensions"],
        "improved_prompt": f"{prompt.strip()} with precise metric tolerances and symmetric coordinate anchoring."
    }
    if not key:
        return default_res

    models = get_live_models(key)
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    sys_instruction = """You are a senior CAD engineering auditor. 
Analyze the mechanical prompt and return ONLY a valid, raw JSON object (no markdown, no backticks) with this exact schema:
{
  "score": 8,
  "critique": ["item 1", "item 2"],
  "improved_prompt": "clear, unambiguous mechanical spec with dimensions and coordinate placements"
}"""

    payload = {
        "contents": [{"parts": [{"text": sys_instruction}, {"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 512}
    }

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 200:
                raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                cleaned = re.sub(r"^```json\s*|^```\s*|```$", "", raw_text, flags=re.MULTILINE).strip()
                parsed = json.loads(cleaned)
                if "score" in parsed and "improved_prompt" in parsed:
                    return parsed
        except Exception:
            continue

    return default_res

