import os
import re
import shutil
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from kernel import (
    CadError,
    MAX_PROMPT_CHARS,
    compile_to_files,
    export_step,
    extract_params_from_code,
    fallback_script,
    diagnose,
    generate_model,
    inject_params,
)

ASSET_TTL_S = 30 * 60
SID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,32}$")
os.makedirs("assets", exist_ok=True)

def _warmup():
    try:
        compile_to_files(fallback_script("warmup"), "warmup")
        shutil.rmtree(os.path.join("assets", "warmup"), ignore_errors=True)
        print("[warmup] kernel ready")
    except Exception as e:
        print(f"[warmup] skipped: {e}")

@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_warmup, daemon=True).start()
    yield

app = FastAPI(title="Nutbolt CAD Kernel", lifespan=lifespan)

_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

_LIMITS = {
    "generate": int(os.getenv("RATE_GENERATE_PER_MIN", "30")),
    "recompile": int(os.getenv("RATE_RECOMPILE_PER_MIN", "120")),
    "step": int(os.getenv("RATE_STEP_PER_MIN", "30")),
}
_hits = defaultdict(deque)
_hits_lock = threading.Lock()

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")

def _allowed(request: Request, bucket: str) -> bool:
    key, now = (bucket, _client_ip(request)), time.monotonic()
    with _hits_lock:
        q = _hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= _LIMITS[bucket]:
            return False
        q.append(now)
        return True

def _cleanup_assets():
    try:
        now = time.time()
        for name in os.listdir("assets"):
            path = os.path.join("assets", name)
            if os.path.isdir(path) and now - os.path.getmtime(path) > ASSET_TTL_S:
                shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        print(f"[cleanup] {e}")

def _err(status, detail):
    return JSONResponse(status_code=status, content={"status": "error", "detail": detail})

class GenReq(BaseModel):
    prompt: str

class UpdateReq(BaseModel):
    session_id: str
    code: str
    params: dict

class StepReq(BaseModel):
    session_id: str
    code: str

@app.api_route("/", methods=["GET", "HEAD"])
def health():
    return {"status": "online"}

@app.get("/api/health")
def health_api():
    return {"status": "online"}

@app.get("/api/diag")
def diag(request: Request):
    return diagnose()

@app.post("/api/generate")
def generate(req: GenReq, request: Request):
    if not _allowed(request, "generate"):
        return _err(429, "Too many requests. Wait a few seconds.")
    prompt = (req.prompt or "").strip()[:MAX_PROMPT_CHARS]
    if not prompt:
        return _err(400, "Prompt is empty.")
    try:
        _cleanup_assets()
        sid = uuid.uuid4().hex[:8]
        out = generate_model(prompt, sid)
        return {
            "status": "success",
            "session_id": sid,
            "cadquery_code": out["code"],
            "parameters": extract_params_from_code(out["code"]),
            "stl_url": f"/assets/{sid}/part.stl",
            "step_url": f"/assets/{sid}/part.step",
            "telemetry": out["telemetry"],
            "source": out["source"],
            "timings": out["timings"],
            "trace": out["trace"],
        }
    except Exception as e:
        print(f"[generate] fatal: {e}")
        return _err(500, str(e))

@app.post("/api/recompile")
@app.post("/api/update-params")
def recompile(req: UpdateReq, request: Request):
    if not SID_RE.match(req.session_id):
        return _err(400, "Invalid session id.")
    if not _allowed(request, "recompile"):
        return _err(429, "Too many requests.")
    try:
        new_code = inject_params(req.code, req.params)
        _, telemetry = compile_to_files(new_code, req.session_id)
        return {
            "status": "success",
            "session_id": req.session_id,
            "cadquery_code": new_code,
            "parameters": extract_params_from_code(new_code),
            "stl_url": f"/assets/{req.session_id}/part.stl",
            "step_url": f"/assets/{req.session_id}/part.step",
            "telemetry": telemetry,
        }
    except CadError as e:
        return _err(400, f"Those dimensions don't produce a valid solid: {e}")
    except Exception as e:
        return _err(500, str(e))

@app.post("/api/export-step")
def export_step_endpoint(req: StepReq, request: Request):
    if not SID_RE.match(req.session_id):
        return _err(400, "Invalid session id.")
    if not _allowed(request, "step"):
        return _err(429, "Too many requests.")
    try:
        export_step(req.code, req.session_id)
        return {"status": "success", "session_id": req.session_id, "step_url": f"/assets/{req.session_id}/part.step"}
    except CadError as e:
        return _err(400, f"STEP export failed: {e}")
    except Exception as e:
        return _err(500, str(e))
