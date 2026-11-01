import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Sparkles, ArrowRight, Box, SlidersHorizontal, Download } from "lucide-react";

const EXAMPLES = [
  "L-shaped mounting bracket 50 wide, 60 base, 50 tall, 5 thick, two 6 mm base holes",
  "GT2 timing pulley 20 teeth 5 mm bore",
  "NEMA 17 motor mount plate",
  "Stepped shaft 30/20/12 mm with 4 mm keyway",
  "Project box 80x60x35 with 4 corner screw bosses",
];

function GridField() {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext("2d");
    const COLS = 44, ROWS = 26;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, dpr = 1, raf = 0, t = 0, last = performance.now();
    const mouse = { x: -9999, y: -9999, sx: -9999, sy: -9999, active: false };

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth; h = canvas.clientHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const project = (i, j) => {
      const gx = (i / (COLS - 1)) * 2 - 1;
      const gz = j / (ROWS - 1);
      const d = 1 + gz * 4.2;
      const sx = w / 2 + (gx * w * 0.95) / d;
      const baseY = h * 0.36 + (h * 0.7) / d;
      let lift = reduce ? 0 : Math.sin(gx * 3.2 + t * 0.9) * Math.cos(gz * 5 - t * 0.7) * 16;
      let glow = 0;
      if (mouse.active) {
        const dx = sx - mouse.sx, dy = baseY - mouse.sy;
        const k = Math.exp(-(dx * dx + dy * dy) / (2 * 150 * 150));
        lift += k * 70;
        glow = k;
      }
      return { x: sx, y: baseY - lift / d, glow, a: 1 - gz * 0.88, d };
    };

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      const pts = [];
      for (let j = 0; j < ROWS; j++) for (let i = 0; i < COLS; i++) pts.push(project(i, j));
      const P = (i, j) => pts[j * COLS + i];
      ctx.lineWidth = 1;
      for (let j = 0; j < ROWS; j++) {
        for (let i = 0; i < COLS; i++) {
          const p = P(i, j);
          const pulse = reduce ? 0 : Math.max(0, Math.sin(t * 1.4 - j * 0.45)) * 0.18;
          const alpha = Math.min(1, p.a * (0.16 + pulse) + p.glow * 0.7);
          ctx.strokeStyle = `rgba(0, 240, 255, ${alpha})`;
          if (i < COLS - 1) { const q = P(i + 1, j); ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke(); }
          if (j < ROWS - 1) { const q = P(i, j + 1); ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke(); }
          if (p.glow > 0.08 || (i % 4 === 0 && j % 3 === 0)) {
            ctx.fillStyle = `rgba(160, 250, 255, ${Math.min(1, p.a * 0.35 + p.glow)})`;
            ctx.fillRect(p.x - 1, p.y - 1, 2 + p.glow * 2, 2 + p.glow * 2);
          }
        }
      }
    };

    const loop = (now) => {
      raf = requestAnimationFrame(loop);
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      t += dt;
      mouse.sx += (mouse.x - mouse.sx) * 0.12;
      mouse.sy += (mouse.y - mouse.sy) * 0.12;
      draw();
    };

    const onMove = (e) => {
      const r = canvas.getBoundingClientRect();
      mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top;
      if (!mouse.active) { mouse.sx = mouse.x; mouse.sy = mouse.y; }
      mouse.active = true;
    };
    const onLeave = () => { mouse.active = false; };

    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerleave", onLeave);
    if (reduce) draw(); else raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return <canvas ref={ref} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block" }} />;
}

const mono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" };

export default function Home() {
  const nav = useNavigate();
  const [prompt, setPrompt] = useState("");

  const go = (text) => {
    const p = (text ?? prompt).trim();
    nav(p ? `/studio?prompt=${encodeURIComponent(p)}` : "/studio");
  };

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: "#030712", color: "#e2e8f0", overflow: "hidden", ...mono }}>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 80% 60% at 50% 30%, rgba(0,240,255,0.08) 0%, rgba(3,7,18,0) 60%)" }} />
      <GridField />
      <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(3,7,18,0.85) 0%, rgba(3,7,18,0) 35%, rgba(3,7,18,0.6) 100%)", pointerEvents: "none" }} />

      <nav style={{ position: "relative", zIndex: 2, display: "flex", justifyContent: "space-between", alignItems: "center", padding: "20px 28px" }}>
        <Link to="/" style={{ color: "#fff", textDecoration: "none", fontWeight: 600, fontSize: 18, letterSpacing: "-0.02em" }}>
          nut<b style={{ color: "#00f0ff" }}>bolt</b>.ai
        </Link>
        <Link to="/studio" style={{ color: "#00f0ff", textDecoration: "none", fontSize: 13, border: "1px solid rgba(0,240,255,0.35)", padding: "7px 14px", borderRadius: 8 }}>
          Open Studio
        </Link>
      </nav>

      <main style={{ position: "relative", zIndex: 2, maxWidth: 880, margin: "0 auto", padding: "7vh 24px 60px", textAlign: "center" }}>
        <div style={{ display: "inline-block", fontSize: 11, letterSpacing: "0.14em", color: "#00f0ff", border: "1px solid rgba(0,240,255,0.3)", borderRadius: 999, padding: "5px 12px", marginBottom: 22 }}>
          GENERATIVE CAD KERNEL · OPENCASCADE
        </div>
        <h1 style={{ margin: 0, fontSize: "clamp(34px, 6vw, 62px)", lineHeight: 1.05, letterSpacing: "-0.03em", fontWeight: 600 }}>
          Describe a part.<br /><span style={{ color: "#00f0ff" }}>Get a solid.</span>
        </h1>
        <p style={{ margin: "20px auto 0", maxWidth: 560, color: "#94a3b8", fontSize: 15, lineHeight: 1.6 }}>
          Plain-English specs in, watertight B-Rep out. Live parametric sliders, mass and material cost, STL and STEP export.
        </p>

        <div style={{ margin: "34px auto 0", maxWidth: 680, background: "rgba(8,14,28,0.82)", border: "1px solid rgba(0,240,255,0.25)", borderRadius: 14, padding: 14, backdropFilter: "blur(8px)", textAlign: "left" }}>
          <textarea
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) go(); }}
            placeholder="e.g. L-shaped mounting bracket with 4 holes, 5 mm thick aluminium..."
            style={{ width: "100%", boxSizing: "border-box", background: "transparent", border: "none", outline: "none", resize: "none", color: "#e2e8f0", fontSize: 14, lineHeight: 1.55, ...mono }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
            <span style={{ fontSize: 11, color: "#64748b" }}>Ctrl+Enter</span>
            <button
              onClick={() => go()}
              style={{ display: "flex", alignItems: "center", gap: 8, background: "linear-gradient(90deg, #00f0ff, #00a8ff)", color: "#04101a", border: "none", borderRadius: 9, padding: "10px 18px", fontWeight: 700, fontSize: 13, cursor: "pointer", ...mono }}
            >
              <Sparkles size={15} /> SYNTHESIZE <ArrowRight size={15} />
            </button>
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", marginTop: 18 }}>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => go(ex)}
              style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", color: "#94a3b8", borderRadius: 999, padding: "6px 12px", fontSize: 11, cursor: "pointer", ...mono }}
            >
              {ex.length > 46 ? ex.slice(0, 46) + "…" : ex}
            </button>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 14, marginTop: 56, textAlign: "left" }}>
          {[
            [Box, "Manifold-safe solids", "One closed profile, one revolve. No floating parts, no air gaps."],
            [SlidersHorizontal, "Live parametrics", "Every dimension becomes a slider; the mesh recompiles as you drag."],
            [Download, "STL + STEP", "Print-ready meshes instantly, CNC-ready STEP on demand."],
          ].map(([Icon, title, body]) => (
            <div key={title} style={{ background: "rgba(8,14,28,0.7)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, padding: 16 }}>
              <Icon size={18} color="#00f0ff" />
              <div style={{ margin: "10px 0 6px", fontWeight: 600, fontSize: 14 }}>{title}</div>
              <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.55 }}>{body}</div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
