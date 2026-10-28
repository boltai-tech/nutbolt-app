import os
import re
import ast
import requests
import cadquery as cq

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
   - The output must always remain ONE single connected solid body. Never slice through the core such that geometry breaks into detached fragments.
   - For radial pockets or peripheral scoops (like Geneva wheels, sprockets, or slots), carefully calculate center offsets so cuts only remove material from the outer perimeter, leaving the core intact.
   - Always build from the primary base mass first (e.g. cq.Workplane("XY").circle(r).extrude(h)), add features via .union(), and perform subtractions/holes (.cut()) last.
6. COMPLETE FEATURE COVERAGE:
   - Include every feature mentioned: slots, keyways, clearance bores, ventilation vents, and bolt patterns.
   - Standard central bore & keyway:
     base = base.faces(">Z").workplane().hole(params["bore_dia"])
7. OPENCASCADE STABILITY:
   - Construct geometry strictly via Constructive Solid Geometry (CSG).
   - Avoid zero-thickness tangency cuts and avoid applying edge fillets to boolean intersection seams.
   - Always ensure geometry is manifold, watertight, and valid.
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

def validate_and_compile(code_str: str) -> bool:
    exec_scope = {"cq": cq}
    try:
        exec(code_str, exec_scope)
        res = exec_scope.get("result")
        if res is not None:
            return True
        return False
    except Exception as e:
        print(f"[CadQuery Compilation Error]: {e}")
        return False

def fallback_generator(prompt: str) -> str:
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
        print("[AI Synthesis] No GEMINI_API_KEY found in environment.")
        return fallback_generator(prompt)

    payload = {
        "contents": [{
            "parts": [
                {"text": SYSTEM_PROMPT},
                {"text": f"Engineering Request: {prompt}\nBe meticulous: generate a single connected watertight solid with every specified slot, bore, hole pattern, and cut."}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048
        }
    }

    active_models = [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash"
    ]

    for model in active_models:
        clean_model = model.replace("models/", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={key}"

        for attempt in range(2):
            try:
                resp = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=45
                )

                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        continue
                    text = candidates[0]["content"]["parts"][0]["text"]
                    clean_code = re.sub(r"^```python\s*|^```\s*|```$", "", text.strip(), flags=re.MULTILINE)

                    if validate_and_compile(clean_code):
                        print(f"[AI Synthesis Success] Generated watertight CadQuery via {clean_model}!")
                        return clean_code
                    else:
                        print(f"[{clean_model}] Compiled code validation failed, retrying...")
                elif resp.status_code in (429, 503, 404):
                    print(f"[{clean_model}] Model busy or unavailable (Status {resp.status_code}), falling back...")
                    break
                else:
                    print(f"[{clean_model}] HTTP Error {resp.status_code}: {resp.text}")
                    break
            except Exception as e:
                print(f"[{clean_model}] Network/Timeout Error: {e}")
                break

    print("[AI Synthesis] All models exhausted or busy, serving fallback generator.")
    return fallback_generator(prompt)
