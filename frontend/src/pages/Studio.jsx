import React, { useState, useRef, useCallback } from "react";
import CadViewport from "../components/CadViewport";
import { Download, Sliders, Code, Weight, RefreshCw, Sparkles, Layers } from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "";

const DENSITIES = {
  steel: { name: "A36 Steel", g_cm3: 7.85, cost_kg: 1.2 },
  aluminum: { name: "6061 Aluminum", g_cm3: 2.7, cost_kg: 4.5 },
  brass: { name: "C360 Brass", g_cm3: 8.5, cost_kg: 8.0 },
  copper: { name: "Pure Copper", g_cm3: 8.96, cost_kg: 9.5 },
};

export default function Studio() {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [stepLoading, setStepLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("params");
  const [material, setMaterial] = useState("steel");
  const [wireframe, setWireframe] = useState(false);

  const [sessionId, setSessionId] = useState(null);
  const [code, setCode] = useState("");
  const [params, setParams] = useState({});
  const [telemetry, setTelemetry] = useState(null);
  const [stlUrl, setStlUrl] = useState(null);
  const [timings, setTimings] = useState(null);

  const debounceTimer = useRef(null);
  const resetViewRef = useRef(null);

  const handleGenerate = async () => {
    if (!prompt.trim() || loading) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Generation failed");

      setSessionId(data.session_id);
      setCode(data.code);
      setParams(data.params || {});
      setTelemetry(data.telemetry);
      setTimings(data.timings);
      setStlUrl(`${API_BASE}${data.stl_url}`);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleParamChange = (k, v) => {
    const updated = { ...params, [k]: parseFloat(v) || v };
    setParams(updated);

    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/recompile`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, code, params: updated }),
        });
        const data = await res.json();
        if (res.ok) {
          setCode(data.code);
          setTelemetry(data.telemetry);
          setStlUrl(`${API_BASE}${data.stl_url}`);
        }
      } catch (err) {
        console.error("Recompile error:", err);
      }
    }, 250);
  };

  const handleDownloadStep = async () => {
    if (!sessionId || !code) return;
    setStepLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/export-step`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, code }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "STEP export failed");

      const link = document.createElement("a");
      link.href = `${API_BASE}${data.step_url}`;
      link.download = `part_${sessionId}.step`;
      link.click();
    } catch (err) {
      alert(err.message);
    } finally {
      setStepLoading(false);
    }
  };

  const cm3 = telemetry?.volume_cm3 || 0;
  const currentDensity = DENSITIES[material] || DENSITIES.steel;
  const massGrams = cm3 * currentDensity.g_cm3;
  const estCost = (massGrams / 1000) * currentDensity.cost_kg;

  return (
    <div className="flex h-screen bg-[#030712] text-slate-100 font-sans overflow-hidden">
      {/* Sidebar Controls */}
      <div className="w-[420px] flex flex-col border-r border-slate-800 bg-slate-950/70 backdrop-blur-md z-10">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
            <h1 className="font-mono font-bold text-base tracking-wider text-slate-200">nutbolt.ai</h1>
          </div>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
            OpenCASCADE 7.7
          </span>
        </div>

        {/* Prompt Input */}
        <div className="p-4 border-b border-slate-800 flex flex-col gap-3">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe mechanical part (e.g. GT2 timing pulley with 20 teeth, 5mm shaft bore, and 7mm belt width)..."
            className="w-full h-24 p-3 rounded-lg bg-slate-900 border border-slate-800 focus:border-cyan-500 focus:outline-none text-xs font-mono resize-none leading-relaxed text-slate-200"
          />
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 font-semibold font-mono text-xs flex items-center justify-center gap-2 transition-all shadow-md shadow-cyan-500/20"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            {loading ? "SYNTHESIZING SOLID..." : "SYNTHESIZE SOLID"}
          </button>
          {timings && (
            <div className="text-[10px] font-mono text-slate-500 text-right">
              Generated in {timings.total_ms}ms
            </div>
          )}
        </div>

        {/* Tab Selection */}
        <div className="flex border-b border-slate-800 text-xs font-mono">
          <button
            onClick={() => setActiveTab("params")}
            className={`flex-1 py-2.5 flex items-center justify-center gap-1.5 border-b-2 transition-colors ${
              activeTab === "params" ? "border-cyan-400 text-cyan-400 bg-slate-900/50" : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Sliders className="w-3.5 h-3.5" /> PARAMETERS
          </button>
          <button
            onClick={() => setActiveTab("code")}
            className={`flex-1 py-2.5 flex items-center justify-center gap-1.5 border-b-2 transition-colors ${
              activeTab === "code" ? "border-cyan-400 text-cyan-400 bg-slate-900/50" : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Code className="w-3.5 h-3.5" /> SCRIPT
          </button>
          <button
            onClick={() => setActiveTab("mass")}
            className={`flex-1 py-2.5 flex items-center justify-center gap-1.5 border-b-2 transition-colors ${
              activeTab === "mass" ? "border-cyan-400 text-cyan-400 bg-slate-900/50" : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Weight className="w-3.5 h-3.5" /> MASS
          </button>
        </div>

        {/* Tab Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === "params" && (
            <div className="flex flex-col gap-4">
              {Object.keys(params).length === 0 ? (
                <div className="text-slate-500 text-xs font-mono text-center py-12">
                  No parameters generated yet.
                </div>
              ) : (
                Object.entries(params).map(([k, v]) => (
                  <div key={k} className="flex flex-col gap-1.5">
                    <div className="flex justify-between text-xs font-mono text-slate-400">
                      <span>{k}</span>
                      <span className="text-cyan-400">{v} mm</span>
                    </div>
                    {typeof v === "number" && (
                      <input
                        type="range"
                        min={Math.max(1, Math.round(v * 0.2))}
                        max={Math.round(v * 2.5)}
                        step="0.5"
                        value={v}
                        onChange={(e) => handleParamChange(k, e.target.value)}
                        className="w-full accent-cyan-400 h-1 bg-slate-800 rounded-lg cursor-pointer"
                      />
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "code" && (
            <pre className="text-[11px] font-mono text-slate-300 bg-slate-900 p-3 rounded-lg overflow-x-auto leading-relaxed border border-slate-800">
              {code || "# Synthesize a solid to inspect CadQuery code"}
            </pre>
          )}

          {activeTab === "mass" && (
            <div className="flex flex-col gap-4 text-xs font-mono">
              <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 flex justify-between">
                <span className="text-slate-400">Displacement Volume:</span>
                <span className="text-cyan-400 font-bold">{cm3} cm?</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 flex justify-between">
                <span className="text-slate-400">Computed Part Mass:</span>
                <span className="text-slate-200 font-bold">{massGrams.toFixed(1)} grams</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 flex justify-between">
                <span className="text-slate-400">Raw Material Cost:</span>
                <span className="text-emerald-400 font-bold">${estCost.toFixed(2)}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 3D Viewport Stage */}
      <div className="flex-1 relative flex flex-col">
        {/* Viewport Top Bar */}
        <div className="absolute top-4 left-4 z-10 flex gap-2">
          {["steel", "aluminum", "brass", "copper"].map((m) => (
            <button
              key={m}
              onClick={() => setMaterial(m)}
              className={`px-3 py-1 rounded text-xs font-mono uppercase tracking-wider transition-all border ${
                material === m ? "border-cyan-400 bg-cyan-950/70 text-cyan-300" : "border-slate-800 bg-slate-900/60 text-slate-400 hover:text-slate-200"
              }`}
            >
              {m}
            </button>
          ))}
          <button
            onClick={() => setWireframe(!wireframe)}
            className={`px-3 py-1 rounded text-xs font-mono transition-all border ${
              wireframe ? "border-cyan-400 bg-cyan-950/70 text-cyan-300" : "border-slate-800 bg-slate-900/60 text-slate-400 hover:text-slate-200"
            }`}
          >
            WIREFRAME
          </button>
        </div>

        {/* Viewport Action Exports */}
        <div className="absolute top-4 right-4 z-10 flex gap-2">
          {stlUrl && (
            <a
              href={stlUrl}
              download="part.stl"
              className="px-4 py-1.5 rounded-lg border border-slate-700 bg-slate-900/80 hover:bg-slate-800 text-slate-200 text-xs font-mono flex items-center gap-1.5 backdrop-blur-md"
            >
              <Download className="w-3.5 h-3.5" /> STL
            </a>
          )}
          {stlUrl && (
            <button
              onClick={handleDownloadStep}
              disabled={stepLoading}
              className="px-4 py-1.5 rounded-lg border border-cyan-500/50 bg-cyan-950/60 hover:bg-cyan-900/70 text-cyan-300 text-xs font-mono flex items-center gap-1.5 backdrop-blur-md"
            >
              {stepLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              {stepLoading ? "COMPILING STEP..." : "STEP (AP214)"}
            </button>
          )}
        </div>

        <CadViewport
          stlUrl={stlUrl}
          materialType={material}
          wireframe={wireframe}
          onResetViewRef={resetViewRef}
        />
      </div>
    </div>
  );
}
