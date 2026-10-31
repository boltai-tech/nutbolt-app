"""
nutbolt.ai - FastAPI Production Backend
"""
import os
import uuid
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import kernel

app = FastAPI(title="nutbolt.ai CAD Kernel", version="2.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("assets", exist_ok=True)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

class GenerateRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None

class RecompileRequest(BaseModel):
    session_id: str
    code: str
    params: Dict[str, Any]

class ExportStepRequest(BaseModel):
    session_id: str
    code: str

@app.get("/health")
def health():
    return {"status": "ready", "kernel": "OpenCASCADE 7.7 via CadQuery 2.4.0"}

@app.post("/api/generate")
def generate(req: GenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Empty prompt provided.")

    session_id = req.session_id or str(uuid.uuid4())[:8]
    try:
        output = kernel.generate_model(req.prompt, session_id)
        params = kernel.extract_params_from_code(output["code"])
        return {
            "session_id": session_id,
            "code": output["code"],
            "params": params,
            "telemetry": output["telemetry"],
            "source": output["source"],
            "timings": output["timings"],
            "stl_url": f"/assets/{session_id}/part.stl",
            "step_url": None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/recompile")
def recompile(req: RecompileRequest):
    try:
        updated_code = kernel.inject_params(req.code, req.params)
        _, telemetry = kernel.compile_stl(updated_code, req.session_id)
        timestamp = int(os.path.getmtime(os.path.join("assets", req.session_id, "part.stl")))
        return {
            "session_id": req.session_id,
            "code": updated_code,
            "params": req.params,
            "telemetry": telemetry,
            "stl_url": f"/assets/{req.session_id}/part.stl?t={timestamp}",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Recompile failed: {e}")

@app.post("/api/export-step")
def export_step(req: ExportStepRequest):
    try:
        kernel.compile_step(req.code, req.session_id)
        return {"status": "success", "step_url": f"/assets/{req.session_id}/part.step"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STEP export failed: {e}")
