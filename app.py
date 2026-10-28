import os
import re
import json
import uuid
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import kernel

app = FastAPI(title="NutBolt CAD Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("assets", exist_ok=True)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

sessions = {}

class GenerateRequest(BaseModel):
    prompt: str

class RecompileRequest(BaseModel):
    session_id: str
    params: dict

class AnalyzeRequest(BaseModel):
    prompt: str

@app.get("/")
def health_check():
    return {"status": "ok", "engine": "NutBolt CAD Kernel v2.5"}

@app.post("/api/analyze-prompt")
def analyze_cad_prompt(req: AnalyzeRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return {
            "score": 6,
            "critique": ["Missing GEMINI_API_KEY for dynamic review. Ensure outer diameter, thickness, and mounting details are specified."],
            "improved_prompt": req.prompt
        }

    analysis_instruction = """You are a Senior Mechanical & Parametric CAD Engineer reviewer.
Analyze the user's natural language CAD description for OpenCASCADE / CadQuery compilation viability.

Identify missing engineering parameters:
1. Missing primary outer envelope dimensions (diameter, length, width, thickness).
2. Unspecified bores, keyways, or bolt pitch circle diameters (PCD).
3. Vague adjectives (e.g. "small holes", "medium plate", "normal thickness").
4. Geometric fragmentation risks.

Return STRICT JSON matching this schema:
{
  "score": <integer from 1 to 10>,
  "critique": ["concise bullet 1", "concise bullet 2"],
  "improved_prompt": "A complete, professionally dimensioned rewrite in metric millimeters"
}
Output raw JSON only without markdown formatting."""

    payload = {
        "contents": [{
            "parts": [
                {"text": analysis_instruction},
                {"text": f"User Prompt: {req.prompt}"}
            ]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
    try:
        resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            clean_json = re.sub(r"^```json\s*|^```\s*|```$", "", raw_text.strip(), flags=re.MULTILINE)
            return json.loads(clean_json)
        return {
            "score": 7,
            "critique": ["Model busy during review. Ensure all dimensions include metric units (mm)."],
            "improved_prompt": req.prompt
        }
    except Exception as e:
        return {
            "score": 7,
            "critique": [f"Review skipped: {str(e)}"],
            "improved_prompt": req.prompt
        }

@app.post("/api/generate")
def generate_cad(req: GenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    session_id = str(uuid.uuid4())[:8]
    code_str = kernel.call_gemini(req.prompt)
    
    stl_path, step_path, telemetry = kernel.compile_to_files(code_str, session_id)
    if not stl_path:
        raise HTTPException(status_code=500, detail="OpenCASCADE compilation failed.")
    
    extracted_params = kernel.extract_params_from_code(code_str)
    sessions[session_id] = {
        "code": code_str,
        "params": extracted_params
    }
    
    return {
        "session_id": session_id,
        "stl_url": f"/assets/{session_id}/part.stl",
        "step_url": f"/assets/{session_id}/part.step",
        "params": extracted_params,
        "code": code_str,
        "telemetry": telemetry
    }

@app.post("/api/recompile")
def recompile_cad(req: RecompileRequest):
    sess = sessions.get(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session expired or not found. Please re-generate.")
    
    updated_code = kernel.inject_params(sess["code"], req.params)
    stl_path, step_path, telemetry = kernel.compile_to_files(updated_code, req.session_id)
    
    if not stl_path:
        return {"status": "error", "detail": "Recompilation failed with given parameters."}
    
    sess["params"] = req.params
    sess["code"] = updated_code
    
    return {
        "status": "success",
        "stl_url": f"/assets/{req.session_id}/part.stl",
        "telemetry": telemetry
    }
