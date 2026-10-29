import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Sparkles, Copy, Check, SlidersHorizontal, Code, Scale, Zap, X, ShieldCheck, SearchCheck, CheckCircle } from "lucide-react";
import CadViewport from "../components/CadViewport.jsx";

const API = "https://nutbolt-backend.onrender.com";
const DENSITY = [
  ["Aluminum 6061-T6", 2.70],
  ["Titanium Grade 5", 4.43],
  ["1018 Cold Rolled Steel", 7.87],
  ["Carbon-Fiber PLA", 1.30]
];

const ICON = { params: SlidersHorizontal, code: Code, mass: Scale };

function highlight(code) {
  const esc = code.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return esc.replace(/(#.*$)|("[^"\n]*"|'[^'\n]*')|\b(import|from|as|def|return|for|in|if|else|True|False|None)\b|\b(\d+\.?\d*)\b/gm,
    (m, c, s, k, n) => (c ? `<span class="c">${m}</span>` : s ? `<span class="s">${m}</span>` : k ? `<span class="k">${m}</span>` : `<span class="n">${m}</span>`));
}

export default function Studio() {
  const [qs] = useSearchParams();
  const [prompt, setPrompt] = useState(qs.get("prompt") || "");
  const [history, setHistory] = useState([]);
  const [tab, setTab] = useState("params");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [m, setM] = useState(null);
  const timer = useRef(null);
  const auto = useRef(false);

  // Credit System
  const [credits, setCredits] = useState(5);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

  // Prompt Auditor
  const [auditing, setAuditing] = useState(false);
  const [auditResult, setAuditResult] = useState(null);

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

  const updateCredits = (newCount) => {
    setCredits(newCount);
    localStorage.setItem("nutbolt_credits", newCount.toString());
  };

  const abs = (u) => (u.startsWith("http") ? u : API + u) + "?t=" + Date.now();

  const auditPrompt = async () => {
    if (!prompt.trim()) return;
    setAuditing(true);
    setErr("");
    try {
      const res = await fetch(`${API}/api/analyze-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt })
      });
      if (!res.ok) throw new Error("Audit service unavailable.");
      const data = await res.json();
      setAuditResult(data);
    } catch (e) {
      setErr(` ${e.message}`);
    }
    setAuditing(false);
  };

  const generate = async (text = prompt) => {
    if (!text.trim()) return;
    if (credits <= 0) {
      setShowUpgradeModal(true);
      return;
    }

    setBusy(true); setErr("");
    try {
      const r = await fetch(`${API}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: text })
      });
      if (!r.ok) {
        const ed = await r.json().catch(() => ({}));
        throw new Error(ed.detail || `Kernel returned ${r.status}`);
      }
      const d = await r.json();
      setM({ ...d, stl: abs(d.stl_url), step: API + d.step_url });
      setHistory((h) => [text, ...h.filter((x) => x !== text)].slice(0, 6));
      updateCredits(credits - 1);
      setAuditResult(null);
    } catch (e) {
      setErr(`${e.message}. Is the FastAPI kernel running at ${API}?`);
    }
    setBusy(false);
  };

  useEffect(() => {
    if (qs.get("prompt") && !auto.current) {
      auto.current = true;
      generate(qs.get("prompt"));
    }
  }, []);

  const handleParamChange = (k, newVal) => {
    const val = Number(newVal);
    if (isNaN(val)) return;
    const params = { ...m.params, [k]: val };
    setM((s) => ({ ...s, params }));
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await fetch(`${API}/api/recompile`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: m.session_id, params })
        });
        const d = await r.json();
        if (d.status === "success") {
          setM((s) => ({ ...s, telemetry: d.telemetry, stl: abs(d.stl_url) }));
        } else {
          setErr("Recompile failed: " + (d.detail || d.status));
        }
      } catch (e) {
        setErr("Recompile error: " + e.message);
      }
    }, 280);
  };

  const copy = async () => {
    await navigator.clipboard.writeText(m.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  const handleSimulatePayment = (addedCredits) => {
    updateCredits(credits + addedCredits);
    setShowUpgradeModal(false);
  };

  const vol = m?.telemetry?.volume_cm3;

  return (
    <div className="studio">
      <aside className="console">
        <header>
          <Link to="/" className="logo">nut<b>bolt</b>.ai</Link>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <button 
              onClick={() => setShowUpgradeModal(true)}
              style={{
                background: credits > 0 ? "rgba(0, 240, 255, 0.1)" : "rgba(255, 75, 75, 0.2)",
                border: credits > 0 ? "1px solid rgba(0, 240, 255, 0.3)" : "1px solid rgba(255, 75, 75, 0.4)",
                color: credits > 0 ? "var(--cyan, #00f0ff)" : "#ff6b6b",
                padding: "3px 8px",
                borderRadius: "12px",
                fontSize: "11px",
                fontWeight: 600,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "4px"
              }}
            >
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

          <div style={{ display: "flex", gap: "6px", margin: "6px 0 10px 0" }}>
            <button
              type="button"
              onClick={auditPrompt} style={{display: "none"}}
              disabled={auditing || busy || !prompt.trim()}
              style={{
                flex: 1,
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                color: "#94a3b8",
                padding: "7px 10px",
                borderRadius: "6px",
                fontSize: "11px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "5px"
              }}
            >
              <SearchCheck size={13} color="#00f0ff" />
              {auditing ? "Analyzing Specs..." : ""}
            </button>
          </div>

          {auditResult && (
            <div style={{
              background: "rgba(10, 15, 28, 0.85)",
              border: "1px solid rgba(0, 240, 255, 0.25)",
              borderRadius: "8px",
              padding: "10px 12px",
              marginBottom: "12px",
              fontSize: "12px"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <span style={{ fontWeight: 600, color: "#00f0ff", fontSize: "11px" }}>CAD SPEC FEASIBILITY</span>
                <span style={{
                  fontWeight: 700,
                  fontSize: "12px",
                  color: auditResult.score >= 8 ? "#22c55e" : auditResult.score >= 5 ? "#f59e0b" : "#ef4444"
                }}>
                  {auditResult.score}/10
                </span>
              </div>

              <ul style={{ margin: "0 0 8px 0", paddingLeft: "14px", color: "#94a3b8", fontSize: "11px", lineHeight: "1.4" }}>
                {auditResult.critique?.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>

              {auditResult.improved_prompt && (
                <div>
                  <div style={{ fontSize: "10px", color: "#64748b", fontWeight: 700, marginBottom: "3px" }}>OPTIMIZED SPEC:</div>
                  <div style={{
                    background: "rgba(0, 0, 0, 0.4)",
                    padding: "6px 8px",
                    borderRadius: "4px",
                    fontFamily: "monospace",
                    fontSize: "11px",
                    color: "#cbd5e1",
                    marginBottom: "8px",
                    maxHeight: "70px",
                    overflowY: "auto"
                  }}>
                    {auditResult.improved_prompt}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setPrompt(auditResult.improved_prompt);
                      setAuditResult(null);
                    }}
                    style={{
                      width: "100%",
                      padding: "6px",
                      borderRadius: "5px",
                      border: "none",
                      background: "rgba(0, 240, 255, 0.2)",
                      color: "#00f0ff",
                      fontWeight: 600,
                      fontSize: "11px",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "5px"
                    }}
                  >
                    <CheckCircle size={12} /> Apply Suggested Spec
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="row">
            <span className="core-chip">OpenCASCADE Core</span>
            <span>Ctrl+Enter to compile</span>
          </div>

          <button 
            className="btn gold" 
            style={{ width: "100%" }} 
            disabled={busy} 
            onClick={() => generate()}
          >
            <Sparkles size={15} />{busy ? "SYNTHESIZING SOLID..." : "SYNTHESIZE SOLID"}
          </button>

          <div className="chips">
            {history.map((h) => (
              <span key={h} className="chip" style={{ cursor: "pointer" }} onClick={() => { setPrompt(h); generate(h); }}>
                {h.slice(0, 28)}{h.length > 28 ? "..." : ""}
              </span>
            ))}
          </div>
          {err && <div className="err">{err}</div>}
        </div>

        <div className="tabs">
          {[["params", "PARAMETERS"], ["code", "CADQUERY"], ["mass", "MASS"]].map(([k, l]) => {
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

          {m && tab === "params" && Object.entries(m.params || {}).map(([k, v]) => {
            if (typeof v !== "number") return null;
            const int = Number.isInteger(v);
            const min = int ? Math.max(1, Math.floor(v * 0.25)) : +(v * 0.25).toFixed(2);
            const max = int ? Math.max(10, Math.ceil(v * 2.5)) : +(v * 2.5).toFixed(2);

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
              <table>
                <thead>
                  <tr><th>Material</th><th>g/cm³</th><th>Mass</th></tr>
                </thead>
                <tbody>
                  {DENSITY.map(([n, d]) => (
                    <tr key={n}>
                      <td style={{ width: "auto" }}>{n}</td>
                      <td className="mono">{d}</td>
                      <td className="mono" style={{ color: "var(--cyan)" }}>
                        {vol != null ? (vol * d).toFixed(1) + " g" : "-"}
                      </td>
                    </tr>
                  ))}
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

      <CadViewport stlUrl={m?.stl} stepUrl={m?.step} busy={busy} />

      {/* Pricing & Upgrade Modal */}
      {showUpgradeModal && (
        <div style={{
          position: "fixed",
          inset: 0,
          backgroundColor: "rgba(5, 7, 15, 0.82)",
          backdropFilter: "blur(8px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 9999,
          padding: "20px"
        }}>
          <div style={{
            background: "#0d111c",
            border: "1px solid rgba(255, 255, 255, 0.12)",
            borderRadius: "16px",
            width: "100%",
            maxWidth: "520px",
            padding: "28px",
            boxShadow: "0 25px 60px rgba(0, 0, 0, 0.6)",
            position: "relative",
            color: "#fff"
          }}>
            <button 
              onClick={() => setShowUpgradeModal(false)}
              style={{
                position: "absolute",
                top: "16px",
                right: "16px",
                background: "transparent",
                border: "none",
                color: "#7e8b9b",
                cursor: "pointer"
              }}
            >
              <X size={20} />
            </button>

            <div style={{ textAlign: "center", marginBottom: "24px" }}>
              <div style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: "48px",
                height: "48px",
                borderRadius: "50%",
                background: "rgba(0, 240, 255, 0.1)",
                color: "#00f0ff",
                marginBottom: "12px"
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
              {/* Pocket Refill */}
              <div style={{
                background: "rgba(255, 255, 255, 0.03)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                borderRadius: "12px",
                padding: "16px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between"
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
                    marginTop: "16px",
                    width: "100%",
                    padding: "10px",
                    borderRadius: "8px",
                    border: "1px solid rgba(255, 255, 255, 0.15)",
                    background: "#182032",
                    color: "#fff",
                    fontWeight: 600,
                    fontSize: "13px",
                    cursor: "pointer"
                  }}
                >
                  Get 25 Credits
                </button>
              </div>

              {/* Maker Monthly */}
              <div style={{
                background: "linear-gradient(180deg, rgba(0, 240, 255, 0.08) 0%, rgba(0, 0, 0, 0.1) 100%)",
                border: "1px solid rgba(0, 240, 255, 0.35)",
                borderRadius: "12px",
                padding: "16px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between"
              }}>
                <div>
                  <span style={{ fontSize: "11px", color: "#00f0ff", fontWeight: 700, letterSpacing: "0.5px" }}>BEST VALUE</span>
                  <h4 style={{ margin: "4px 0 8px 0", fontSize: "16px" }}>Maker Pass</h4>
                  <div style={{ fontSize: "24px", fontWeight: 800, marginBottom: "8px" }}>
                    ₹199 <span style={{ fontSize: "12px", color: "#8a99ad", fontWeight: 400 }}>/ month</span>
                  </div>
                  <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "#cbd5e1", lineHeight: "1.6" }}>
                    <li><b>100 Generations</b> / mo</li>
                    <li>STEP & STL Export</li>
                    <li>Priority Queue</li>
                  </ul>
                </div>
                <button 
                  onClick={() => handleSimulatePayment(100)}
                  style={{
                    marginTop: "16px",
                    width: "100%",
                    padding: "10px",
                    borderRadius: "8px",
                    border: "none",
                    background: "linear-gradient(90deg, #00f0ff 0%, #00a8ff 100%)",
                    color: "#05070f",
                    fontWeight: 700,
                    fontSize: "13px",
                    cursor: "pointer"
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

