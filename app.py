import os
import uuid
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from kernel import call_gemini, audit_gemini, compile_to_files, extract_params_from_code, inject_params

app = FastAPI(title="Nutbolt CAD Engine")

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

class ParamUpdateRequest(BaseModel):
    session_id: str
    code: str
    params: dict

@app.get("/")
def health_check():
    return {"status": "online", "engine": "OpenCASCADE / CadQuery"}

@app.post("/api/generate")
async def generate_solid(req: GenerateRequest):
    code = call_gemini(req.prompt)
    session_id = str(uuid.uuid4())[:8]
    stl_path, step_path, telemetry = compile_to_files(code, session_id)
    params = extract_params_from_code(code)
    
    return {
        "session_id": session_id,
        "cadquery_code": code,
        "parameters": params,
        "stl_url": f"/assets/{session_id}/part.stl",
        "step_url": f"/assets/{session_id}/part.step",
        "telemetry": telemetry
    }

@app.post("/api/update-params")
async def update_params(req: ParamUpdateRequest):
    new_code = inject_params(req.code, req.params)
    stl_path, step_path, telemetry = compile_to_files(new_code, req.session_id)
    return {
        "session_id": req.session_id,
        "cadquery_code": new_code,
        "stl_url": f"/assets/{req.session_id}/part.stl",
        "step_url": f"/assets/{req.session_id}/part.step",
        "telemetry": telemetry
    }

@app.post("/api/analyze-prompt")
@app.post("/api/audit-prompt")
async def audit_endpoint(request: Request):
    try:
        body = await request.json()
        raw_prompt = body.get("prompt", "")
    except Exception:
        raw_prompt = ""

    if not raw_prompt:
        return {"audited_prompt": "Please specify length, width, thickness, and hole diameters."}

    refined = audit_gemini(raw_prompt)
    return {"audited_prompt": refined}
