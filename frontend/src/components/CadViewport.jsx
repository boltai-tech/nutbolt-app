import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Layers, Box, Download } from "lucide-react";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

// Authentic workshop metals & alloys
export const MATERIALS = {
  steel: { name: "A36 Steel", color: "#686d76", metalness: 0.95, roughness: 0.28 },
  aluminum: { name: "6061 Aluminum", color: "#d2d7df", metalness: 0.90, roughness: 0.20 },
  brass: { name: "C360 Brass", color: "#d9a536", metalness: 0.92, roughness: 0.22 },
  copper: { name: "Polished Copper", color: "#b85d38", metalness: 0.95, roughness: 0.25 },
};

export default function CadViewport({ stlUrl, stepUrl, busy }) {
  const mount = useRef(null);
  const S = useRef({});
  const [wire, setWire] = useState(false);
  const [mat, setMat] = useState("steel");
  const firstFrame = useRef(true);

  useEffect(() => {
    const el = mount.current;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = null;
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
    camera.position.set(130, 95, 150);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };

    const key = new THREE.DirectionalLight("#fff6e8", 2.4);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.bias = -0.0004;
    scene.add(key, new THREE.AmbientLight("#90a0c0", 0.35));

    const floor = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), new THREE.ShadowMaterial({ opacity: 0.45 }));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    const gc = document.createElement("canvas");
    gc.width = gc.height = 1024;
    const x = gc.getContext("2d");
    x.strokeStyle = "rgba(139,162,255,.45)";
    x.lineWidth = 2;
    for (let i = 0; i <= 32; i++) {
      const q = i * 32;
      x.beginPath(); x.moveTo(q, 0); x.lineTo(q, 1024); x.moveTo(0, q); x.lineTo(1024, q); x.stroke();
    }
    x.globalCompositeOperation = "destination-in";
    const rg = x.createRadialGradient(512, 512, 0, 512, 512, 512);
    rg.addColorStop(0, "#fff");
    rg.addColorStop(1, "rgba(255,255,255,0)");
    x.fillStyle = rg;
    x.fillRect(0, 0, 1024, 1024);

    const grid = new THREE.Mesh(
      new THREE.PlaneGeometry(1600, 1600),
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(gc), transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 })
    );
    grid.rotation.x = -Math.PI / 2;
    scene.add(grid);

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let raf;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      controls.update();
      renderer.render(scene, camera);
    };
    loop();

    S.current = { renderer, scene, camera, controls, key, floor, grid };
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, []);

  // Instant snap to viewpoint without locking or disabling OrbitControls
  const setView = (directionVector) => {
    const { camera, controls } = S.current;
    const f = S.current.fit;
    if (!f || !camera || !controls) return;

    const dir = new THREE.Vector3(...directionVector).normalize();
    const newPos = f.target.clone().add(dir.multiplyScalar(f.dist));

    camera.position.copy(newPos);
    controls.target.copy(f.target);
    controls.update();
  };

  useEffect(() => {
    if (!stlUrl) return;
    const { scene, camera, controls, key, floor, grid } = S.current;
    new STLLoader().load(stlUrl, (geo) => {
      geo.computeBoundingBox();
      geo.computeVertexNormals();

      const c = new THREE.Vector3();
      geo.boundingBox.getCenter(c);
      geo.translate(-c.x, -geo.boundingBox.min.y, -c.z);
      geo.computeBoundingBox();

      const m = MATERIALS[S.current.matKey || "steel"];
      const mesh = new THREE.Mesh(
        geo,
        new THREE.MeshStandardMaterial({
          color: m.color,
          metalness: m.metalness,
          roughness: m.roughness,
          wireframe: S.current.wire || false,
          envMapIntensity: 1.3
        })
      );
      mesh.castShadow = true;
      mesh.receiveShadow = true;

      if (S.current.mesh) {
        scene.remove(S.current.mesh);
        S.current.mesh.geometry.dispose();
      }
      scene.add(mesh);
      S.current.mesh = mesh;

      const size = new THREE.Vector3();
      geo.boundingBox.getSize(size);
      const r = Math.max(size.x, size.y, size.z);

      floor.position.y = grid.position.y = -0.05;
      key.position.set(r * 1.6, r * 2.5, r * 1.3);
      const sc = key.shadow.camera;
      sc.left = sc.bottom = -r * 2;
      sc.right = sc.top = r * 2;
      sc.near = 1;
      sc.far = r * 8;
      sc.updateProjectionMatrix();

      const dist = (r / 2) / Math.tan((camera.fov * Math.PI) / 360) * 1.85;
      const target = new THREE.Vector3(0, size.y / 2, 0);
      S.current.fit = { target, dist };

      if (firstFrame.current) {
        const initialDir = new THREE.Vector3(1, 0.7, 1.15).normalize();
        camera.position.copy(target.clone().add(initialDir.multiplyScalar(dist)));
        controls.target.copy(target);
        controls.update();
        firstFrame.current = false;
      }
    });
  }, [stlUrl]);

  useEffect(() => {
    S.current.matKey = mat;
    S.current.wire = wire;
    const mesh = S.current.mesh;
    if (!mesh) return;
    const m = MATERIALS[mat];
    mesh.material.color.set(m.color);
    mesh.material.metalness = m.metalness;
    mesh.material.roughness = m.roughness;
    mesh.material.wireframe = wire;
  }, [mat, wire, stlUrl]);

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
          <button key={n} onClick={() => setView(v)}>{n}</button>
        ))}
      </div>
      <div className="dock">
        <button data-tip={wire ? "Solid shading" : "Wireframe"} className={wire ? "on" : ""} onClick={() => setWire((w) => !w)}>
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
        {Object.entries(MATERIALS).map(([k, m]) => (
          <button
            key={k}
            className={mat === k ? "on" : ""}
            onClick={() => setMat(k)}
            style={{ whiteSpace: "nowrap", flexShrink: 0 }}
          >
            <i style={{ background: m.color }} />
            {m.name}
          </button>
        ))}
      </div>
      {!stlUrl && <div className="empty">AWAITING GEOMETRY - DESCRIBE A PART TO COMPILE</div>}
      {busy && <div className="empty" style={{ background: "#050607aa" }}>COMPILING B-REP ...</div>}
    </div>
  );
}
