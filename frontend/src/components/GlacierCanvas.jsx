import { useEffect, useRef } from "react";

const COL = ["139,92,246", "6,182,212", "245,158,11"];

export default function GlacierCanvas() {
  const ref = useRef(null);
  useEffect(() => {
    const c = ref.current, g = c.getContext("2d"), d = Math.min(window.devicePixelRatio || 1, 1.5);
    let w, h, raf, t = 0;
    const m = { x: -999, y: -999 }, P = [];
    const resize = () => {
      w = window.innerWidth; h = window.innerHeight; c.width = w * d; c.height = h * d; g.setTransform(d, 0, 0, d, 0, 0);
      if (!P.length) for (let i = 0; i < 95; i++) P.push({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 0.35, vy: (Math.random() - 0.5) * 0.35, r: Math.random() * 1.6 + 0.7, c: i % 3 });
    };
    const move = (e) => { m.x = e.clientX; m.y = e.clientY; };
    resize(); window.addEventListener("resize", resize); window.addEventListener("mousemove", move);
    const draw = () => {
      t += 0.006; g.clearRect(0, 0, w, h);
      g.globalCompositeOperation = "lighter";
      for (let i = 0; i < 4; i++) {
        const x = w * (0.5 + 0.38 * Math.sin(t * (0.6 + i * 0.17) + i * 1.9)), y = h * (0.35 + 0.3 * Math.cos(t * (0.5 + i * 0.13) + i * 2.3));
        const r = Math.max(w, h) * (0.32 + 0.1 * Math.sin(t * 0.9 + i)), gr = g.createRadialGradient(x, y, 0, x, y, r);
        gr.addColorStop(0, `rgba(${COL[i % 3]},0.2)`); gr.addColorStop(1, `rgba(${COL[i % 3]},0)`);
        g.fillStyle = gr; g.fillRect(0, 0, w, h);
      }
      const sp = g.createRadialGradient(m.x, m.y, 0, m.x, m.y, 260);
      sp.addColorStop(0, "rgba(139,92,246,0.14)"); sp.addColorStop(1, "rgba(139,92,246,0)");
      g.fillStyle = sp; g.fillRect(0, 0, w, h);
      g.globalCompositeOperation = "source-over";
      for (const p of P) {
        const dx = p.x - m.x, dy = p.y - m.y, dd = Math.hypot(dx, dy);
        if (dd < 170) { p.vx += (dx / dd) * 0.05; p.vy += (dy / dd) * 0.05; }
        p.vx *= 0.985; p.vy *= 0.985; p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = w; if (p.x > w) p.x = 0; if (p.y < 0) p.y = h; if (p.y > h) p.y = 0;
      }
      for (let i = 0; i < P.length; i++) {
        const a = P[i];
        for (let j = i + 1; j < P.length; j++) {
          const b = P[j], dist = Math.hypot(a.x - b.x, a.y - b.y);
          if (dist < 125) { g.strokeStyle = `rgba(${COL[a.c]},${(1 - dist / 125) * 0.28})`; g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke(); }
        }
        const md = Math.hypot(a.x - m.x, a.y - m.y);
        if (md < 190) { g.strokeStyle = `rgba(103,232,249,${(1 - md / 190) * 0.55})`; g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(m.x, m.y); g.stroke(); }
        g.fillStyle = `rgba(${COL[a.c]},0.9)`; g.shadowColor = `rgb(${COL[a.c]})`; g.shadowBlur = 8;
        g.beginPath(); g.arc(a.x, a.y, a.r, 0, 7); g.fill(); g.shadowBlur = 0;
      }
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); window.removeEventListener("mousemove", move); };
  }, []);
  return <canvas ref={ref} className="canvas-bg" />;
}