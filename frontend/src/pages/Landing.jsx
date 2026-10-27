import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import GlacierCanvas from "../components/GlacierCanvas.jsx";

const PROMPT = "NEMA 23 to 8mm lead-screw flanged adapter plate with radial cooling fins";
const LOGS = [
  "[00.04s] parse intent: adapter_plate / NEMA23 / lead_screw",
  "[00.31s] extract pilot_dia=38.1 bolt_circle=66.68 bore=8.0",
  "[00.62s] synthesize CadQuery AST (14 ops, 3 workplanes)",
  "[01.40s] OCCT boolean fuse: plate + 12 radial fins",
  "[02.15s] fillet r=2.0 on 24 edges ... ok",
  "[02.90s] shape check: manifold, watertight, 0 free edges",
  "[03.42s] mass @ Al6061-T6: 118.6 g  |  vol 43.93 cm3",
  "[03.71s] export part.step (AP214) + part.stl  DONE",
];
const PARAMS = ["plate_thickness=8.0", "pilot_dia=38.1", "bolt_circle=66.68", "shaft_bore=8.0", "fin_count=12", "fin_height=14.0"];

const BENTO = [
  ["01", "True mathematical B-Rep solids", "Analytical cylinders, true circles and exact planar faces with native NURBS surfaces. Your bore is a cylinder, not 4,000 triangles pretending to be one."],
  ["02", "Live AST dimensional override", "Every synthesized model exposes a reactive parameter dictionary. Drag bore diameter, bolt circle, wall thickness or rib count and the solid recompiles - no prompt regeneration."],
  ["03", "Instant physical BOM", "Volume in cm3 mapped against real densities: Al 6061-T6, Grade 5 Titanium, 1018 CR Steel, Carbon-Fiber PLA. Know the weight before you cut stock."],
  ["04", "Turnkey CAM and slicer output", "One-click ISO 10303-21 .STEP and high-resolution binary .STL for Mastercam, Fusion CAM, Bambu Studio and PrusaSlicer."],
  ["05", "Airgapped and sovereign", "A self-hosted FastAPI + CadQuery kernel runs on your machine. No proprietary geometry is ever sent to a shared model database."],
];
const PRESETS = [
  ["Rotary Drive", "Flanged Shaft Couplers and Dual-Bore Bushings", "Flanged shaft coupler, 8mm to 12mm dual bore, 4x M3 set screws, 30mm OD", "bore A/B - flange OD - set-screw count"],
  ["Mechatronics", "NEMA 17/23/34 Motor Mounts and Belt Tensioners", "NEMA 23 stepper motor mount bracket with slotted belt tensioner, 5mm wall", "frame size - slot travel - wall"],
  ["Power Transmission", "Parametric Timing Pulleys and Spur Pinions", "GT2 20-tooth timing pulley, 8mm bore, 6mm belt width, M3 grub screw", "tooth count - bore - belt width"],
  ["Structural", "Self-Centering Pillow Blocks and Extrusion Brackets", "Pillow block for 608 bearing, 2x M5 mounting holes, with 2020 extrusion bracket", "bearing OD - hole pitch - rib count"],
];
const FAQ = [
  ["How does this differ from mesh-based generative 3D tools?", "Text-to-3D gaming models emit triangulated .OBJ meshes: no faces, no edges, no dimensions you can machine. nutbolt.ai emits a B-Rep solid from parametric CadQuery code on OpenCASCADE, so every hole, fillet and plane remains an addressable mathematical entity."],
  ["Can I import the STEP files into SolidWorks or Siemens NX?", "Yes. AP214 STEP carries solid bodies with analytic and NURBS faces, which SolidWorks, NX, Inventor and Fusion 360 recognize natively as editable solid bodies you can mate, drawing-annotate and toolpath."],
  ["What precision tolerances are guaranteed?", "Geometry is analytical, so dimensional accuracy is +/-0.001 mm within the kernel. Your final part tolerance is then set by your machine and process, not by tessellation."],
  ["Does my design data leave my machine?", "No. The kernel is a local FastAPI service on localhost:8000. Prompts, code and geometry stay on your hardware."],
];

function Count({ to, dec = 0, pre = "", suf = "" }) {
  const r = useRef(null); const [v, setV] = useState(0);
  useEffect(() => {
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return; io.disconnect(); const t0 = performance.now();
      const f = (t) => { const p = Math.min((t - t0) / 1500, 1); setV(to * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(f); };
      requestAnimationFrame(f);
    });
    if (r.current) io.observe(r.current);
    return () => io.disconnect();
  }, [to]);
  return <span ref={r}>{pre}{v.toFixed(dec)}{suf}</span>;
}
const TICKER = ["STEP AP214", "OpenCASCADE kernel", "NURBS surfaces", "Manifold watertight", "CadQuery AST", "Mastercam ready", "Fusion CAM", "Bambu Studio", "PrusaSlicer", "SolidWorks import", "Siemens NX import", "Airgapped"];
const STEPS = [
  ["01", "Describe", "Write the part the way you would brief a machinist: frame size, bore, bolt circle, wall, fins, material intent."],
  ["02", "Compile", "The kernel synthesizes CadQuery, fuses and fillets on OpenCASCADE, then validates the shape is manifold."],
  ["03", "Machine", "Tune parameters live, check mass per material, then export STEP to CAM or STL to your slicer."],
];

export default function Landing() {
  const nav = useNavigate();
  const [typed, setTyped] = useState(0);
  const [shown, setShown] = useState(0);
  const [run, setRun] = useState(0);

  useEffect(() => {
    setTyped(0); setShown(0);
    const a = setInterval(() => setTyped((n) => (n < PROMPT.length ? n + 1 : n)), 28);
    const b = setTimeout(() => {
      const l = setInterval(() => setShown((n) => { if (n >= LOGS.length) { clearInterval(l); return n; } return n + 1; }), 520);
    }, PROMPT.length * 28 + 300);
    return () => { clearInterval(a); clearTimeout(b); };
  }, [run]);

  return (
    <>
      <GlacierCanvas />
      <div className="page">
        <nav><div className="wrap">
          <div className="logo">nut<b>bolt</b>.ai</div>
          <div style={{ display: "flex", gap: 22, alignItems: "center" }}>
            <a href="#why">Why switch</a><a href="#presets">Presets</a><a href="#faq">Specs</a>
            <Link className="btn gold" to="/studio">LAUNCH STUDIO</Link>
          </div>
        </div></nav>

        <header className="wrap hero">
          <div>
            <div className="eyebrow pill"><i className="dot" />Natural language to mill-spec solids</div>
            <h1>Describe the part.<br />Receive a <em>B-Rep solid</em>.</h1>
            <p className="lede">Type an engineering description, get deterministic STEP (AP214) with native NURBS curvature - not the triangulated .OBJ debris that text-to-3D gaming models hand you. Watertight, manifold, ready for the mill.</p>
            <div style={{ display: "flex", gap: 12 }}>
              <Link className="btn gold" to="/studio">START COMPILING</Link>
              <a className="btn" href="#why">WHY ENGINEERS SWITCH</a>
            </div>
            <div className="spec mono" style={{ marginTop: 28 }}>OpenCASCADE kernel - +/-0.001 mm analytical - under 4 s</div>
          </div>
          <div className="card sim">
            <div className="sim-head"><i /><i /><i /></div>
            <div className="sim-body">
              <div className="sim-prompt">&gt; {PROMPT.slice(0, typed)}<span style={{ opacity: typed < PROMPT.length ? 1 : 0 }}>|</span></div>
              {LOGS.slice(0, shown).map((l, i) => <div key={i} className={"log" + (i === LOGS.length - 1 ? " ok" : "")}>{l}</div>)}
              {shown >= LOGS.length - 2 && <div className="chips">{PARAMS.map((p) => <span className="chip" key={p}>{p}</span>)}</div>}
              <button className="btn" style={{ marginTop: 16 }} onClick={() => setRun((r) => r + 1)}>REPLAY</button>
            </div>
          </div>
        </header>

        <div className="marquee"><div className="track">{[...TICKER, ...TICKER].map((t, i) => <span key={i}>{t}</span>)}</div></div>

        <section style={{ padding: "64px 0 0" }}><div className="wrap stats">
          <div className="stat"><b><Count to={4} pre="< " suf=" s" /></b><span>Prompt to solid</span></div>
          <div className="stat"><b><Count to={0.001} dec={3} pre="+/-" /></b><span>mm analytical tolerance</span></div>
          <div className="stat"><b><Count to={100} suf="%" /></b><span>B-Rep, zero mesh</span></div>
          <div className="stat"><b><Count to={0} suf=" B" /></b><span>IP leaving your machine</span></div>
        </div></section>

        <section style={{ paddingBottom: 0 }}><div className="wrap">
          <div className="eyebrow">Workflow</div>
          <h2>Brief. Compile. <em>Cut metal.</em></h2>
          <div className="steps">{STEPS.map(([n, t, d]) => <div className="card step" key={n}><big>{n}</big><h3>{t}</h3><p>{d}</p></div>)}</div>
        </div></section>

        <section id="why"><div className="wrap">
          <div className="eyebrow">Why engineers switch</div>
          <h2>45 minutes of sketching, <em>or 4 seconds</em>.</h2>
          <div className="versus">
            <div className="card bad"><h3>Legacy CAD</h3><ul>
              <li>SolidWorks, Inventor, Fusion 360: 45 minutes of manual sketching and constraint setting for a standard adapter, bracket or enclosure.</li>
              <li>Over-constrained sketches that break on the first dimension change.</li>
              <li>Mesh generators: faceted, non-manifold, unmachinable.</li></ul></div>
            <div className="card good"><h3>nutbolt.ai</h3><ul>
              <li>Instant parametric code on an OpenCASCADE kernel.</li>
              <li>Guaranteed manifold, watertight, CNC-milling-ready solids.</li>
              <li>Exact mass telemetry per material in under 4 seconds.</li></ul></div>
          </div>
          <div className="bento">
            {BENTO.map(([n, t, d]) => <div className="card" key={n}><div className="num">MODULE {n}</div><h3>{t}</h3><p>{d}</p></div>)}
          </div>
        </div></section>

        <section id="presets"><div className="wrap">
          <div className="eyebrow">Hardware preset gallery</div>
          <h2>One click. <em>Real hardware.</em></h2>
          <div className="presets">
            {PRESETS.map(([cat, t, prompt, spec]) => (
              <a className="card preset" key={cat} onClick={() => nav("/studio?prompt=" + encodeURIComponent(prompt))}>
                <div className="num">{cat.toUpperCase()}</div><h3>{t}</h3>
                <p>{prompt}</p><div className="spec">{spec}</div>
              </a>
            ))}
          </div>
        </div></section>

        <section id="faq"><div className="wrap">
          <div className="eyebrow">Technical specifications</div>
          <h2>Answers for <em>machinists</em>.</h2>
          <div className="card" style={{ padding: 0, marginTop: 30 }}>
            <table><thead><tr><th>Question</th><th>Answer</th></tr></thead>
              <tbody>{FAQ.map(([q, a]) => <tr key={q}><td>{q}</td><td>{a}</td></tr>)}</tbody></table>
          </div>
        </div></section>

        <footer><div className="wrap">nutbolt.ai - local kernel at localhost:8000 - ISO 10303-21</div></footer>
      </div>
    </>
  );
}