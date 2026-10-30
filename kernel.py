"""
nutbolt.ai CAD kernel.

Pipeline (each distinct piece of code is compiled at most ONCE):
  1. Gemini router (cooldown-aware, tight timeouts) -> CadQuery code
  2. validate (AST allow-list) -> exec -> single-solid check -> export STL + STEP
  3. on failure: ONE self-heal call feeding the exact error back to the LLM
  4. on failure: deterministic parametric fallback (never raises to the user)
"""
import os
import re
import ast
import builtins
import math
import time
import threading
import traceback

import requests
import cadquery as cq
from cadquery import exporters

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
MODELS = [
    m.strip()
    for m in os.getenv(
        "GEMINI_MODELS",
        "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-3.1-flash-lite",
    ).split(",")
    if m.strip()
]
GEN_BUDGET_S = float(os.getenv("GEN_BUDGET_S", "9"))     # total LLM time, first call
HEAL_BUDGET_S = float(os.getenv("HEAL_BUDGET_S", "6"))   # total LLM time, heal call
PER_MODEL_S = float(os.getenv("PER_MODEL_S", "4.5"))     # max wait on one model
MAX_PROMPT_CHARS = 1500

_COMPILE_LOCK = threading.Lock()   # OpenCASCADE is not thread-safe; 0.1 CPU anyway
_COOLDOWN = {}                     # model -> monotonic time until which we skip it
_COOLDOWN_LOCK = threading.Lock()

_SESSION = requests.Session()


class CadError(Exception):
    """Raised when code is unsafe, fails to build, or is not one clean solid."""


SYSTEM_PROMPT = '''You are a Principal CAD Engineer writing CadQuery 2.4 Python scripts.
Output ONLY executable Python code. No markdown fences, no prose, no comments.
`cq` and `math` are already imported. Do not write import statements.

STRUCTURE
1. First statement: params = {...}  (flat dict, plain numeric literals only, millimetres, no expressions).
2. Build the part using only params[...] values.
3. Last statement: result = <cq.Workplane>. The result MUST be ONE connected solid.

NO FLOATING PARTS (most important rule)
- NEVER build a part from several .box()/.cylinder() pieces positioned with .translate()/.moveTo offsets and then union them.
- NEVER use .translate() or .rotate() to assemble pieces.
- Angles, L-brackets, U-channels, T-sections, Z-brackets, stepped profiles:
  draw ONE closed 2D profile with .polyline([...]).close() on Workplane("XZ"), then .extrude(width/2.0, both=True).
  (On "XZ": local x = global X, local y = global Z; both=True centres the part on Y.)
- Plates, spacers, discs, flanges, bushings: ONE .box(...) or .circle(...).extrude(...) (use a second .circle() before extrude for a bore).
- Overlapping pieces are only allowed when they genuinely overlap by at least 1 mm and are combined with .union().

HOLES
- Preferred: explicit cutter cylinders in global coordinates, then .cut():
  cutter = cq.Workplane("XY").workplane(offset=-t).pushPoints([(x, y), ...]).circle(d/2.0).extrude(3.0*t)
  result = body.cut(cutter)
  Vertical holes use Workplane("XY"); holes along X use Workplane("YZ") (local x=Y, local y=Z); holes along Y use Workplane("XZ") (local x=X, local y=Z).
- Alternative: .faces(">Z").workplane().pushPoints([...]).hole(d). Always select ONE unambiguous face (">Z", "<Z", ">X", "<X", ">Y", "<Y").
- Keep every hole at least one diameter away from edges and from other holes.

SANITY
- Wall/plate thickness must be larger than 0. Hole diameters must be smaller than the feature that holds them.
- Use params for every dimension the user specifies. Pick sensible engineering defaults for anything unspecified.

EXAMPLE (L-bracket with two base holes and one wall hole):
params = {"width": 50.0, "base_length": 60.0, "wall_height": 50.0, "thickness": 5.0, "base_hole": 6.0, "wall_hole": 12.0}
t = params["thickness"]
pts = [(0, 0), (params["base_length"], 0), (params["base_length"], t), (t, t), (t, params["wall_height"]), (0, params["wall_height"])]
body = cq.Workplane("XZ").polyline(pts).close().extrude(params["width"] / 2.0, both=True)
base_cut = cq.Workplane("XY").workplane(offset=-t).pushPoints([(params["base_length"] * 0.7, -params["width"] * 0.25), (params["base_length"] * 0.7, params["width"] * 0.25)]).circle(params["base_hole"] / 2.0).extrude(3.0 * t)
wall_cut = cq.Workplane("YZ").workplane(offset=-t).center(0, params["wall_height"] * 0.6).circle(params["wall_hole"] / 2.0).extrude(3.0 * t)
result = body.cut(base_cut).cut(wall_cut)
'''

HEAL_SUFFIX = '''

Your previous script failed. Fix it and return the COMPLETE corrected script (same rules, code only).
Failure reason:
{error}

Previous script:
{code}
'''


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


_BANNED_NAMES = {
    "eval", "exec", "open", "compile", "__import__", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "input", "breakpoint", "os", "sys",
    "subprocess", "importlib", "builtins", "exit", "quit",
}
_BANNED_ATTRS = {"os", "sys", "subprocess", "system", "popen", "importlib", "builtins", "modules"}
_ALLOWED_IMPORTS = {"math", "cadquery"}

_SAFE_BUILTINS = {
    n: getattr(builtins, n)
    for n in (
        "range", "len", "min", "max", "abs", "sum", "float", "int", "round", "enumerate",
        "zip", "list", "tuple", "dict", "pow", "sorted", "reversed", "bool", "str",
        "any", "all", "map", "isinstance", "divmod", "set",
    )
}


def _validate_and_prepare(code_str: str):
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        raise CadError(f"SyntaxError: {e.msg} (line {e.lineno})")

    kept = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) \
                else [(node.module or "").split(".")[0]]
            if not all(n in _ALLOWED_IMPORTS for n in names):
                raise CadError("Only `math` and `cadquery` may be imported.")
            continue
        kept.append(node)
    tree.body = kept

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise CadError("Imports are only allowed at top level.")
        if isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            raise CadError(f"Use of `{node.id}` is not allowed.")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("__") or node.attr in _BANNED_ATTRS):
            raise CadError(f"Access to `.{node.attr}` is not allowed.")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise CadError("global/nonlocal are not allowed.")
    return compile(tree, "<cadquery>", "exec")


def build_solid(code_str: str) -> cq.Workplane:
    code_obj = _validate_and_prepare(code_str)
    scope = {"__builtins__": _SAFE_BUILTINS, "cq": cq, "math": math}
    try:
        exec(code_obj, scope)
    except Exception as e:
        tb_last = traceback.format_exc().strip().splitlines()[-3:]
        raise CadError(f"{type(e).__name__}: {e} | {' / '.join(tb_last)}")

    res = scope.get("result")
    if res is None:
        raise CadError("Script did not assign a final object to `result`.")
    if isinstance(res, cq.Shape):
        res = cq.Workplane("XY").newObject([res])
    if not isinstance(res, cq.Workplane):
        raise CadError("`result` must be a cq.Workplane.")

    try:
        solids = res.solids().vals()
        if not solids:
            raise CadError("Result contains no solid (selection or boolean produced nothing).")
        if len(solids) > 1:
            raise CadError(
                f"Result has {len(solids)} DISCONNECTED solids (floating parts). "
                "Rebuild it as one closed 2D profile extruded, or make pieces overlap and union."
            )
        val = solids[0]
        if val.Volume() <= 0.001:
            raise CadError("Result has zero volume.")
        if not val.isValid():
            raise CadError("Result solid is not valid (self-intersecting or non-manifold).")
    except CadError:
        raise
    except Exception as e:
        raise CadError(f"{type(e).__name__}: {e}")
    return res


def compile_to_files(code_str: str, session_id: str):
    with _COMPILE_LOCK:
        res = build_solid(code_str)
        val = res.solids().vals()[0]

        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)
        stl_path = os.path.join(out_dir, "part.stl")
        step_path = os.path.join(out_dir, "part.step")
        try:
            exporters.export(res, stl_path, exporters.ExportTypes.STL, tolerance=0.15, angularTolerance=0.2)
            exporters.export(res, step_path, exporters.ExportTypes.STEP)
        except Exception as e:
            raise CadError(f"Export failed: {type(e).__name__}: {e}")

        bbox = val.BoundingBox()
        vol = val.Volume()
        telemetry = {
            "volume_mm3": round(vol, 2),
            "volume_cm3": round(vol / 1000.0, 3),
            "bbox_mm": [round(bbox.xlen, 2), round(bbox.ylen, 2), round(bbox.zlen, 2)],
            "solids": 1,
        }
        return stl_path, step_path, telemetry


def _cooling(model: str) -> bool:
    with _COOLDOWN_LOCK:
        return _COOLDOWN.get(model, 0) > time.monotonic()


def _cool(model: str, seconds: float):
    with _COOLDOWN_LOCK:
        _COOLDOWN[model] = time.monotonic() + seconds


def _thinking_config(model: str):
    if "gemini-3" in model:
        return {"thinkingLevel": "minimal"}
    if "2.5" in model:
        return {"thinkingBudget": 128 if "pro" in model else 0}
    return None


def _clean_code(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r"```(?:python)?\s*(.*?)```", raw, flags=re.DOTALL)
    if m:
        raw = m.group(1)
    return raw.strip()


def _call_model(model: str, key: str, user_text: str, timeout_s: float, with_thinking: bool = True):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    gen_cfg = {"temperature": 0.1, "maxOutputTokens": 1800}
    tc = _thinking_config(model) if with_thinking else None
    if tc:
        gen_cfg["thinkingConfig"] = tc
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": gen_cfg,
    }
    try:
        resp = _SESSION.post(
            url,
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            json=payload,
            timeout=(2.0, max(0.5, timeout_s)),
        )
    except requests.RequestException as e:
        print(f"[gemini:{model}] network/timeout: {type(e).__name__}")
        return None, "error"

    if resp.status_code == 200:
        try:
            cand = resp.json()["candidates"][0]
            parts = cand.get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            if cand.get("finishReason") == "MAX_TOKENS":
                print(f"[gemini:{model}] truncated output")
                return None, "bad"
            code = _clean_code(text)
            if "result" in code and "params" in code:
                return code, "ok"
        except Exception as e:
            print(f"[gemini:{model}] parse error: {e}")
        return None, "bad"

    print(f"[gemini:{model}] HTTP {resp.status_code}")
    if resp.status_code == 400 and tc:
        return _call_model(model, key, user_text, timeout_s, with_thinking=False)
    if resp.status_code == 429:
        return None, "rate"
    if resp.status_code in (500, 502, 503, 504):
        return None, "busy"
    if resp.status_code == 404:
        return None, "gone"
    return None, "error"


def _route(user_text: str, budget_s: float):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None, None
    deadline = time.monotonic() + budget_s
    for model in MODELS:
        remaining = deadline - time.monotonic()
        if remaining < 0.8:
            break
        if _cooling(model):
            continue
        code, status = _call_model(model, key, user_text, min(PER_MODEL_S, remaining))
        if status == "ok":
            return code, model
        if status == "rate":
            _cool(model, 45)
        elif status == "busy":
            _cool(model, 20)
        elif status == "gone":
            _cool(model, 3600)
        elif status == "error":
            _cool(model, 10)
    return None, None


def call_gemini(prompt: str):
    return _route("Part request: " + prompt[:MAX_PROMPT_CHARS], GEN_BUDGET_S)


def heal_with_gemini(prompt: str, bad_code: str, error: str):
    text = "Part request: " + prompt[:MAX_PROMPT_CHARS] + HEAL_SUFFIX.format(error=error[:800], code=bad_code[:3000])
    return _route(text, HEAL_BUDGET_S)


def generate_model(prompt: str, session_id: str) -> dict:
    t0 = time.monotonic()
    timings = {}

    code, model = call_gemini(prompt)
    timings["llm_ms"] = int((time.monotonic() - t0) * 1000)

    source = "fallback"
    telemetry = None

    if code:
        t1 = time.monotonic()
        try:
            _, _, telemetry = compile_to_files(code, session_id)
            source = f"gemini:{model}"
        except CadError as e:
            err = str(e)
            print(f"[compile failed -> heal] {err}")
            t2 = time.monotonic()
            healed, hmodel = heal_with_gemini(prompt, code, err)
            timings["heal_llm_ms"] = int((time.monotonic() - t2) * 1000)
            if healed:
                try:
                    _, _, telemetry = compile_to_files(healed, session_id)
                    code, source = healed, f"healed:{hmodel}"
                except CadError as e2:
                    print(f"[heal failed -> fallback] {e2}")
                    telemetry = None
        timings["compile_ms"] = int((time.monotonic() - t1) * 1000)

    if telemetry is None:
        code = fallback_generator(prompt)
        _, _, telemetry = compile_to_files(code, session_id)
        source = "fallback"

    timings["total_ms"] = int((time.monotonic() - t0) * 1000)
    return {"code": code, "telemetry": telemetry, "source": source, "timings": timings}


def fallback_generator(prompt: str) -> str:
    p = prompt.lower()

    if "channel" in p or "u-channel" in p or "u channel" in p:
        return '''params = {
    "width": 80.0,
    "flange_height": 40.0,
    "thickness": 6.0,
    "length": 100.0,
    "hole_dia": 8.0
}
w = params["width"]
h = params["flange_height"]
t = params["thickness"]
pts = [(0, 0), (w, 0), (w, h), (w - t, h), (w - t, t), (t, t), (t, h), (0, h)]
body = cq.Workplane("XZ").polyline(pts).close().extrude(params["length"] / 2.0, both=True)
cut = (
    cq.Workplane("XY").workplane(offset=-t)
    .pushPoints([(w / 2.0, -params["length"] * 0.25), (w / 2.0, params["length"] * 0.25)])
    .circle(params["hole_dia"] / 2.0).extrude(3.0 * t)
)
result = body.cut(cut)
'''

    if "bushing" in p or "spacer" in p or "sleeve" in p:
        return '''params = {
    "outer_dia": 40.0,
    "inner_bore": 16.0,
    "height": 35.0
}
result = (
    cq.Workplane("XY")
    .circle(params["outer_dia"] / 2.0)
    .circle(min(params["inner_bore"], params["outer_dia"] * 0.9) / 2.0)
    .extrude(params["height"])
)
'''

    if "bracket" in p or "l-shape" in p or "l shape" in p or "angle" in p:
        return '''params = {
    "width": 50.0,
    "base_length": 60.0,
    "wall_height": 50.0,
    "thickness": 5.0,
    "base_hole": 6.0,
    "wall_hole": 12.0
}
t = params["thickness"]
pts = [
    (0, 0),
    (params["base_length"], 0),
    (params["base_length"], t),
    (t, t),
    (t, params["wall_height"]),
    (0, params["wall_height"]),
]
body = cq.Workplane("XZ").polyline(pts).close().extrude(params["width"] / 2.0, both=True)
base_cut = (
    cq.Workplane("XY").workplane(offset=-t)
    .pushPoints([
        (params["base_length"] * 0.7, -params["width"] * 0.25),
        (params["base_length"] * 0.7, params["width"] * 0.25),
    ])
    .circle(params["base_hole"] / 2.0).extrude(3.0 * t)
)
wall_cut = (
    cq.Workplane("YZ").workplane(offset=-t)
    .center(0, params["wall_height"] * 0.6)
    .circle(params["wall_hole"] / 2.0).extrude(3.0 * t)
)
result = body.cut(base_cut).cut(wall_cut)
'''

    if "flange" in p or "pipe" in p or "cylinder" in p or "disc" in p or "disk" in p:
        return '''params = {
    "outer_dia": 90.0,
    "bore_dia": 30.0,
    "pcd": 65.0,
    "hole_dia": 8.0,
    "bolt_count": 4,
    "thickness": 8.0
}
n = int(params["bolt_count"])
r = params["pcd"] / 2.0
bolt_pts = [(r * math.cos(2.0 * math.pi * i / n), r * math.sin(2.0 * math.pi * i / n)) for i in range(n)]
t = params["thickness"]
body = cq.Workplane("XY").circle(params["outer_dia"] / 2.0).extrude(t)
bore = cq.Workplane("XY").workplane(offset=-t).circle(params["bore_dia"] / 2.0).extrude(3.0 * t)
holes = cq.Workplane("XY").workplane(offset=-t).pushPoints(bolt_pts).circle(params["hole_dia"] / 2.0).extrude(3.0 * t)
result = body.cut(bore).cut(holes)
'''

    return '''params = {
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
body = cq.Workplane("XY").box(params["width"], params["length"], t, centered=(True, True, False))
bore = cq.Workplane("XY").workplane(offset=-t).circle(params["center_bore"] / 2.0).extrude(3.0 * t)
holes = cq.Workplane("XY").workplane(offset=-t).pushPoints(pts).circle(params["mount_hole"] / 2.0).extrude(3.0 * t)
result = body.cut(bore).cut(holes)
'''
