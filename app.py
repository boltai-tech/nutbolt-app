import os
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import cadquery as cq

import kernel

app = FastAPI(title="nutbolt.ai Luxury CAD Studio Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)
app.mount("/assets", StaticFiles(directory=OUTPUTS_DIR), name="assets")

SESSION_STORAGE = {}

class GenerateRequest(BaseModel):
    prompt: str

class RecompileRequest(BaseModel):
    session_id: str
    params: dict

@app.get("/")
def health_check():
    return {"status": "online", "engine": "OpenCASCADE 7.7.0 / CadQuery B-Rep Kernel"}

@app.post("/api/generate")
def generate_cad(req: GenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    session_id = str(uuid.uuid4())[:8]
    session_dir = os.path.join(OUTPUTS_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    
    try:
        code_str = kernel.call_gemini(req.prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI Synthesis Error: {str(e)}")

    try:
        shape, executed_code = kernel.execute_cq(code_str)
        params = kernel.extract_params_from_code(executed_code)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"OpenCASCADE Kernel Compile Error: {str(e)}")

    stl_path = os.path.join(session_dir, "part.stl")
    step_path = os.path.join(session_dir, "part.step")
    try:
        cq.exporters.export(shape, stl_path)
        cq.exporters.export(shape, step_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CAD Exporter Error: {str(e)}")
    
    telemetry = kernel.solve_telemetry(shape)
    SESSION_STORAGE[session_id] = executed_code

    return {
        "session_id": session_id,
        "code": executed_code,
        "params": params,
        "telemetry": telemetry,
        "stl_url": f"/assets/{session_id}/part.stl",
        "step_url": f"/assets/{session_id}/part.step"
    }

@app.post("/api/recompile")
def recompile_cad(req: RecompileRequest):
    saved_code = SESSION_STORAGE.get(req.session_id)
    if not saved_code:
        raise HTTPException(status_code=404, detail="Session expired or not found. Please re-generate.")
    
    session_dir = os.path.join(OUTPUTS_DIR, req.session_id)
    try:
        shape, updated_code = kernel.execute_cq(saved_code, params_override=req.params)
        stl_path = os.path.join(session_dir, "part.stl")
        step_path = os.path.join(session_dir, "part.step")
        cq.exporters.export(shape, stl_path)
        cq.exporters.export(shape, step_path)
        
        telemetry = kernel.solve_telemetry(shape)
        SESSION_STORAGE[req.session_id] = updated_code

        return {
            "status": "success",
            "telemetry": telemetry,
            "stl_url": f"/assets/{req.session_id}/part.stl"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Geometric Recompilation Constraint Violated: {str(e)}")