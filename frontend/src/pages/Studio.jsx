import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Sparkles, Copy, Check, SlidersHorizontal, Code, Scale } from "lucide-react";
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

  const abs = (u) => (u.startsWith("http") ? u : API + u) + "?t=" + Date.now();

  const generate = async (text = prompt) => {
    if (!text.trim()) return;
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

  const vol = m?.telemetry?.volume_cm3;

  return (
    <div className="studio">
      <aside className="console">
        <header>
          <Link to="/" className="logo">nut<b>bolt</b>.ai</Link>
          <span className={"status" + (busy ? " busy" : "")}>
            <i />{busy ? "COMPILING" : "KERNEL READY"}
          </span>
        </header>

        <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--line)" }}>
          <textarea
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe the mechanical part: dimensions, holes, fillets, bolt circles, wall thickness..."
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) generate(); }}
          />
          <div className="row">
            <span className="core-chip">OpenCASCADE Core</span>
            <span>Ctrl+Enter to compile</span>
          </div>
          <button className="btn gold" style={{ width: "100%" }} disabled={busy} onClick={() => generate()}>
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
    </div>
  );
}
