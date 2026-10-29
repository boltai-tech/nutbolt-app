import os
import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from kernel import call_gemini, fallback_generator, compile_to_files, extract_params_from_code, inject_params

app = FastAPI(title="Nutbolt Fast CAD Kernel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("assets", exist_ok=True)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

class GenReq(BaseModel):
    prompt: str

class UpdateReq(BaseModel):
    session_id: str
    code: str
    params: dict

@app.get("/")
def health():
    return {"status": "online"}

@app.options("/{full_path:path}")
async def preflight_handler(full_path: str):
    return JSONResponse(status_code=200, content={"status": "ok"})

@app.post("/api/analyze-prompt")
@app.post("/api/audit-prompt")
async def analyze_prompt(req: GenReq):
    # Returns in 1 millisecond if frontend ever calls it
    return {"status": "success", "score": 10, "critique": [], "improved_prompt": req.prompt}

@app.post("/api/generate")
async def generate(req: GenReq):
    try:
        code = call_gemini(req.prompt)
        sid = str(uuid.uuid4())[:8]
        stl_p, step_p, telemetry = compile_to_files(code, sid)
        
        # If LLM code had a syntax/geometry flaw, compile fallback immediately without second API call
        if stl_p is None:
            code = fallback_generator(req.prompt)
            stl_p, step_p, telemetry = compile_to_files(code, sid)

        params = extract_params_from_code(code)
        return {
            "status": "success",
            "session_id": sid,
            "cadquery_code": code,
            "parameters": params,
            "stl_url": f"/assets/{sid}/part.stl",
            "step_url": f"/assets/{sid}/part.step",
            "telemetry": telemetry
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})

@app.post("/api/update-params")
async def update_params(req: UpdateReq):
    try:
        new_code = inject_params(req.code, req.params)
        stl_p, step_p, telemetry = compile_to_files(new_code, req.session_id)
        if stl_p is None:
            return JSONResponse(status_code=400, content={"status": "error", "detail": "Recompile failed"})
        return {
            "status": "success",
            "session_id": req.session_id,
            "cadquery_code": new_code,
            "stl_url": f"/assets/{req.session_id}/part.stl",
            "step_url": f"/assets/{req.session_id}/part.step",
            "telemetry": telemetry
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})
