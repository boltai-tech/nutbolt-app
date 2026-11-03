import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Sparkles, Copy, Check, SlidersHorizontal, Code, Scale, Zap, X, ShieldCheck } from "lucide-react";
import CadViewport, { MATERIALS as IMPORTED_MATERIALS, MATERIAL_ORDER as IMPORTED_ORDER } from "../components/CadViewport.jsx";

const MATERIALS = IMPORTED_MATERIALS || {
  steel: { name: "A36 Steel", density: 7.85, usdPerKg: 1.20 },
  aluminum: { name: "6061 Aluminum", density: 2.70, usdPerKg: 3.50 },
  brass: { name: "C360 Brass", density: 8.50, usdPerKg: 7.20 },
  copper: { name: "Polished Copper", density: 8.96, usdPerKg: 9.80 }
};
const MATERIAL_ORDER = IMPORTED_ORDER || Object.keys(MATERIALS);

const API = "https://nutbolt-backend.onrender.com";
const FX_FALLBACK_INR = 88.0;

const ICON = { params: SlidersHorizontal, code: Code, mass: Scale };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const abs = (u) => (u.startsWith("http") ? u : API + u) + "?t=" + Date.now();

async function post(path, body, timeoutMs = 150000) {
  const ctl = new AbortController();
  const to = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctl.signal,
    });
    const data = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, data };
  } finally {
    clearTimeout(to);
  }
}

async function saveFile(url, filename) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Download failed (${r.status}).`);
  const blobUrl = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(blobUrl), 4000);
}

function highlight(code) {
  const esc = code.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return esc.replace(
    /(#.*$)|("[^"\n]*"|'[^'\n]*')|\b(import|from|as|def|return|for|in|if|else|True|False|None)\b|\b(\d+\.?\d*)\b/gm,
    (m, c, s, k) => (c ? `<span class="c">${m}</span>` : s ? `<span class="s">${m}</span>` : k ? `<span class="k">${m}</span>` : `<span class="n">${m}</span>`)
  );
}

const toModel = (d) => {
  const params = d.parameters ?? d.params ?? {};
  return {
    session_id: d.session_id,
    code: d.cadquery_code ?? d.code ?? "",
    params,
    base: { ...params },
    telemetry: d.telemetry || null,
    stl: abs(d.stl_url),
    rev: 0,
    stepRev: -1,
    source: d.source || "",
    timings: d.timings || {},
    trace: d.trace || [],
  };
};

const fmtMass = (g) => (g >= 1000 ? `${(g / 1000).toFixed(3)} kg` : `${g.toFixed(1)} g`);
const fmtUsd = (v) => "$" + (v < 1 ? v.toFixed(3) : v.toFixed(2));
const fmtInr = (v) => "₹" + (v < 10 ? v.toFixed(2) : Math.round(v).toLocaleString("en-IN"));

const pill = (on) => ({
  background: on ? "rgba(0, 240, 255, 0.1)" : "rgba(255, 75, 75, 0.2)",
  border: on ? "1px solid rgba(0, 240, 255, 0.3)" : "1px solid rgba(255, 75, 75, 0.4)",
  color: on ? "var(--cyan, #00f0ff)" : "#ff6b6b",
  padding: "3px 8px",
  borderRadius: "12px",
  fontSize: "11px",
  fontWeight: 600,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "4px",
});

export default function Studio() {
  const [qs] = useSearchParams();
  const [prompt, setPrompt] = useState(qs.get("prompt") || "");
  const [history, setHistory] = useState([]);
  const [tab, setTab] = useState("params");
  const [busy, setBusy] = useState(false);
  const [stepBusy, setStepBusy] = useState(false);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);
  const [m, setM] = useState(null);
  const [material, setMaterial] = useState("steel");
  const [fx, setFx] = useState({ rate: FX_FALLBACK_INR, live: false });
  const [credits, setCredits] = useState(5);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

  const timer = useRef(null);
  const auto = useRef(false);
  const mRef = useRef(null);
  mRef.current = m;
  const reqId = useRef(0);
  const lastGood = useRef({});
  const busyRef = useRef(false);

  useEffect(() => {
    const today = new Date().toISOString().slice(0, 10);
    const savedDate = localStorage.getItem("nutbolt_credit_date");
    const savedCredits = localStorage.getItem("nutbolt_credits");
    if (savedDate !== today) {
      localStorage.setItem("nutbolt_credit_date", today);
      localStorage.setItem("nutbolt_credits", "5");
      setCredits(5);
    } else if (savedCredits !== null) {
      setCredits(parseInt(savedCredits, 10));
    }
  }, []);

  useEffect(() => {
    fetch(API + "/", { mode: "no-cors" }).catch(() => {});
  }, []);

  useEffect(() => {
    let dead = false;
    fetch("https://open.er-api.com/v6/latest/USD")
      .then((r) => r.json())
      .then((d) => { if (!dead && d?.rates?.INR) setFx({ rate: d.rates.INR, live: true }); })
      .catch(() => {});
    return () => { dead = true; };
  }, []);

  const updateCredits = (n) => {
    setCredits(n);
    localStorage.setItem("nutbolt_credits", String(n));
  };

  const generate = async (text = prompt) => {
    if (!text.trim() || busyRef.current) return;
    if (credits <= 0) { setShowUpgradeModal(true); return; }

    busyRef.current = true;
    setBusy(true); setErr(""); setNote("");
    const wake = setTimeout(
      () => setNote("Waking the free-tier CAD server - the first request after idle can take up to a minute."),
      7000
    );
    try {
      let res;
      try {
        res = await post("/api/generate", { prompt: text });
      } catch (e) {
        if (e.name === "AbortError") throw new Error("The kernel took too long to respond.");
        await sleep(4000);
        res = await post("/api/generate", { prompt: text });
      }
      if (!res.ok) throw new Error(res.data.detail || `Kernel returned ${res.status}`);
      const model = toModel(res.data);
      lastGood.current = { ...model.params };
      setM(model);
      setHistory((h) => [text, ...h.filter((x) => x !== text)].slice(0, 6));
      updateCredits(credits - 1);
      setNote("");
    } catch (e) {
      setErr(`${e.message || "Request failed."} The kernel at ${API} may still be starting - try again in a few seconds.`);
    } finally {
      clearTimeout(wake);
      busyRef.current = false;
      setBusy(false);
    }
  };

  useEffect(() => {
    if (qs.get("prompt") && !auto.current) {
      auto.current = true;
      generate(qs.get("prompt"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleParamChange = (k, newVal) => {
    const val = Number(newVal);
    if (!Number.isFinite(val) || val <= 0 || !mRef.current) return;
    const params = { ...mRef.current.params, [k]: val };
    setM((s) => ({ ...s, params }));
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const cur = mRef.current;
      if (!cur) return;
      const myReq = ++reqId.current;
      try {
        const { ok, data } = await post("/api/recompile", { session_id: cur.session_id, code: cur.code, params }, 60000);
        if (myReq !== reqId.current) return;
        if (ok && data.status === "success") {
          const next = data.parameters ?? params;
          lastGood.current = { ...next };
          setM((s) => ({ ...s, code: data.cadquery_code, params: next, telemetry: data.telemetry, stl: abs(data.stl_url), rev: s.rev + 1 }));
          setErr("");
        } else {
          setErr(data.detail || "Recompile failed.");
          setM((s) => ({ ...s, params: { ...lastGood.current } }));
        }
      } catch (e) {
        if (myReq !== reqId.current) return;
        setErr("Recompile error: " + (e.message || "network"));
        setM((s) => ({ ...s, params: { ...lastGood.current } }));
      }
    }, 250);
  };

  const downloadStl = async () => {
    if (!mRef.current) return;
    try { await saveFile(mRef.current.stl, "part.stl"); } catch (e) { setErr(e.message); }
  };

  const downloadStep = async () => {
    const cur = mRef.current;
    if (!cur || stepBusy) return;
    setStepBusy(true); setErr("");
    try {
      if (cur.stepRev !== cur.rev) {
        const { ok, data } = await post("/api/export-step", { session_id: cur.session_id, code: cur.code }, 120000);
        if (!ok || data.status !== "success") throw new Error(data.detail || "STEP export failed.");
        setM((s) => (s && s.rev === cur.rev ? { ...s, stepRev: cur.rev } : s));
      }
      await saveFile(`${API}/assets/${cur.session_id}/part.step?t=${Date.now()}`, "part.step");
    } catch (e) {
      setErr(e.message || "STEP export failed.");
    } finally {
      setStepBusy(false);
    }
  };

  const copy = async () => {
    await navigator.clipboard.writeText(m.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  const handleSimulatePayment = (added) => {
    updateCredits(credits + added);
    setShowUpgradeModal(false);
  };

  const vol = m?.telemetry?.volume_cm3;
  const mat = MATERIALS[material];
  const massG = vol != null ? vol * mat.density : null;
  const costUsd = massG != null ? (massG / 1000) * mat.usdPerKg : null;

  const sourceLine = !m ? "" : m.source.startsWith("fallback")
    ? `AI step failed (${(m.trace || []).join(" | ") || "no details"}) - showing a safe template plate sized from your numbers.`
    : m.source.startsWith("catalog:")
      ? `Matched catalog part: ${m.source.slice(8).replace(/_/g, " ")}`
      : m.source.startsWith("healed:")
        ? "Auto-corrected after a geometry check."
        : "";

  return (
    <div className="studio">
      <aside className="console">
        <header>
          <Link to="/" className="logo">nut<b>bolt</b>.ai</Link>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <button onClick={() => setShowUpgradeModal(true)} style={pill(credits > 0)}>
              <Zap size={12} />
              {credits > 0 ? `${credits} Credits Left` : "0 Credits (Refill)"}
            </button>
            <span className={"status" + (busy ? " busy" : "")}>
              <i />{busy ? "COMPILING" : "KERNEL READY"}
            </span>
          </div>
        </header>

        <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--line)" }}>
          <textarea
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe the mechanical part: dimensions, holes, fillets, bolt circles, wall thickness..."
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) generate(); }}
          />

          <div className="row" style={{ marginTop: 8 }}>
            <span className="core-chip">OpenCASCADE Core</span>
            <span>Ctrl+Enter to compile</span>
          </div>

          <button className="btn gold" style={{ width: "100%" }} disabled={busy} onClick={() => generate()}>
            <Sparkles size={15} />{busy ? "SYNTHESIZING SOLID..." : "SYNTHESIZE SOLID"}
          </button>

          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", margin: "10px 0 6px 0" }}>
            <span style={{ fontSize: "11px", color: "#64748b", alignSelf: "center", marginRight: "2px" }}>PRESETS:</span>
            {[
              ["⚙️ 70T Gear Rack (20cm)", "Linear gear rack: 70 teeth, module 0.91, 5mm base height, 15mm width"],
              ["⚙️ 15T Meshing Gear", "Spur gear: 15 teeth, module 0.91, 15mm face height, 5mm shaft bore"],
              ["🔩 GT2 Pulley (20T)", "GT2 timing pulley with 20 teeth, 5mm shaft bore, and 7mm belt width"],
              ["📐 L-Bracket", "L-shaped mounting bracket 50 wide, 60 base, 50 tall, 5 thick, two 6 mm base holes"]
            ].map(([lbl, val]) => (
              <button
                key={lbl}
                type="button"
                style={{
                  background: "rgba(0, 240, 255, 0.08)",
                  border: "1px solid rgba(0, 240, 255, 0.28)",
                  color: "#00f0ff",
                  padding: "3px 8px",
                  borderRadius: "999px",
                  fontSize: "11px",
                  cursor: "pointer"
                }}
                onClick={() => { setPrompt(val); generate(val); }}
              >
                {lbl}
              </button>
            ))}
          </div>

          <div className="chips">
            {history.map((h) => (
              <span key={h} className="chip" style={{ cursor: "pointer" }} onClick={() => { setPrompt(h); generate(h); }}>
                {h.slice(0, 28)}{h.length > 28 ? "..." : ""}
              </span>
            ))}
          </div>
          {note && <div className="row" style={{ marginTop: 8, color: "#f59e0b", fontSize: 11 }}>{note}</div>}
          {err && <div className="err">{err}</div>}
        </div>

        <div className="tabs">
          {[["params", "PARAMETERS"], ["code", "SCRIPT"], ["mass", "MASS"]].map(([k, l]) => {
            const I = ICON[k];
            return (
              <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
                <I size={14} />{l}
              </button>
            );
          })}
        </div>

        <div className="pane">
          {!m && <div className="row">Compile a part to unlock live parametric controls.</div>}

          {m && (sourceLine || m.timings?.total_ms) && tab === "params" && (
            <div className="row" style={{ marginBottom: 10, fontSize: 11, color: m.source.startsWith("fallback") ? "#f59e0b" : "#8a99ad" }}>
              <span>{sourceLine}</span>
              {m.timings?.total_ms ? <span>{(m.timings.total_ms / 1000).toFixed(1)}s</span> : null}
            </div>
          )}

          {m && tab === "params" && Object.entries(m.params || {}).map(([k, v]) => {
            if (typeof v !== "number") return null;
            const b = m.base?.[k] ?? v;
            const int = Number.isInteger(b);
            const min = b > 0 ? (int ? Math.max(1, Math.floor(b * 0.25)) : +(b * 0.25).toFixed(2)) : 0;
            const max = b > 0 ? (int ? Math.max(10, Math.ceil(b * 2.5)) : +(b * 2.5).toFixed(2)) : 10;
            return (
              <div className="param-card" key={k}>
                <div className="param-header">
                  <span className="param-title">{k.replace(/_/g, " ")}</span>
                  <div className="param-input-wrap">
                    <input
                      type="number"
                      className="param-num-input"
                      value={v}
                      step={int ? 1 : 0.1}
                      onChange={(e) => handleParamChange(k, e.target.value)}
                    />
                    <span className="param-unit">mm</span>
                  </div>
                </div>
                <input
                  type="range"
                  min={min}
                  max={max}
                  step={int ? 1 : 0.1}
                  value={v}
                  onChange={(e) => handleParamChange(k, e.target.value)}
                />
              </div>
            );
          })}

          {m && tab === "code" && (
            <>
              <button className="btn" style={{ marginBottom: 10 }} onClick={copy}>
                {copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "COPIED" : "COPY SCRIPT"}
              </button>
              <pre dangerouslySetInnerHTML={{ __html: highlight(m.code) }} />
            </>
          )}

          {m && tab === "mass" && (
            <>
              <div style={{ background: "rgba(0,240,255,0.06)", border: "1px solid rgba(0,240,255,0.25)", borderRadius: 10, padding: "12px 14px", marginBottom: 12 }}>
                <div style={{ fontSize: 11, color: "#8a99ad", fontWeight: 600, letterSpacing: "0.5px" }}>{mat.name.toUpperCase()} · {mat.density} g/cm³</div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 6 }}>
                  <span className="mono" style={{ fontSize: 22, fontWeight: 700, color: "var(--cyan, #00f0ff)" }}>
                    {massG != null ? fmtMass(massG) : "-"}
                  </span>
                  <span className="mono" style={{ fontSize: 14, textAlign: "right" }}>
                    {costUsd != null ? `${fmtUsd(costUsd)} · ${fmtInr(costUsd * fx.rate)}` : "-"}
                  </span>
                </div>
                <div style={{ fontSize: 10, color: "#64748b", marginTop: 6, lineHeight: 1.5 }}>
                  Estimated raw material / filament cost at ${mat.usdPerKg}/kg, 100% solid.
                  {" "}1 USD = ₹{fx.rate.toFixed(2)} ({fx.live ? "live rate" : "approx. rate"}). Prices are rough retail estimates, not a live commodity feed.
                </div>
              </div>

              <table>
                <thead>
                  <tr><th>Material</th><th>g/cm³</th><th>Mass</th><th>USD</th><th>INR</th></tr>
                </thead>
                <tbody>
                  {MATERIAL_ORDER.map((k) => {
                    const mm = MATERIALS[k];
                    const g = vol != null ? vol * mm.density : null;
                    const usd = g != null ? (g / 1000) * mm.usdPerKg : null;
                    return (
                      <tr key={k} onClick={() => setMaterial(k)} style={{ cursor: "pointer", background: k === material ? "rgba(0,240,255,0.08)" : "transparent" }}>
                        <td style={{ width: "auto" }}>{mm.name}</td>
                        <td className="mono">{mm.density}</td>
                        <td className="mono" style={{ color: "var(--cyan)" }}>{g != null ? fmtMass(g) : "-"}</td>
                        <td className="mono">{usd != null ? fmtUsd(usd) : "-"}</td>
                        <td className="mono">{usd != null ? fmtInr(usd * fx.rate) : "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="row" style={{ marginTop: 14 }}>
                <span>Volume: {vol != null ? vol.toFixed(2) : "-"} cm³</span>
                <span>BBox: {m.telemetry?.bbox_mm?.map((x) => x.toFixed(1)).join(" × ") || "-"} mm</span>
              </div>
            </>
          )}
        </div>
      </aside>

      <CadViewport
        stlUrl={m?.stl}
        busy={busy}
        fitKey={m?.session_id}
        material={material}
        onMaterialChange={setMaterial}
        onDownloadStl={downloadStl}
        onDownloadStep={downloadStep}
        stepBusy={stepBusy}
      />

      {showUpgradeModal && (
        <div style={{
          position: "fixed", inset: 0, backgroundColor: "rgba(5, 7, 15, 0.82)", backdropFilter: "blur(8px)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999, padding: "20px",
        }}>
          <div style={{
            background: "#0d111c", border: "1px solid rgba(255, 255, 255, 0.12)", borderRadius: "16px",
            width: "100%", maxWidth: "520px", padding: "28px", boxShadow: "0 25px 60px rgba(0, 0, 0, 0.6)",
            position: "relative", color: "#fff",
          }}>
            <button
              onClick={() => setShowUpgradeModal(false)}
              style={{ position: "absolute", top: "16px", right: "16px", background: "transparent", border: "none", color: "#7e8b9b", cursor: "pointer" }}
            >
              <X size={20} />
            </button>

            <div style={{ textAlign: "center", marginBottom: "24px" }}>
              <div style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center", width: "48px", height: "48px",
                borderRadius: "50%", background: "rgba(0, 240, 255, 0.1)", color: "#00f0ff", marginBottom: "12px",
              }}>
                <Zap size={24} />
              </div>
              <h3 style={{ margin: "0 0 6px 0", fontSize: "20px", fontWeight: 700 }}>
                {credits <= 0 ? "Daily Free Quota Reached" : "Upgrade Your Engine"}
              </h3>
              <p style={{ margin: 0, fontSize: "13px", color: "#8a99ad" }}>
                Keep synthesizing complex parts without interruption.
              </p>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px", marginBottom: "20px" }}>
              <div style={{
                background: "rgba(255, 255, 255, 0.03)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "12px",
                padding: "16px", display: "flex", flexDirection: "column", justifyContent: "space-between",
              }}>
                <div>
                  <span style={{ fontSize: "11px", color: "#8a99ad", fontWeight: 600, letterSpacing: "0.5px" }}>ONE-TIME</span>
                  <h4 style={{ margin: "4px 0 8px 0", fontSize: "16px" }}>Pocket Refill</h4>
                  <div style={{ fontSize: "24px", fontWeight: 800, marginBottom: "8px" }}>
                    ₹99 <span style={{ fontSize: "12px", color: "#8a99ad", fontWeight: 400 }}>($1.29)</span>
                  </div>
                  <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "#cbd5e1", lineHeight: "1.6" }}>
                    <li><b>25 Credits</b></li>
                    <li>Never expires</li>
                    <li>Standard STL Export</li>
                  </ul>
                </div>
                <button
                  onClick={() => handleSimulatePayment(25)}
                  style={{
                    marginTop: "16px", width: "100%", padding: "10px", borderRadius: "8px",
                    border: "1px solid rgba(255, 255, 255, 0.15)", background: "#182032", color: "#fff",
                    fontWeight: 600, fontSize: "13px", cursor: "pointer",
                  }}
                >
                  Get 25 Credits
                </button>
              </div>

              <div style={{
                background: "linear-gradient(180deg, rgba(0, 240, 255, 0.08) 0%, rgba(0, 0, 0, 0.1) 100%)",
                border: "1px solid rgba(0, 240, 255, 0.35)", borderRadius: "12px", padding: "16px",
                display: "flex", flexDirection: "column", justifyContent: "space-between",
              }}>
                <div>
                  <span style={{ fontSize: "11px", color: "#00f0ff", fontWeight: 700, letterSpacing: "0.5px" }}>BEST VALUE</span>
                  <h4 style={{ margin: "4px 0 8px 0", fontSize: "16px" }}>Maker Pass</h4>
                  <div style={{ fontSize: "24px", fontWeight: 800, marginBottom: "8px" }}>
                    ₹199 <span style={{ fontSize: "12px", color: "#8a99ad", fontWeight: 400 }}>/ month</span>
                  </div>
                  <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "#cbd5e1", lineHeight: "1.6" }}>
                    <li><b>100 Generations</b> / mo</li>
                    <li>STEP &amp; STL Export</li>
                    <li>Priority Queue</li>
                  </ul>
                </div>
                <button
                  onClick={() => handleSimulatePayment(100)}
                  style={{
                    marginTop: "16px", width: "100%", padding: "10px", borderRadius: "8px", border: "none",
                    background: "linear-gradient(90deg, #00f0ff 0%, #00a8ff 100%)", color: "#05070f",
                    fontWeight: 700, fontSize: "13px", cursor: "pointer",
                  }}
                >
                  Upgrade to Pass
                </button>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", fontSize: "11px", color: "#7e8b9b" }}>
              <ShieldCheck size={14} color="#00f0ff" />
              <span>Instant activation via UPI, Cards, or Netbanking</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}



