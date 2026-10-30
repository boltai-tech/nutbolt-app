"""
nutbolt.ai CAD kernel - Modular Catalog & Few-Shot LLM Engine
"""
import os
import re
import ast
import builtins
import math
import time
import threading

import requests
import cadquery as cq
from cadquery import exporters

from catalog import match_catalog_template

MODELS = [
    m.strip()
    for m in os.getenv(
        "GEMINI_MODELS",
        "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-1.5-flash",
    ).split(",")
    if m.strip()
]
PER_MODEL_S = 4.0
MAX_PROMPT_CHARS = 1500

_COMPILE_LOCK = threading.Lock()
_SESSION = requests.Session()


class CadError(Exception):
    pass


SYSTEM_PROMPT = """You are a Principal CAD Engineer writing CadQuery 2.4 Python scripts.
Output ONLY executable Python code. No markdown fences, no prose, no comments.
`cq` and `math` are already imported. Do not write import statements.

RULES:
1. First statement: params = {...} (flat dict, numeric values only, in mm).
2. Final assignment must be result = <cq.Workplane>. Must be ONE single solid.
3. FOR RADIAL CUTS: Loop a MAXIMUM of 8 to 12 cuts. High-density loops (>12) crash OpenCASCADE.
4. NO FLOATING SOLIDS: Overlap pieces by at least 1mm or extrude from single profiles.
"""


def _find_params_node(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "params":
                    return node
    return None


def extract_params_from_code(code_str: str) -> dict:
    try:
        node = _find_params_node(ast.parse(code_str))
        if node is not None:
            val = ast.literal_eval(node.value)
            if isinstance(val, dict):
                return val
    except Exception:
        pass
    return {}


def inject_params(code_str: str, new_params: dict) -> str:
    old = extract_params_from_code(code_str)
    parts = []
    for k, v in new_params.items():
        try:
            f = float(v)
            if isinstance(old.get(k), int) and not isinstance(old.get(k), bool) and f.is_integer():
                val = repr(int(f))
            else:
                val = repr(f)
        except Exception:
            val = repr(v)
        parts.append(f"    {k!r}: {val},")
    block = "params = {\n" + "\n".join(parts) + "\n}"

    try:
        node = _find_params_node(ast.parse(code_str))
        if node is not None:
            lines = code_str.split("\n")
            start, end = node.lineno - 1, node.end_lineno
            return "\n".join(lines[:start] + block.split("\n") + lines[end:])
    except Exception:
        pass
    return block + "\n" + code_str


def build_solid(code_str: str) -> cq.Workplane:
    scope = {"cq": cq, "math": math}
    try:
        exec(code_str, scope)
    except Exception as e:
        raise CadError(f"{type(e).__name__}: {e}")

    res = scope.get("result")
    if res is None or not isinstance(res, cq.Workplane):
        raise CadError("Script did not assign a cq.Workplane to `result`.")

    solids = res.solids().vals()
    if not solids or len(solids) > 1 or solids[0].Volume() <= 0.001:
        raise CadError("Invalid solid geometry generated.")

    return res


def compile_to_files(code_str: str, session_id: str):
    with _COMPILE_LOCK:
        res = build_solid(code_str)
        val = res.solids().vals()[0]

        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)
        stl_path = os.path.join(out_dir, "part.stl")
        step_path = os.path.join(out_dir, "part.step")

        # Fast free-tier meshing: 0.8s build
        exporters.export(res, stl_path, exporters.ExportTypes.STL, tolerance=0.35, angularTolerance=0.4)
        exporters.export(res, step_path, exporters.ExportTypes.STEP)

        bbox = val.BoundingBox()
        vol = val.Volume()
        telemetry = {
            "volume_mm3": round(vol, 2),
            "volume_cm3": round(vol / 1000.0, 3),
            "bbox_mm": [round(bbox.xlen, 2), round(bbox.ylen, 2), round(bbox.zlen, 2)],
            "solids": 1,
        }
        return stl_path, step_path, telemetry


def _call_gemini(user_text: str):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None

    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1200},
        }
        if "2.5" in model:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}

        try:
            resp = _SESSION.post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
                json=payload,
                timeout=(2.0, PER_MODEL_S),
            )
            if resp.status_code == 200:
                parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                clean = re.sub(r"```(?:python)?\s*|```", "", text).strip()
                if "result" in clean and "params" in clean:
                    return clean
        except Exception:
            continue

    return None


def generate_model(prompt: str, session_id: str) -> dict:
    t0 = time.monotonic()
    timings = {}

    # Tier 1: Check Modular Parametric Catalog (Instant 100% Geometry)
    template_code = match_catalog_template(prompt)
    if template_code:
        try:
            _, _, telemetry = compile_to_files(template_code, session_id)
            timings["total_ms"] = int((time.monotonic() - t0) * 1000)
            return {
                "code": template_code,
                "telemetry": telemetry,
                "source": "parametric_catalog",
                "timings": timings,
            }
        except Exception as e:
            print(f"[catalog error]: {e}")

    # Tier 2: LLM Router for Custom Shapes
    llm_code = _call_gemini("Part description: " + prompt[:MAX_PROMPT_CHARS])
    if llm_code:
        try:
            _, _, telemetry = compile_to_files(llm_code, session_id)
            timings["total_ms"] = int((time.monotonic() - t0) * 1000)
            return {
                "code": llm_code,
                "telemetry": telemetry,
                "source": "gemini_few_shot",
                "timings": timings,
            }
        except Exception as e:
            print(f"[llm error]: {e}")

    # Tier 3: Deterministic Base Plate Fallback
    fallback = '''params = {
    "width": 60.0,
    "length": 60.0,
    "thickness": 5.0,
    "center_bore": 22.0,
    "mount_hole": 3.5,
    "hole_spacing": 31.0
}
s = params["hole_spacing"] / 2.0
t = params["thickness"]
pts = [(-s, -s), (s, -s), (s, s), (-s, s)]
body = cq.Workplane("XY").box(params["width"], params["length"], t)
bore = cq.Workplane("XY").workplane(offset=-t).circle(params["center_bore"] / 2.0).extrude(3.0 * t)
holes = cq.Workplane("XY").workplane(offset=-t).pushPoints(pts).circle(params["mount_hole"] / 2.0).extrude(3.0 * t)
result = body.cut(bore).cut(holes)
'''
    _, _, telemetry = compile_to_files(fallback, session_id)
    timings["total_ms"] = int((time.monotonic() - t0) * 1000)
    return {
        "code": fallback,
        "telemetry": telemetry,
        "source": "fallback",
        "timings": timings,
    }
