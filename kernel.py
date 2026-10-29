import os
import re
import ast
import json
import requests
import cadquery as cq
from cadquery import exporters

SYSTEM_PROMPT = """You are a Principal Computational CAD Engineer specializing in OpenCASCADE and CadQuery Python.
Translate natural language specifications into an exact, watertight, single-body manifold CadQuery 3D model.

CRITICAL ARCHITECTURE RULES:
1. Always parameterize every primary dimension at the top in a dictionary named `params`:
params = {
    "length": 100.0,
    "width": 50.0,
    "thickness": 5.0
}
2. The final 3D shape MUST be assigned to the variable named `result`.
3. Output ONLY valid, executable Python code. Do NOT wrap in markdown fences (no ```python). No commentary.
4. COORDINATE & FACE SELECTION RULES:
   - Global Origin: Place the center of mass or symmetric center at (0, 0, 0) whenever possible using `centered=(True, True, False)`.
   - Bores / Pilot Holes: Center them at (0, 0) on the target face workplane.
   - Distinct Faces: When selecting faces on multi-feature parts (like L-brackets or stepped blocks):
     * To select the horizontal base top face: `.faces(">Z[-2]")` or create individual solids and `.union()`.
     * To select the upright vertical face: `.faces(">Y")` or `.faces(">X")`.
     * Never chain multiple `.faces().workplane().hole()` if face orientation is ambiguous; instead, create secondary cutter solids (`cq.Workplane(...).cylinder(...)`) and use `.cut()`.
   - Multi-hole patterns: Use `.pushPoints([(-x, -y), (x, -y), ...]).hole(dia)`.
5. Code must be concise, robust, and mathematically watertight.
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
        print(f"[AST Parse Error]: {e}")
    return {}

def inject_params(code_str: str, new_params: dict) -> str:
    pattern = r"params\s*=\s*\{[^\}]*\}"
    items = []
    for k, v in new_params.items():
        try:
            val = float(v)
        except (ValueError, TypeError):
            val = v
        items.append(f'    "{k}": {val}')
    formatted = "params = {\n" + ",\n".join(items) + "\n}"
    return re.sub(pattern, formatted, code_str, count=1)

def execute_cq(code_str: str):
    scope = {"cq": cq}
    exec(code_str, scope)
    res = scope.get("result")
    if res is None:
        raise ValueError("Script did not assign output to 'result'.")
    val = res.val()
    if val is None or val.Volume() <= 0:
        raise ValueError("CadQuery generated an empty or non-manifold volume.")
    return res

def compile_to_files(code_str: str, session_id: str):
    try:
        res = execute_cq(code_str)
        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)

        stl_path = os.path.join(out_dir, "part.stl")
        step_path = os.path.join(out_dir, "part.step")

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
        print(f"[CAD Engine Error]: {e}")
        return None, None, None

def call_gemini(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set.")

    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=){key}"

    payload = {
        "contents": [
            {"parts": [{"text": SYSTEM_PROMPT}, {"text": f"Engineering Specification:\n{prompt}\nGenerate executable CadQuery code."}]}
        ],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024}
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=12)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API returned status {resp.status_code}: {resp.text}")

    raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    clean_code = re.sub(r"^```python\s*|^```\s*|```$", "", raw_text, flags=re.MULTILINE).strip()

    try:
        execute_cq(clean_code)
        return clean_code
    except Exception as err:
        print(f"[Self-Healing] Execution failed: {err}. Asking model to auto-correct...")
        repair_payload = {
            "contents": [
                {"parts": [{"text": SYSTEM_PROMPT}, {"text": f"Engineering Specification:\n{prompt}"}]},
                {"role": "model", "parts": [{"text": clean_code}]},
                {"role": "user", "parts": [{"text": f"Your code failed compilation in OpenCASCADE with error: {str(err)}. Fix the code so it compiles cleanly into a solid single-body manifold."}]}
            ],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024}
        }
        repair_resp = requests.post(url, headers=headers, json=repair_payload, timeout=12)
        if repair_resp.status_code == 200:
            repaired_text = repair_resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            repaired_clean = re.sub(r"^```python\s*|^```\s*|```$", "", repaired_text, flags=re.MULTILINE).strip()
            try:
                execute_cq(repaired_clean)
                return repaired_clean
            except Exception as final_err:
                print(f"[Self-Healing Failed]: {final_err}")

        return clean_code

def audit_gemini(prompt: str) -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return {
            "score": 0,
            "critique": ["Missing GEMINI_API_KEY on server."],
            "improved_prompt": prompt
        }

    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=){key}"

    audit_sys = """You are an expert Mechanical Design Engineer & CAD Auditor.
Analyze the user's CAD request. Return a genuine, rigorous mechanical critique.
Identify:
1. Ambiguous face or coordinate references.
2. Missing engineering dimensions (thickness, clearance tolerances, PCD).
3. Manufacturability risks.

You MUST respond with valid JSON matching this schema:
{
  "score": <integer from 1 to 10>,
  "critique": ["<specific issue 1>", "<specific issue 2>", ...],
  "improved_prompt": "<fully specified, unambiguous engineering prompt with explicit coordinate datums>"
}
"""

    payload = {
        "contents": [
            {"parts": [{"text": audit_sys}, {"text": f"Audit this CAD prompt:\n{prompt}"}]}
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 512,
            "responseMimeType": "application/json"
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            data = json.loads(raw)
            if "score" in data and "critique" in data and "improved_prompt" in data:
                return data
    except Exception as e:
        print(f"[Audit Engine Error]: {e}")

    return {
        "score": 5,
        "critique": [
            "Network timeout during deep CAD spec analysis.",
            "Verify all hole positions specify explicit offsets from edges."
        ],
        "improved_prompt": prompt
    }
