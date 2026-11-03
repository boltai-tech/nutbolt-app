"""
nutbolt.ai CAD kernel

Tier 1  catalog template  (prompt router, no LLM, deterministic)
Tier 2  Gemini router -> script that may ONLY call the MechanicalBuilder / catalog API
Tier 3  one self-heal call with the exact failure, then a deterministic parametric plate
"""
import ast
import builtins
import math
import os
import re
import threading
import time
import traceback
import types
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import requests
import cadquery as cq
from cadquery import exporters

from cad_builder import ARCHETYPES, BuilderError, MechanicalBuilder
from catalog_templates import (
    CATALOG_FUNCS,
    build_system_prompt,
    match_catalog_template,
    render_script,
)

# --------------------------------------------------------------------------- #
# config (Active Production Models)
# --------------------------------------------------------------------------- #
MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_MODELS", "gemini-2.0-flash,gemini-1.5-flash").split(",")
    if m.strip()
]
GEN_BUDGET_S = float(os.getenv("GEN_BUDGET_S", "8"))
HEAL_BUDGET_S = float(os.getenv("HEAL_BUDGET_S", "6"))
PER_MODEL_S = float(os.getenv("PER_MODEL_S", "4.5"))
HEDGE_S = float(os.getenv("HEDGE_S", "2.5"))
MESH_TOL = float(os.getenv("MESH_TOL", "0.35"))
MESH_ANG = float(os.getenv("MESH_ANG", "0.45"))
MAX_PROMPT_CHARS = 1500
MAX_CODE_CHARS = 6000
MIN_VOLUME_MM3 = 1.0

_COMPILE_LOCK = threading.Lock()
_COOLDOWN = {}
_COOLDOWN_LOCK = threading.Lock()
_SESSION = requests.Session()
_MB = MechanicalBuilder()
_SYSTEM_PROMPT = build_system_prompt()

class CadError(Exception):
    """Unsafe script, builder failure, or invalid topology."""

# --------------------------------------------------------------------------- #
# params <-> script
# --------------------------------------------------------------------------- #
def _find_params_node(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "params":
                    return node
    return None

def extract_params_from_code(code_str):
    try:
        node = _find_params_node(ast.parse(code_str))
        if node is not None:
            val = ast.literal_eval(node.value)
            if isinstance(val, dict):
                return {k: v for k, v in val.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    except Exception:
        pass
    return {}

def inject_params(code_str, new_params):
    old = extract_params_from_code(code_str)
    parts = []
    for k, v in new_params.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,40}", str(k)):
            continue
        try:
            f = float(v)
            if not math.isfinite(f):
                raise ValueError
            keep_int = isinstance(old.get(k), int) and not isinstance(old.get(k), bool) and f.is_integer()
            val = repr(int(f)) if keep_int else repr(f)
        except Exception:
            continue
        parts.append(f"    {k!r}: {val},")
    block = "params = {\n" + "\n".join(parts) + "\n}"
    try:
        node = _find_params_node(ast.parse(code_str))
        if node is not None:
            lines = code_str.split("\n")
            return "\n".join(lines[: node.lineno - 1] + block.split("\n") + lines[node.end_lineno:])
    except Exception:
        pass
    return block + "\n" + code_str

# --------------------------------------------------------------------------- #
# script validation + execution
# --------------------------------------------------------------------------- #
_ALLOWED_FUNCS = {"range", "len", "min", "max", "abs", "round", "float", "int", "sum", "zip", "enumerate", "list", "tuple", "dict", "bool"}
_MATH_OK = {"pi", "e", "tau", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sqrt", "radians", "degrees", "floor", "ceil", "hypot", "fabs"}
_NODE_OK = (
    ast.Module, ast.Assign, ast.Name, ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.BinOp, ast.UnaryOp,
    ast.BoolOp, ast.Compare, ast.IfExp, ast.Subscript, ast.Call, ast.keyword, ast.Attribute, ast.ListComp,
    ast.comprehension, ast.Slice, ast.operator, ast.unaryop, ast.boolop, ast.cmpop, ast.expr_context,
)

def _safe_range(*a):
    r = range(*[int(x) for x in a])
    if len(r) > 256:
        raise CadError("range() too large (max 256 iterations)")
    return r

_SAFE_BUILTINS = {n: getattr(builtins, n) for n in _ALLOWED_FUNCS if n != "range"}
_SAFE_BUILTINS["range"] = _safe_range

def _validate(code_str):
    if len(code_str) > MAX_CODE_CHARS:
        raise CadError("Script is too long.")
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        raise CadError(f"SyntaxError: {e.msg} (line {e.lineno})")

    def _harmless_import(n):
        if isinstance(n, ast.Import):
            return all(a.name.split(".")[0] in ("math", "cadquery") for a in n.names)
        if isinstance(n, ast.ImportFrom):
            return (n.module or "").split(".")[0] in ("math", "cadquery")
        return False

    tree.body = [n for n in tree.body if not _harmless_import(n)]

    for node in ast.walk(tree):
        if not isinstance(node, _NODE_OK):
            raise CadError(f"`{type(node).__name__}` is not allowed.")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and abs(node.value) > 1e6:
                raise CadError("Numeric constant too large.")
            if isinstance(node.value, str) and len(node.value) > 40:
                raise CadError("String constant too long.")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            raise CadError("Dunder names are not allowed.")
        elif isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Pow):
                raise CadError("`**` is not allowed.")
            if isinstance(node.op, ast.Mult) and any(
                isinstance(s, (ast.List, ast.Tuple)) or (isinstance(s, ast.Constant) and isinstance(s.value, str))
                for s in (node.left, node.right)
            ):
                raise CadError("Sequence repetition is not allowed.")
        elif isinstance(node, ast.Assign):
            if not all(isinstance(t, ast.Name) for t in node.targets):
                raise CadError("Only simple `name = value` assignments are allowed.")
        elif isinstance(node, ast.Attribute):
            base = node.value.id if isinstance(node.value, ast.Name) else None
            ok = (
                (base == "mb" and node.attr in ARCHETYPES)
                or (base == "catalog" and node.attr in CATALOG_FUNCS)
                or (base == "math" and node.attr in _MATH_OK)
            )
            if not ok:
                raise CadError(f"`.{node.attr}` is not available.")
        elif isinstance(node, ast.Call):
            if any(k.arg is None for k in node.keywords):
                raise CadError("`**kwargs` are not allowed.")
            f = node.func
            if isinstance(f, ast.Name):
                if f.id not in _ALLOWED_FUNCS:
                    raise CadError(f"Function `{f.id}` is not allowed.")
            elif not isinstance(f, ast.Attribute):
                raise CadError("Unsupported call.")
    return compile(tree, "<part>", "exec")

def build_solid(code_str):
    code_obj = _validate(code_str)
    scope = {
        "__builtins__": _SAFE_BUILTINS,
        "mb": _MB,
        "catalog": types.SimpleNamespace(**CATALOG_FUNCS),
        "math": math,
    }
    try:
        exec(code_obj, scope)
    except BuilderError as e:
        raise CadError(f"Builder: {e}")
    except CadError:
        raise
    except Exception as e:
        tb = " / ".join(traceback.format_exc().strip().splitlines()[-2:])
        raise CadError(f"{type(e).__name__}: {e} | {tb}")

    res = scope.get("result")
    if res is None:
        raise CadError("Script did not assign `result`.")
    if isinstance(res, cq.Shape):
        res = cq.Workplane("XY").newObject([res])
    if not isinstance(res, cq.Workplane):
        raise CadError("`result` must come from an mb.* or catalog.* call.")

    try:
        solids = res.solids().vals()
        if not solids:
            raise CadError("Result contains no solid.")
        if len(solids) > 1:
            raise CadError(f"Result has {len(solids)} DISCONNECTED solids.")
        s = solids[0]
        if s.Volume() <= MIN_VOLUME_MM3:
            raise CadError("Result volume is below 0.001 cm^3.")
        if not s.isValid():
            raise CadError("Result solid is non-manifold.")
    except CadError:
        raise
    except Exception as e:
        raise CadError(f"{type(e).__name__}: {e}")
    return res

# --------------------------------------------------------------------------- #
# compile / export
# --------------------------------------------------------------------------- #
def compile_to_files(code_str, session_id):
    with _COMPILE_LOCK:
        res = build_solid(code_str)
        solid = res.solids().vals()[0]
        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)
        stl_path = os.path.join(out_dir, "part.stl")
        try:
            exporters.export(res, stl_path, exporters.ExportTypes.STL, tolerance=MESH_TOL, angularTolerance=MESH_ANG)
        except Exception as e:
            raise CadError(f"STL export failed: {type(e).__name__}: {e}")
        with open(os.path.join(out_dir, "code.py"), "w", encoding="utf-8") as fh:
            fh.write(code_str)
        bb = solid.BoundingBox()
        vol = solid.Volume()
        return stl_path, {
            "volume_mm3": round(vol, 2),
            "volume_cm3": round(vol / 1000.0, 3),
            "bbox_mm": [round(bb.xlen, 2), round(bb.ylen, 2), round(bb.zlen, 2)],
            "solids": 1,
        }

def export_step(code_str, session_id):
    with _COMPILE_LOCK:
        res = build_solid(code_str)
        out_dir = os.path.join("assets", session_id)
        os.makedirs(out_dir, exist_ok=True)
        step_path = os.path.join(out_dir, "part.step")
        try:
            exporters.export(res, step_path, exporters.ExportTypes.STEP)
        except Exception as e:
            raise CadError(f"STEP export failed: {type(e).__name__}: {e}")
        return step_path

# --------------------------------------------------------------------------- #
# Gemini router
# --------------------------------------------------------------------------- #
def _cooling(model):
    with _COOLDOWN_LOCK:
        return _COOLDOWN.get(model, 0) > time.monotonic()

def _cool(model, seconds):
    if seconds <= 0:
        return
    with _COOLDOWN_LOCK:
        _COOLDOWN[model] = time.monotonic() + seconds

def _clean_code(raw):
    raw = raw.strip()
    m = re.search(r"```(?:python)?\s*(.*?)```", raw, flags=re.DOTALL)
    return (m.group(1) if m else raw).strip()

def _call_model(model, key, user_text, timeout_s):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1500},
    }
    try:
        resp = _SESSION.post(url, headers={"Content-Type": "application/json", "x-goog-api-key": key},
                             json=payload, timeout=(2.0, max(0.5, timeout_s)))
    except requests.RequestException as e:
        print(f"[gemini:{model}] {type(e).__name__}")
        return None, "error"
    if resp.status_code == 200:
        try:
            cand = resp.json()["candidates"][0]
            if cand.get("finishReason") == "MAX_TOKENS":
                return None, "bad"
            text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
            code = _clean_code(text)
            if "result" in code and "params" in code:
                return code, "ok"
        except Exception as e:
            print(f"[gemini:{model}] parse error {e}")
        return None, "bad"
    print(f"[gemini:{model}] HTTP {resp.status_code}: {resp.text[:100]}")
    if resp.status_code == 429:
        return None, "rate"
    if resp.status_code >= 500:
        return None, "busy"
    if resp.status_code == 404:
        return None, "gone"
    return None, "error"

def _route_gemini(user_text, budget_s, trace):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        trace.append("gemini:NO_API_KEY_SET")
        return None, None
    models = [m for m in MODELS if not _cooling(m)]
    if not models:
        trace.append("gemini:all-models-cooling-down")
        return None, None
    deadline = time.monotonic() + budget_s
    ex = ThreadPoolExecutor(max_workers=2)
    pending, state = {}, {"i": 0}

    def launch():
        m = models[state["i"]]
        state["i"] += 1
        t = time.monotonic()
        pending[ex.submit(_call_model, m, key, user_text, min(PER_MODEL_S, max(0.8, deadline - t)))] = (m, t)

    try:
        launch()
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                trace.append("gemini:budget-exceeded")
                break
            done, _ = wait(list(pending), timeout=min(HEDGE_S, remaining), return_when=FIRST_COMPLETED)
            if not done:
                if state["i"] < len(models):
                    launch()
                continue
            for f in done:
                m, t0 = pending.pop(f)
                try:
                    code, status = f.result()
                except Exception as e:
                    code, status = None, "error"
                trace.append(f"{m}:{status}:{int((time.monotonic() - t0) * 1000)}ms")
                if status == "ok":
                    return code, m
                _cool(m, {"rate": 45, "busy": 20, "gone": 3600, "error": 10}.get(status, 0))
                if not pending and state["i"] < len(models):
                    launch()
        return None, None
    finally:
        ex.shutdown(wait=False)

def _route(user_text, budget_s, trace):
    code, model = _route_gemini(user_text, budget_s, trace)
    return code, model

_CACHE = {}
_CACHE_LOCK = threading.Lock()

def call_gemini(prompt, trace):
    key = re.sub(r"\s+", " ", prompt.lower()).strip()[:MAX_PROMPT_CHARS]
    with _CACHE_LOCK:
        if key in _CACHE:
            trace.append("cache-hit")
            return _CACHE[key], "cache"
    code, model = _route("Part request: " + prompt[:MAX_PROMPT_CHARS], GEN_BUDGET_S, trace)
    if code:
        with _CACHE_LOCK:
            if len(_CACHE) >= 200:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[key] = code
    return code, model

def heal_with_gemini(prompt, bad_code, error, trace):
    text = (
        "Part request: " + prompt[:MAX_PROMPT_CHARS]
        + "\n\nYour previous script failed. Return the COMPLETE corrected script (same rules, code only)."
        + f"\nFailure: {error[:700]}\n\nPrevious script:\n{bad_code[:3000]}"
    )
    return _route(text, HEAL_BUDGET_S, trace)

def diagnose():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    out = {"gemini_key_set": bool(key), "models": {}}
    for m in MODELS:
        t = time.monotonic()
        code, status = _call_model(m, key, "Part request: 40 x 40 x 5 plate with a 10 mm center hole", 6.0) if key else (None, "no-key")
        out["models"][m] = {"status": status, "ms": int((time.monotonic() - t) * 1000), "valid_script": bool(code)}
    return out

# --------------------------------------------------------------------------- #
# deterministic fallback
# --------------------------------------------------------------------------- #
def fallback_script(prompt):
    L = W = 60.0
    T = 5.0
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(?:mm)?(?:\s*[x×*]\s*(\d+(?:\.\d+)?))?",
        prompt.lower(),
    )
    if m:
        L = min(max(float(m.group(1)), 10.0), 500.0)
        W = min(max(float(m.group(2)), 10.0), 500.0)
        T = min(max(float(m.group(3)), 1.0), 100.0) if m.group(3) else min(max(min(L, W) * 0.1, 2.0), 20.0)
    s = min(L, W)
    params = {
        "length": round(L, 2), "width": round(W, 2), "thickness": round(T, 2),
        "center_bore": round(s * 0.35, 2), "hole_dia": round(min(max(s * 0.07, 3.0), 8.0), 2),
        "hole_dx": round(L * 0.7, 2), "hole_dy": round(W * 0.7, 2), "corner_radius": round(min(s * 0.08, 8.0), 2),
    }
    lines = ["params = {"] + [f'    "{k}": {v!r},' for k, v in params.items()] + ["}"]
    lines.append(
        'result = mb.prismatic_plate(length=params["length"], width=params["width"], thickness=params["thickness"], '
        'center_bore=params["center_bore"], bolt_pattern={"type": "rect", "dx": params["hole_dx"], "dy": params["hole_dy"], '
        '"dia": params["hole_dia"]}, corner_radius=params["corner_radius"])'
    )
    return "\n".join(lines) + "\n"

# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #
def generate_model(prompt, session_id):
    t0 = time.monotonic()
    timings, trace = {}, []

    def done(code, telemetry, source):
        timings["total_ms"] = int((time.monotonic() - t0) * 1000)
        return {"code": code, "telemetry": telemetry, "source": source, "timings": timings, "trace": trace}

    hit = match_catalog_template(prompt)
    if hit:
        name, prm = hit
        code = render_script(name, prm)
        try:
            _, tele = compile_to_files(code, session_id)
            return done(code, tele, f"catalog:{name}")
        except CadError as e:
            trace.append(f"catalog:{name}:failed:{str(e)[:80]}")

    code, model = call_gemini(prompt, trace)
    timings["llm_ms"] = int((time.monotonic() - t0) * 1000)
    if code:
        try:
            _, tele = compile_to_files(code, session_id)
            return done(code, tele, f"gemini:{model}")
        except CadError as e:
            err = str(e)
            trace.append(f"compile-failed:{err[:120]}")
            t1 = time.monotonic()
            healed, hmodel = heal_with_gemini(prompt, code, err, trace)
            timings["heal_llm_ms"] = int((time.monotonic() - t1) * 1000)
            if healed:
                try:
                    _, tele = compile_to_files(healed, session_id)
                    return done(healed, tele, f"healed:{hmodel}")
                except CadError as e2:
                    trace.append(f"heal-failed:{str(e2)[:120]}")

    print(f"[fallback] {trace}")
    code = fallback_script(prompt)
    _, tele = compile_to_files(code, session_id)
    return done(code, tele, "fallback")
