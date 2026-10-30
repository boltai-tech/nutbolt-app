import os
import re
import time
import uuid
import shutil
import threading
from collections import defaultdict, deque

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from kernel import (
    CadError,
    MAX_PROMPT_CHARS,
    compile_to_files,
    extract_params_from_code,
    generate_model,
    inject_params,
)

app = FastAPI(title="Nutbolt Fast CAD Kernel")

_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("assets", exist_ok=True)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

SID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,32}$")
ASSET_TTL_S = 30 * 60

RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
_hits = defaultdict(deque)
_hits_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _allowed(request: Request) -> bool:
    ip, now = _client_ip(request), time.monotonic()
    with _hits_lock:
        q = _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT:
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


class GenReq(BaseModel):
    prompt: str


class UpdateReq(BaseModel):
    session_id: str
    code: str
    params: dict


@app.api_route("/", methods=["GET", "HEAD"])
def health():
    return {"status": "online"}


@app.get("/api/health")
def health2():
    return {"status": "online"}


@app.post("/api/analyze-prompt")
@app.post("/api/audit-prompt")
def analyze_prompt(req: GenReq):
    return {"status": "success", "score": 10, "critique": [], "improved_prompt": req.prompt}


@app.post("/api/generate")
def generate(req: GenReq, request: Request):
    if not _allowed(request):
        return JSONResponse(status_code=429, content={"status": "error", "detail": "Too many requests. Wait a few seconds."})
    prompt = (req.prompt or "").strip()[:MAX_PROMPT_CHARS]
    if not prompt:
        return JSONResponse(status_code=400, content={"status": "error", "detail": "Prompt is empty."})
    try:
        _cleanup_assets()
        sid = uuid.uuid4().hex[:8]
        out = generate_model(prompt, sid)
        code = out["code"]
        return {
            "status": "success",
            "session_id": sid,
            "cadquery_code": code,
            "parameters": extract_params_from_code(code),
            "stl_url": f"/assets/{sid}/part.stl",
            "step_url": f"/assets/{sid}/part.step",
            "telemetry": out["telemetry"],
            "source": out["source"],
            "timings": out["timings"],
        }
    except Exception as e:
        print(f"[generate] fatal: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})


@app.post("/api/update-params")
@app.post("/api/recompile")
def update_params(req: UpdateReq, request: Request):
    if not SID_RE.match(req.session_id):
        return JSONResponse(status_code=400, content={"status": "error", "detail": "Invalid session id."})
    if not _allowed(request):
        return JSONResponse(status_code=429, content={"status": "error", "detail": "Too many requests."})
    try:
        new_code = inject_params(req.code, req.params)
        _, _, telemetry = compile_to_files(new_code, req.session_id)
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
        return JSONResponse(status_code=400, content={"status": "error", "detail": f"Those dimensions don't produce a valid solid: {e}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})
