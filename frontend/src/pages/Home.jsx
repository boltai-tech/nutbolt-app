import React, { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import * as THREE from "three";
import { ArrowRight, Cpu, Layers, Sliders, ShieldCheck, Download } from "lucide-react";

export default function Home() {
  const mountRef = useRef(null);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x030712, 0.015);

    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 15, 30);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const gridDim = 50;
    const particleCount = gridDim * gridDim;
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);

    const colorCyan = new THREE.Color(0x06b6d4);
    const colorMuted = new THREE.Color(0x1e293b);

    let idx = 0;
    for (let i = 0; i < gridDim; i++) {
      for (let j = 0; j < gridDim; j++) {
        const x = (i - gridDim / 2) * 1.5;
        const z = (j - gridDim / 2) * 1.5;
        positions[idx * 3] = x;
        positions[idx * 3 + 1] = 0;
        positions[idx * 3 + 2] = z;

        const mixRatio = Math.sin((i / gridDim) * Math.PI) * Math.cos((j / gridDim) * Math.PI);
        const col = colorMuted.clone().lerp(colorCyan, Math.max(0, mixRatio * 0.8));
        colors[idx * 3] = col.r;
        colors[idx * 3 + 1] = col.g;
        colors[idx * 3 + 2] = col.b;
        idx++;
      }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
      size: 0.15,
      vertexColors: true,
      transparent: true,
      opacity: 0.65,
    });

    const pointsMesh = new THREE.Points(geometry, material);
    scene.add(pointsMesh);

    const boxGeo = new THREE.BoxGeometry(16, 8, 16);
    const boxEdges = new THREE.EdgesGeometry(boxGeo);
    const boxLines = new THREE.LineSegments(
      boxEdges,
      new THREE.LineBasicMaterial({ color: 0x0ea5e9, transparent: true, opacity: 0.15 })
    );
    boxLines.position.set(0, 4, 0);
    scene.add(boxLines);

    let mouseX = 0;
    let mouseY = 0;
    const handleMouseMove = (e) => {
      mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
      mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
    };
    window.addEventListener("mousemove", handleMouseMove);

    const handleResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener("resize", handleResize);

    let clock = new THREE.Clock();
    let animId;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();

      const posAttr = geometry.attributes.position;
      let pIdx = 0;
      for (let i = 0; i < gridDim; i++) {
        for (let j = 0; j < gridDim; j++) {
          const u = i / gridDim;
          const v = j / gridDim;
          posAttr.setY(pIdx, Math.sin(elapsed * 1.5 + u * 8.0) * Math.cos(elapsed * 1.5 + v * 8.0) * 1.2);
          pIdx++;
        }
      }
      posAttr.needsUpdate = true;

      camera.position.x += (mouseX * 5 - camera.position.x) * 0.02;
      camera.position.y += (-mouseY * 3 + 15 - camera.position.y) * 0.02;
      camera.lookAt(0, 0, 0);

      boxLines.rotation.y = elapsed * 0.05;
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("resize", handleResize);
      if (container && renderer.domElement) container.removeChild(renderer.domElement);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div className="relative min-h-screen bg-[#030712] text-slate-100 font-sans overflow-x-hidden selection:bg-cyan-500 selection:text-black">
      <div ref={mountRef} className="absolute inset-0 pointer-events-none z-0" />

      <div className="relative z-10 max-w-6xl mx-auto px-6 pt-32 pb-24 flex flex-col items-center text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-cyan-500/30 bg-cyan-950/40 text-cyan-400 text-xs font-mono uppercase tracking-widest mb-8 backdrop-blur-md">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          Autonomous Parametric CAD Kernel v2.4
        </div>

        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight max-w-4xl font-mono text-transparent bg-clip-text bg-gradient-to-b from-white via-slate-200 to-slate-500 leading-tight">
          Mechanical Parts from Plain Text in <span className="text-cyan-400">1.5 Seconds</span>.
        </h1>

        <p className="mt-6 text-lg md:text-xl text-slate-400 max-w-2xl font-light leading-relaxed">
          The autonomous text-to-CAD platform built for hardware engineers. Produces single-solid, watertight manifold geometry with full parametric slider editing and AP214 STEP exports.
        </p>

        <div className="mt-10 flex flex-wrap gap-4 justify-center">
          <Link
            to="/studio"
            className="inline-flex items-center gap-2 px-8 py-3.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-base transition-all transform hover:-translate-y-0.5 shadow-lg shadow-cyan-500/25"
          >
            Open Studio <ArrowRight className="w-5 h-5" />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-28 w-full text-left">
          <div className="p-5 rounded-xl border border-slate-800/80 bg-slate-950/60 backdrop-blur-md">
            <Cpu className="w-6 h-6 text-cyan-400 mb-3" />
            <h3 className="font-semibold text-slate-200 font-mono text-sm">Deterministic Catalog</h3>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Standard hardware families synthesize instantly without boolean collisions.
            </p>
          </div>
          <div className="p-5 rounded-xl border border-slate-800/80 bg-slate-950/60 backdrop-blur-md">
            <ShieldCheck className="w-6 h-6 text-cyan-400 mb-3" />
            <h3 className="font-semibold text-slate-200 font-mono text-sm">Watertight B-Rep</h3>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Single-solid verification ensures manifold integrity before rendering.
            </p>
          </div>
          <div className="p-5 rounded-xl border border-slate-800/80 bg-slate-950/60 backdrop-blur-md">
            <Sliders className="w-6 h-6 text-cyan-400 mb-3" />
            <h3 className="font-semibold text-slate-200 font-mono text-sm">Live Parametric Sliders</h3>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Directly manipulate teeth, pitch, bores, and thicknesses with debounced updates.
            </p>
          </div>
          <div className="p-5 rounded-xl border border-slate-800/80 bg-slate-950/60 backdrop-blur-md">
            <Download className="w-6 h-6 text-cyan-400 mb-3" />
            <h3 className="font-semibold text-slate-200 font-mono text-sm">On-Demand AP214 STEP</h3>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Fast STL mesh streaming for preview; analytical STEP compiled strictly on demand.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
