import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Layers, Box, Download } from "lucide-react";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export const MATERIALS = {
  steel: {
    name: "A36 Steel",
    color: "#686d76",
    metalness: 0.95,
    roughness: 0.28
  },
  aluminum: {
    name: "6061 Aluminum",
    color: "#d2d7df",
    metalness: 0.9,
    roughness: 0.2
  },
  brass: {
    name: "C360 Brass",
    color: "#d9a536",
    metalness: 0.92,
    roughness: 0.22
  },
  copper: {
    name: "Polished Copper",
    color: "#b85d38",
    metalness: 0.95,
    roughness: 0.25
  },
  pla: {
    name: "PLA Plastic",
    color: "#38bdf8",
    metalness: 0.05,
    roughness: 0.75
  },
  abs: {
    name: "ABS Plastic",
    color: "#f97316",
    metalness: 0.05,
    roughness: 0.55
  },
  petg: {
    name: "PETG / Tough Resin",
    color: "#10b981",
    metalness: 0.1,
    roughness: 0.35
  }
};

const createGridTexture = () => {
  const size = 1024;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, size, size);

  ctx.fillStyle = "rgba(15, 23, 42, 0.95)";
  ctx.fillRect(0, 0, size, size);

  const major = 128;
  const minor = 32;

  ctx.strokeStyle = "rgba(96, 165, 250, 0.18)";
  ctx.lineWidth = 1;
  for (let x = 0; x <= size; x += minor) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, size);
    ctx.stroke();
  }
  for (let y = 0; y <= size; y += minor) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(size, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(96, 165, 250, 0.45)";
  ctx.lineWidth = 2;
  for (let x = 0; x <= size; x += major) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, size);
    ctx.stroke();
  }
  for (let y = 0; y <= size; y += major) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(size, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(251, 191, 36, 0.32)";
  ctx.beginPath();
  ctx.moveTo(size / 2, 0);
  ctx.lineTo(size / 2, size);
  ctx.moveTo(0, size / 2);
  ctx.lineTo(size, size / 2);
  ctx.stroke();

  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(255,255,255,0.28)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);

  return canvas;
};

export default function CadViewport({
  stlUrl,
  stepUrl,
  busy,
  materialKey = "steel",
  onMaterialChange
}) {
  const mount = useRef(null);
  const S = useRef({});
  const [wire, setWire] = useState(false);
  const [mat, setMat] = useState(materialKey);

  useEffect(() => {
    setMat(materialKey);
  }, [materialKey]);

  useEffect(() => {
    const el = mount.current;
    if (!el) return;

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: false
    });

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.outputColorSpace = THREE.SRGBColorSpace;

    if ("logarithmicDepthBuffer" in renderer) {
      renderer.logarithmicDepthBuffer = true;
    }

    const scene = new THREE.Scene();
    scene.background = null;
    scene.fog = new THREE.Fog("#020617", 200, 1800);

    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
    camera.position.set(140, 100, 180);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = true;
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN
    };
    controls.minDistance = 20;
    controls.maxDistance = 2500;

    const keyLight = new THREE.DirectionalLight("#fff6e8", 2.5);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(2048, 2048);
    keyLight.shadow.camera.near = 0.5;
    keyLight.shadow.camera.far = 4000;
    keyLight.shadow.bias = -0.00025;
    keyLight.position.set(160, 220, 140);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight("#7dd3fc", 0.9);
    fillLight.position.set(-200, 120, -120);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight("#f8fafc", 0.7);
    rimLight.position.set(-160, 80, 180);
    scene.add(rimLight);

    scene.add(new THREE.AmbientLight("#94a3b8", 0.45));

    const gridTexture = new THREE.CanvasTexture(createGridTexture());
    gridTexture.anisotropy = renderer.capabilities.getMaxAnisotropy();

    const grid = new THREE.Mesh(
      new THREE.PlaneGeometry(1800, 1800),
      new THREE.MeshBasicMaterial({
        map: gridTexture,
        transparent: true,
        opacity: 0.65,
        depthWrite: false,
        toneMapped: false
      })
    );
    grid.rotation.x = -Math.PI / 2;
    grid.position.y = -0.3;
    scene.add(grid);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(300, 128),
      new THREE.MeshStandardMaterial({
        color: "#0b1220",
        roughness: 0.9,
        metalness: 0.06,
        transparent: true,
        opacity: 0.92
      })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.32;
    floor.receiveShadow = true;
    scene.add(floor);

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let raf = 0;
    const render = () => {
      raf = requestAnimationFrame(render);
      controls.update();
      renderer.render(scene, camera);
    };
    render();

    S.current = { renderer, scene, camera, controls, keyLight, fillLight, rimLight, grid, floor };

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      pmrem.dispose();

      if (S.current.mesh) {
        S.current.mesh.geometry.dispose();
        if (S.current.mesh.material) {
          if (Array.isArray(S.current.mesh.material)) {
            S.current.mesh.material.forEach((m) => m.dispose && m.dispose());
          } else {
            S.current.mesh.material.dispose();
          }
        }
      }

      el.removeChild(renderer.domElement);
    };
  }, []);

  const setView = (directionVector) => {
    const { camera, controls } = S.current;
    if (!camera || !controls) return;

    const target = new THREE.Vector3(0, 0, 0);
    const dir = new THREE.Vector3(...directionVector).normalize();
    const dist = S.current.fit?.dist ?? 180;

    camera.position.copy(target.clone().add(dir.multiplyScalar(dist)));
    controls.target.copy(target);
    controls.update();
  };

  useEffect(() => {
    if (!stlUrl) return;

    const { scene, camera, controls } = S.current;
    if (!scene || !camera || !controls) return;

    new STLLoader().load(stlUrl, (geometry) => {
      geometry.computeVertexNormals();
      geometry.computeBoundingBox();

      if (!geometry.boundingBox) return;

      const box = geometry.boundingBox;
      const size = new THREE.Vector3();
      box.getSize(size);
      const center = new THREE.Vector3();
      box.getCenter(center);
      geometry.translate(-center.x, -center.y, -center.z);

      const material = new THREE.MeshPhysicalMaterial({
        color: MATERIALS[mat]?.color || "#ffffff",
        metalness: MATERIALS[mat]?.metalness ?? 0.8,
        roughness: MATERIALS[mat]?.roughness ?? 0.3,
        clearcoat: 0.2,
        clearcoatRoughness: 0.25,
        wireframe: wire
      });

      const mesh = new THREE.Mesh(geometry, material);
      mesh.castShadow = true;
      mesh.receiveShadow = true;

      if (S.current.mesh) {
        scene.remove(S.current.mesh);
        if (S.current.mesh.geometry) S.current.mesh.geometry.dispose();
        if (S.current.mesh.material) {
          if (Array.isArray(S.current.mesh.material)) {
            S.current.mesh.material.forEach((m) => m.dispose && m.dispose());
          } else {
            S.current.mesh.material.dispose();
          }
        }
      }

      scene.add(mesh);
      S.current.mesh = mesh;

      const maxDim = Math.max(size.x, size.y, size.z) || 1;
      const dist = (maxDim / 2) / Math.tan((camera.fov * Math.PI) / 360) * 2.3;
      const target = new THREE.Vector3(0, 0, 0);

      S.current.fit = { target, dist };

      const isoDir = new THREE.Vector3(1, 0.7, 1).normalize();
      camera.position.copy(target.clone().add(isoDir.multiplyScalar(dist)));
      controls.target.copy(target);
      controls.update();

      camera.near = 0.1;
      camera.far = 5000;
      camera.updateProjectionMatrix();
    });
  }, [stlUrl, mat, wire]);

  useEffect(() => {
    const mesh = S.current.mesh;
    if (!mesh) return;

    const materialCfg = MATERIALS[mat] || MATERIALS.steel;

    mesh.material.color.set(materialCfg.color);
    mesh.material.metalness = materialCfg.metalness;
    mesh.material.roughness = materialCfg.roughness;
    mesh.material.wireframe = wire;
    mesh.material.needsUpdate = true;

    if (onMaterialChange) {
      onMaterialChange(mat);
    }
  }, [mat, wire, onMaterialChange]);

  return (
    <div className="vp">
      <div ref={mount} style={{ position: "absolute", inset: 0 }} />

      <div className="views">
        {[
          ["ISO", [1, 0.7, 1.15]],
          ["FRONT", [0, 0.01, 1]],
          ["TOP", [0, 1, 0.001]],
          ["RIGHT", [1, 0.01, 0]]
        ].map(([n, v]) => (
          <button key={n} onClick={() => setView(v)}>
            {n}
          </button>
        ))}
      </div>

      <div className="dock">
        <button
          data-tip={wire ? "Solid shading" : "Wireframe"}
          className={wire ? "on" : ""}
          onClick={() => setWire((w) => !w)}
        >
          <Layers size={18} />
        </button>

        <button
          type="button"
          data-tip="Download .STL"
          className="vp-btn"
          onClick={() => {
            if (!stlUrl) {
              alert("Please synthesize a 3D solid first before downloading.");
              return;
            }
            const a = document.createElement("a");
            a.href = stlUrl;
            a.download = "part.stl";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }}
        >
          <Box size={18} />
        </button>

        <button
          type="button"
          data-tip="Download .STEP (CNC)"
          className="hot vp-btn"
          onClick={() => {
            if (!stepUrl) {
              alert("Please synthesize a 3D solid first before downloading.");
              return;
            }
            const a = document.createElement("a");
            a.href = stepUrl;
            a.download = "part.step";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }}
        >
          <Download size={18} />
        </button>
      </div>

      <div className="hud" style={{ whiteSpace: "nowrap", overflowX: "auto" }}>
        {Object.entries(MATERIALS).map(([key, mcfg]) => (
          <button
            key={key}
            className={mat === key ? "on" : ""}
            onClick={() => {
              setMat(key);
              if (onMaterialChange) onMaterialChange(key);
            }}
            style={{ whiteSpace: "nowrap", flexShrink: 0 }}
          >
            <i style={{ background: mcfg.color }} />
            {mcfg.name}
          </button>
        ))}
      </div>

      {!stlUrl && <div className="empty">AWAITING GEOMETRY - DESCRIBE A PART TO COMPILE</div>}
      {busy && <div className="empty" style={{ background: "#050607aa" }}>COMPILING B-REP ...</div>}
    </div>
  );
}
