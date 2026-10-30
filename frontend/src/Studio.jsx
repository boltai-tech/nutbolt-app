import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Sparkles,
  Copy,
  Check,
  SlidersHorizontal,
  Code,
  Scale,
  Zap,
  X,
  ShieldCheck
} from "lucide-react";
import CadViewport from "./components/CadViewport.jsx";

const API = import.meta.env.VITE_API_URL || "https://YOUR_RENDER_URL";

export const MATERIALS = {
  steel: {
    name: "A36 Steel",
    density: 7.85,
    color: "#686d76",
    metalness: 0.95,
    roughness: 0.28,
    usdPerGram: 0.003,
    inrPerGram: 0.25
  },
  aluminum: {
    name: "6061 Aluminum",
    density: 2.7,
    color: "#d2d7df",
    metalness: 0.9,
    roughness: 0.2,
    usdPerGram: 0.008,
    inrPerGram: 0.67
  },
  brass: {
    name: "C360 Brass",
    density: 8.5,
    color: "#d9a536",
    metalness: 0.92,
    roughness: 0.22,
    usdPerGram: 0.015,
    inrPerGram: 1.26
  },
  copper: {
    name: "Polished Copper",
    density: 8.96,
    color: "#b85d38",
    metalness: 0.95,
    roughness: 0.25,
    usdPerGram: 0.02,
    inrPerGram: 1.68
  },
  pla: {
    name: "PLA Plastic",
    density: 1.24,
    color: "#38bdf8",
    metalness: 0.05,
    roughness: 0.75,
    usdPerGram: 0.025,
    inrPerGram: 2.1
  },
  abs: {
    name: "ABS Plastic",
    density: 1.04,
    color: "#f97316",
    metalness: 0.05,
    roughness: 0.55,
    usdPerGram: 0.028,
    inrPerGram: 2.35
  },
  petg: {
    name: "PETG / Tough Resin",
    density: 1.27,
    color: "#10b981",
    metalness: 0.1,
    roughness: 0.35,
    usdPerGram: 0.03,
    inrPerGram: 2.52
  }
};

const ICON = { params: SlidersHorizontal, code: Code, mass: Scale };

function highlight(code) {
  const esc = code
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return esc.replace(
    /(#.*$)|("[^"\n]*"|'[^'\n]*')|\b(import|from|as|def|return|for|in|if|else|True|False|None)\b|\b(\d+\.?\d*)\b/gm,
    (m, c, s, k, n) =>
      c
        ? `<span class="c">${m}</span>`
        : s
          ? `<span class="s">${m}</span>`
          : k
            ? `<span class="k">${m}</span>`
            : `<span class="n">${m}</span>`
  );
}

const formatMass = (grams) => {
  if (grams == null || Number.isNaN(grams)) return "-";
  if (grams < 1000) return `${grams.toFixed(grams >= 100 ? 1 : 2)} g`;
  return `${(grams / 1000).toFixed(2)} kg`;
};

const formatMoney = (value) => Number.isFinite(value) ? `${value.toFixed(2)}` : "0.00";

export default function Studio() {
  const [qs] = useSearchParams();
  const [prompt, setPrompt] = useState(qs.get("prompt") || "");
  const [history, setHistory] = useState([]);
  const [tab, setTab] = useState("params");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [m, setM] = useState(null);
  const [selectedMaterial, setSelectedMaterial] = useState("steel");
  const timer = useRef(null);
  const auto = useRef(false);

  const [credits, setCredits] = useState(5);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

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

  const generate = async (text = prompt) => {
    if (!text.trim()) return;

    if (credits <= 0) {
      setShowUpgradeModal(true);
      return;
    }

    setBusy(true);
    setErr("");

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
      setM({
        ...d,
        stl: abs(d.stl_url),
        step: API + d.step_url
      });

      setHistory((h) => [text, ...h.filter((x) => x !== text)].slice(0, 6));
      updateCredits(credits - 1);
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
    if (isNaN(val) || !m?.session_id || !m?.params) return;

    const params = { ...m.params, [k]: val };
    setM((s) => ({ ...s, params }));

    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await fetch(`${API}/api/recompile`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: m.session_id,
            code: m.cadquery_code || m.code,
            params
          })
        });

        const d = await r.json();
        if (d.status === "success") {
          setM((s) => ({
            ...s,
            telemetry: d.telemetry,
            stl: abs(d.stl_url),
            step: API + d.step_url
          }));
        } else {
          setErr("Recompile failed: " + (d.detail || d.status));
        }
      } catch (e) {
        setErr("Recompile error: " + e.message);
      }
    }, 280);
  };

  const copy = async () => {
    if (!m?.code && !m?.cadquery_code) return;
    await navigator.clipboard.writeText(m.code || m.cadquery_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  const handleSimulatePayment = (addedCredits) => {
    updateCredits(credits + addedCredits);
    setShowUpgradeModal(false);
  };

  const volumeCm3 = Number(m?.telemetry?.volume_cm3 ?? 0);
  const activeMaterial = MATERIALS[selectedMaterial] || MATERIALS.steel;
  const partMassGrams = volumeCm3 > 0 ? volumeCm3 * activeMaterial.density : 0;
  const estCostUsd = partMassGrams * activeMaterial.usdPerGram;
  const estCostInr = partMassGrams * activeMaterial.inrPerGram;

  const materialRows = useMemo(
    () =>
      Object.entries(MATERIALS).map(([key, mat]) => {
        const value = volumeCm3 > 0 ? volumeCm3 * mat.density : 0;
        return {
          key,
          name: mat.name,
          density: mat.density,
          mass: value
        };
      }),
    [volumeCm3]
  );

  return (
    <div className="studio">
      <aside className="console">
        <header>
          <Link to="/" className="logo">
            nut<b>bolt</b>.ai
          </Link>

          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <button
              onClick={() => setShowUpgradeModal(true)}
              style={{
                background:
                  credits > 0
                    ? "rgba(0, 240, 255, 0.1)"
                    : "rgba(255, 75, 75, 0.2)",
                border:
                  credits > 0
                    ? "1px solid rgba(0, 240, 255, 0.3)"
                    : "1px solid rgba(255, 75, 75, 0.4)",
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
              <i />
              {busy ? "COMPILING" : "KERNEL READY"}
            </span>
          </div>
        </header>

        <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--line)" }}>
          <textarea
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe the mechanical part: dimensions, holes, fillets, bolt circles, wall thickness..."
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) generate();
            }}
          />

          <div className="row" style={{ marginTop: "10px" }}>
            <span className="core-chip">OpenCASCADE Core</span>
            <span>Ctrl+Enter to compile</span>
          </div>

          <button
            className="btn gold"
            style={{ width: "100%" }}
            disabled={busy}
            onClick={() => generate()}
          >
            <Sparkles size={15} />
            {busy ? "SYNTHESIZING SOLID..." : "SYNTHESIZE SOLID"}
          </button>

          <div className="chips">
            {history.map((h) => (
              <span
                key={h}
                className="chip"
                style={{ cursor: "pointer" }}
                onClick={() => {
                  setPrompt(h);
                  generate(h);
                }}
              >
                {h.slice(0, 28)}
                {h.length > 28 ? "..." : ""}
              </span>
            ))}
          </div>

          {err && <div className="err">{err}</div>}
        </div>

        <div className="tabs">
          {[
            ["params", "PARAMETERS"],
            ["code", "CADQUERY"],
            ["mass", "MASS"]
          ].map(([k, l]) => {
            const I = ICON[k];
            return (
              <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
                <I size={14} />
                {l}
              </button>
            );
          })}
        </div>

        <div className="pane">
          {!m && <div className="row">Compile a part to unlock live parametric controls.</div>}

          {m && tab === "params" &&
            Object.entries(m.params || {}).map(([k, v]) => {
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
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? "COPIED" : "COPY SCRIPT"}
              </button>
              <pre dangerouslySetInnerHTML={{ __html: highlight(m.code || m.cadquery_code) }} />
            </>
          )}

          {m && tab === "mass" && (
            <>
              <div style={{ marginBottom: "14px" }}>
                <label
                  style={{
                    display: "block",
                    color: "#94a3b8",
                    fontSize: "11px",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    marginBottom: "8px"
                  }}
                >
                  Material
                </label>

                <select
                  value={selectedMaterial}
                  onChange={(e) => setSelectedMaterial(e.target.value)}
                  style={{
                    width: "100%",
                    background: "rgba(15, 23, 42, 0.9)",
                    border: "1px solid rgba(148, 163, 184, 0.25)",
                    borderRadius: "10px",
                    color: "#e2e8f0",
                    padding: "10px 12px",
                    fontSize: "13px",
                    outline: "none"
                  }}
                >
                  {Object.entries(MATERIALS).map(([key, mat]) => (
                    <option key={key} value={key}>
                      {mat.name}
                    </option>
                  ))}
                </select>
              </div>

              <div
                style={{
                  background: "rgba(15, 23, 42, 0.72)",
                  border: "1px solid rgba(148, 163, 184, 0.2)",
                  borderRadius: "12px",
                  padding: "12px",
                  marginBottom: "14px"
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ color: "#94a3b8", fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                    Active material
                  </span>
                  <span style={{ color: "#e2e8f0", fontWeight: 700 }}>{activeMaterial.name}</span>
                </div>

                <div style={{ marginTop: "12px", display: "grid", gap: "8px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <span style={{ color: "#94a3b8" }}>Density</span>
                    <span className="mono">{activeMaterial.density} g/cm³</span>
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <span style={{ color: "#94a3b8" }}>Volume</span>
                    <span className="mono">
                      {volumeCm3 > 0 ? `${volumeCm3.toFixed(2)} cm³` : "-"} /{" "}
                      {volumeCm3 > 0 ? `${(volumeCm3 * 1000).toFixed(0)} mm³` : "-"}
                    </span>
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <span style={{ color: "#94a3b8" }}>Mass</span>
                    <span className="mono">
                      {volumeCm3 > 0 ? formatMass(partMassGrams) : "-"}
                    </span>
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <span style={{ color: "#94a3b8" }}>Est. Material Cost</span>
                    <span className="mono" style={{ color: "#7dd3fc" }}>
                      {volumeCm3 > 0
                        ? `₹${formatMoney(estCostInr)} ($${formatMoney(estCostUsd)} USD)`
                        : "-"}
                    </span>
                  </div>
                </div>
              </div>

              <table>
                <thead>
                  <tr>
                    <th>Material</th>
                    <th>g/cm³</th>
                    <th>Mass</th>
                  </tr>
                </thead>

                <tbody>
                  {materialRows.map(({ key, name, density, mass }) => (
                    <tr key={key}>
                      <td style={{ width: "auto" }}>{name}</td>
                      <td className="mono">{density}</td>
                      <td
                        className="mono"
                        style={{ color: key === selectedMaterial ? "var(--cyan)" : "inherit" }}
                      >
                        {volumeCm3 > 0 ? formatMass(mass) : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="row" style={{ marginTop: 14, alignItems: "center" }}>
                <span>Volume: {volumeCm3 > 0 ? `${volumeCm3.toFixed(2)} cm³` : "-"}</span>
                <span>
                  BBox: {m.telemetry?.bbox_mm?.map((x) => x.toFixed(1)).join(" × ") || "-"} mm
                </span>
              </div>

              <div
                style={{
                  marginTop: "14px",
                  background: "rgba(12, 19, 31, 0.85)",
                  border: "1px solid rgba(125, 211, 252, 0.2)",
                  borderRadius: "10px",
                  padding: "10px 12px",
                  color: "#dbeafe"
                }}
              >
                <div
                  style={{
                    fontSize: "10px",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: "#93c5fd"
                  }}
                >
                  Live cost estimate
                </div>

                <div style={{ marginTop: "6px", fontWeight: 700 }}>
                  {volumeCm3 > 0
                    ? `Est. Material Cost: ₹${formatMoney(estCostInr)} ($${formatMoney(estCostUsd)} USD)`
                    : "Est. Material Cost: -"}
                </div>
              </div>
            </>
          )}
        </div>
      </aside>

      <CadViewport
        stlUrl={m?.stl}
        stepUrl={m?.step}
        busy={busy}
        materialKey={selectedMaterial}
        onMaterialChange={setSelectedMaterial}
      />

      {showUpgradeModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(5, 7, 15, 0.82)",
            backdropFilter: "blur(8px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
            padding: "20px"
          }}
        >
          <div
            style={{
              background: "#0d111c",
              border: "1px solid rgba(255, 255, 255, 0.12)",
              borderRadius: "16px",
              width: "100%",
              maxWidth: "520px",
              padding: "28px",
              boxShadow: "0 25px 60px rgba(0, 0, 0, 0.6)",
              position: "relative",
              color: "#fff"
            }}
          >
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
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "48px",
                  height: "48px",
                  borderRadius: "50%",
                  background: "rgba(0, 240, 255, 0.1)",
                  color: "#00f0ff",
                  marginBottom: "12px"
                }}
              >
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
              <div
                style={{
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: "12px",
                  padding: "16px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between"
                }}
              >
                <div>
                  <span
                    style={{
                      fontSize: "11px",
                      color: "#8a99ad",
                      fontWeight: 600,
                      letterSpacing: "0.5px"
                    }}
                  >
                    ONE-TIME
                  </span>

                  <h4 style={{ margin: "4px 0 8px 0", fontSize: "16px" }}>Pocket Refill</h4>

                  <div style={{ fontSize: "24px", fontWeight: 800, marginBottom: "8px" }}>
                    ₹99 <span style={{ fontSize: "12px", color: "#8a99ad", fontWeight: 400 }}>($1.29)</span>
                  </div>

                  <ul
                    style={{
                      margin: 0,
                      paddingLeft: "16px",
                      fontSize: "12px",
                      color: "#cbd5e1",
                      lineHeight: "1.6"
                    }}
                  >
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

              <div
                style={{
                  background: "linear-gradient(180deg, rgba(0, 240, 255, 0.08) 0%, rgba(0, 0, 0, 0.1) 100%)",
                  border: "1px solid rgba(0, 240, 255, 0.35)",
                  borderRadius: "12px",
                  padding: "16px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between"
                }}
              >
                <div>
                  <span
                    style={{
                      fontSize: "11px",
                      color: "#00f0ff",
                      fontWeight: 700,
                      letterSpacing: "0.5px"
                    }}
                  >
                    BEST VALUE
                  </span>

                  <h4 style={{ margin: "4px 0 8px 0", fontSize: "16px" }}>Maker Pass</h4>

                  <div style={{ fontSize: "24px", fontWeight: 800, marginBottom: "8px" }}>
                    ₹199 <span style={{ fontSize: "12px", color: "#8a99ad", fontWeight: 400 }}>/ month</span>
                  </div>

                  <ul
                    style={{
                      margin: 0,
                      paddingLeft: "16px",
                      fontSize: "12px",
                      color: "#cbd5e1",
                      lineHeight: "1.6"
                    }}
                  >
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

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "6px",
                fontSize: "11px",
                color: "#7e8b9b"
              }}
            >
              <ShieldCheck size={14} color="#00f0ff" />
              <span>Instant activation via UPI, Cards, or Netbanking</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
