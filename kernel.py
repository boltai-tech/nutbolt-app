"""
nutbolt.ai - Unified CAD Kernel
"""
import os
import re
import ast
import math
import time
import threading
import traceback
from typing import Optional, Tuple, Dict, Any

import requests
import cadquery as cq
from cadquery import exporters

from cad_builder import MechanicalBuilder
from catalog_templates import match_catalog_template

MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-1.5-flash").split(",")
    if m.strip()
]
PER_MODEL_TIMEOUT = 4.0
MAX_PROMPT_CHARS = 1500

_COMPILE_LOCK = threading.Lock()
_SESSION = requests.Session()

class CadError(Exception):
    pass

SYSTEM_PROMPT = """You are a Principal CAD Systems Engineer writing Python scripts using the `MechanicalBuilder` API.
Output ONLY raw, executable Python code. Never use markdown fences (no ```python), no commentary, no imports.
`cq`, `math`, and `MechanicalBuilder` are pre-imported in your execution scope.

RULES:
1. First line MUST declare a flat dictionary: params = {...} with numerical float/int values in millimeters.
2. Build ALL geometry via `MechanicalBuilder` methods:
   - MechanicalBuilder.turned_concentric(...)
   - MechanicalBuilder.profile_extruded(...)
   - MechanicalBuilder.prismatic_plate(...)
   - MechanicalBuilder.shell_enclosure(...)
   - MechanicalBuilder.manifold_block(...)
3. Final statement MUST assign: result = <cq.Workplane>.
4. Keep radial pattern loops <= 12 to maintain sub-second compile speed.
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
    scope = {"cq": cq, "math": math, "MechanicalBuilder": MechanicalBuilder}
    try:
        exec(code_str, scope)
    except Exception as e:
        raise CadError(f"Runtime execution error: {type(e).__name__}: {e}")

    res = scope.get("result")
    if res is None or not isinstance(res, cq.Workplane):
        raise CadError("Script did not assign a valid cq.Workplane to variable `result`.")

    solids = res.solids().vals()
    if not solids:
        raise CadError("OpenCASCADE failed to construct any 3D solid geometry.")
    if len(solids) > 1:
        raise CadError(f"Script produced {len(solids)} disconnected solids. Geometry must be a single solid.")

    val = solids[0]
    if val.Volume() <= 0.001:
        raise CadError("Constructed solid has degenerate non-positive volume.")

    return res

def compile_stl(code_str: str, session_id: str) -> Tuple[str, Dict[str, Any]]:
    with _COMPILE_LOCK:
        res = build_solid(code_str)
        val = res.solids().vals()[0]

        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)
        stl_path = os.path.join(out_dir, "part.stl")

        exporters.export(res, stl_path, exporters.ExportTypes.STL, tolerance=0.35, angularTolerance=0.45)

        bbox = val.BoundingBox()
        vol = val.Volume()
        telemetry = {
            "volume_mm3": round(vol, 2),
            "volume_cm3": round(vol / 1000.0, 3),
            "bbox_mm": [round(bbox.xlen, 2), round(bbox.ylen, 2), round(bbox.zlen, 2)],
            "solids": 1,
        }
        return stl_path, telemetry

def compile_step(code_str: str, session_id: str) -> str:
    with _COMPILE_LOCK:
        res = build_solid(code_str)
        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)
        step_path = os.path.join(out_dir, "part.step")
        exporters.export(res, step_path, exporters.ExportTypes.STEP)
        return step_path

def _call_gemini_raw(prompt_text: str, diagnostic_context: Optional[str] = None) -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None

    contents = [{"role": "user", "parts": [{"text": prompt_text}]}]
    if diagnostic_context:
        contents.append({"role": "model", "parts": [{"text": "Failed during kernel compilation."}]})
        contents.append({"role": "user", "parts": [{"text": f"FIX KERNEL ERROR:\n{diagnostic_context}\nOutput ONLY valid python."}]})

    for model in MODELS:
        url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1000},
        }
        if "2.5" in model:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}

        try:
            resp = _SESSION.post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
                json=payload,
                timeout=(2.0, PER_MODEL_TIMEOUT),
            )
            if resp.status_code == 200:
                parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                clean = re.sub(r"```(?:python)?\s*|```", "", text).strip()
                if "params" in clean and "result" in clean:
                    return clean
        except Exception:
            continue

    return None

def generate_model(prompt: str, session_id: str) -> dict:
    t0 = time.monotonic()
    timings = {}

    # Tier 1: Parametric Macro Catalog
    template_code = match_catalog_template(prompt)
    if template_code:
        try:
            _, telemetry = compile_stl(template_code, session_id)
            timings["total_ms"] = int((time.monotonic() - t0) * 1000)
            return {"code": template_code, "telemetry": telemetry, "source": "parametric_catalog", "timings": timings}
        except Exception as e:
            print(f"[Catalog error]: {e}")

    # Tier 2: LLM Synthesis with MechanicalBuilder
    llm_code = _call_gemini_raw(f"Part Request: {prompt[:MAX_PROMPT_CHARS]}")
    if llm_code:
        try:
            _, telemetry = compile_stl(llm_code, session_id)
            timings["total_ms"] = int((time.monotonic() - t0) * 1000)
            return {"code": llm_code, "telemetry": telemetry, "source": "gemini_few_shot", "timings": timings}
        except Exception as e:
            # Tier 2b: Single-Pass Self-Healing
            healed = _call_gemini_raw(
                f"Part Request: {prompt[:MAX_PROMPT_CHARS]}",
                diagnostic_context=f"Failed Code:\n{llm_code}\n\nError:\n{traceback.format_exc()}"
            )
            if healed:
                try:
                    _, telemetry = compile_stl(healed, session_id)
                    timings["total_ms"] = int((time.monotonic() - t0) * 1000)
                    return {"code": healed, "telemetry": telemetry, "source": "gemini_self_healed", "timings": timings}
                except Exception:
                    pass

    # Tier 3: Deterministic Safe Fallback
    fallback = '''params = {
    "length": 60.0,
    "width": 60.0,
    "thickness": 5.0,
    "center_bore": 20.0,
    "mount_hole": 4.5,
    "hole_spacing": 36.0
}
result = MechanicalBuilder.prismatic_plate(
    length=params["length"],
    width=params["width"],
    thickness=params["thickness"],
    center_bore=params["center_bore"],
    bolt_pattern={"spacing_x": params["hole_spacing"], "spacing_y": params["hole_spacing"], "dia": params["mount_hole"]}
)
'''
    _, telemetry = compile_stl(fallback, session_id)
    timings["total_ms"] = int((time.monotonic() - t0) * 1000)
    return {"code": fallback, "telemetry": telemetry, "source": "fallback", "timings": timings}
