import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

const MATERIAL_PRESETS = {
  steel: { color: 0x94a3b8, metalness: 0.75, roughness: 0.28 },
  aluminum: { color: 0xe2e8f0, metalness: 0.55, roughness: 0.35 },
  brass: { color: 0xf59e0b, metalness: 0.8, roughness: 0.3 },
  copper: { color: 0xf97316, metalness: 0.85, roughness: 0.25 },
};

export default function CadViewport({ stlUrl, materialType = "steel", wireframe = false, onResetViewRef }) {
  const mountRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const controlsRef = useRef(null);
  const meshRef = useRef(null);
  const initialCamRef = useRef({ pos: new THREE.Vector3(), target: new THREE.Vector3() });

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0x0a0f1d);

    const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 2000);
    cameraRef.current = camera;
    camera.position.set(80, 80, 80);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controlsRef.current = controls;
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;

    // Studio 4-Point Lighting Rig
    scene.add(new THREE.AmbientLight(0xffffff, 0.65));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.2);
    keyLight.position.set(100, 150, 100);
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight(0x38bdf8, 0.6);
    fillLight.position.set(-100, 50, -100);
    scene.add(fillLight);
    const rimLight = new THREE.DirectionalLight(0x818cf8, 0.4);
    rimLight.position.set(0, -100, 50);
    scene.add(rimLight);

    const grid = new THREE.GridHelper(200, 40, 0x1e293b, 0x0f172a);
    grid.position.y = -0.1;
    scene.add(grid);

    // Responsive Canvas ResizeObserver
    const resizeObserver = new ResizeObserver(() => {
      if (!container || !renderer || !camera) return;
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    });
    resizeObserver.observe(container);

    let animId;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      resizeObserver.disconnect();
      if (container && renderer.domElement) container.removeChild(renderer.domElement);
      renderer.dispose();
    };
  }, []);

  // STL Mesh Loader with Scale-Adaptive Auto-Framing
  useEffect(() => {
    if (!stlUrl || !sceneRef.current) return;
    const loader = new STLLoader();

    loader.load(
      stlUrl,
      (geometry) => {
        geometry.computeVertexNormals();
        geometry.center();

        if (meshRef.current) {
          sceneRef.current.remove(meshRef.current);
          meshRef.current.geometry.dispose();
          meshRef.current.material.dispose();
        }

        const preset = MATERIAL_PRESETS[materialType] || MATERIAL_PRESETS.steel;
        const material = new THREE.MeshPhysicalMaterial({
          color: preset.color,
          metalness: preset.metalness,
          roughness: preset.roughness,
          wireframe: wireframe,
          side: THREE.DoubleSide,
        });

        const mesh = new THREE.Mesh(geometry, material);
        meshRef.current = mesh;
        sceneRef.current.add(mesh);

        geometry.computeBoundingSphere();
        const sphere = geometry.boundingSphere;
        const radius = sphere ? sphere.radius : 40;

        const camera = cameraRef.current;
        const controls = controlsRef.current;
        if (camera && controls) {
          camera.near = Math.max(0.1, radius * 0.01);
          camera.far = Math.max(1000, radius * 80);
          camera.updateProjectionMatrix();

          const dist = radius * 2.8;
          camera.position.set(dist, dist * 0.8, dist);
          controls.target.set(0, 0, 0);
          controls.update();

          initialCamRef.current.pos.copy(camera.position);
          initialCamRef.current.target.copy(controls.target);
        }
      },
      undefined,
      (err) => console.error("STL Load Error:", err)
    );
  }, [stlUrl]);

  // Material & Wireframe Updates
  useEffect(() => {
    if (!meshRef.current) return;
    const preset = MATERIAL_PRESETS[materialType] || MATERIAL_PRESETS.steel;
    meshRef.current.material.color.setHex(preset.color);
    meshRef.current.material.metalness = preset.metalness;
    meshRef.current.material.roughness = preset.roughness;
    meshRef.current.material.wireframe = wireframe;
    meshRef.current.material.needsUpdate = true;
  }, [materialType, wireframe]);

  if (onResetViewRef) {
    onResetViewRef.current = () => {
      if (cameraRef.current && controlsRef.current) {
        cameraRef.current.position.copy(initialCamRef.current.pos);
        controlsRef.current.target.copy(initialCamRef.current.target);
        controlsRef.current.update();
      }
    };
  }

  return <div ref={mountRef} className="w-full h-full relative overflow-hidden" />;
}
