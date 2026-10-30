import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Landing from "./pages/Landing.jsx";
import Studio from "./pages/Studio.jsx";
import "./index.css";

createRoot(document.getElementById("root")).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/studio" element={<Studio />} />
    </Routes>
  </BrowserRouter>
);

const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.1 });
const scan = () => document.querySelectorAll(".page .card, .page h2, .page .eyebrow, .page .stat, .page tr, .page .lede").forEach((el) => {
  if (!el.dataset.o) { el.dataset.o = 1; el.classList.add("rv"); io.observe(el); }
});
new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });

document.addEventListener("pointermove", (e) => {
  const c = e.target.closest?.(".card");
  if (c) { const r = c.getBoundingClientRect(); c.style.setProperty("--cx", e.clientX - r.left + "px"); c.style.setProperty("--cy", e.clientY - r.top + "px"); }
  const b = e.target.closest?.(".btn");
  if (b) { const r = b.getBoundingClientRect(); b.style.setProperty("--tx", (e.clientX - r.left - r.width / 2) * 0.14 + "px"); b.style.setProperty("--ty", (e.clientY - r.top - r.height / 2) * 0.22 + "px"); }
});
document.addEventListener("pointerout", (e) => { const b = e.target.closest?.(".btn"); if (b) { b.style.setProperty("--tx", "0px"); b.style.setProperty("--ty", "0px"); } });
document.addEventListener("pointerdown", (e) => {
  const b = e.target.closest?.(".btn");
  if (b) { const r = b.getBoundingClientRect(); b.style.setProperty("--rx", e.clientX - r.left + "px"); b.style.setProperty("--ry", e.clientY - r.top + "px"); }
});