import {
  ACESFilmicToneMapping,
  CanvasTexture,
  Color,
  DirectionalLight,
  Group,
  Mesh,
  MeshPhysicalMaterial,
  PerspectiveCamera,
  PMREMGenerator,
  PointLight,
  RepeatWrapping,
  Scene,
  SRGBColorSpace,
  WebGLRenderer,
} from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { buildBallGeometry } from "./ballGeometry";

// Real-time 3D soccer ball (loaded only via dynamic import, only on wide, motion-OK,
// non-Save-Data viewports - see SceneBall.tsx). Everything created here is disposed by
// dispose(). No logos, text or brand patterns.

// Rendering the ball on a software rasterizer costs 50-80ms a frame (measured), so those get the static image.
const SOFTWARE_RENDERER = /swiftshader|llvmpipe|softpipe|software/i;

export const MAX_DPR = 1.5;
export const MAX_FPS = 30;
export const ROTATION_RAD_PER_SEC = 0.05;

// Tileable multi-octave value noise -> a grey canvas used as the leather-grain bump map.
function grainTexture(size = 256): CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2d canvas unavailable");
  const img = ctx.createImageData(size, size);
  let seed = 1337;
  const rand = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
  const octaves = [8, 16, 32, 64].map((cells) => {
    const grid = Float32Array.from({ length: cells * cells }, rand);
    return { cells, grid };
  });
  const smooth = (t: number) => t * t * (3 - 2 * t);
  const sample = (o: { cells: number; grid: Float32Array }, x: number, y: number) => {
    const fx = (x / size) * o.cells;
    const fy = (y / size) * o.cells;
    const x0 = Math.floor(fx) % o.cells;
    const y0 = Math.floor(fy) % o.cells;
    const x1 = (x0 + 1) % o.cells;
    const y1 = (y0 + 1) % o.cells;
    const tx = smooth(fx - Math.floor(fx));
    const ty = smooth(fy - Math.floor(fy));
    const g = (xx: number, yy: number) => o.grid[yy * o.cells + xx];
    return (g(x0, y0) * (1 - tx) + g(x1, y0) * tx) * (1 - ty) + (g(x0, y1) * (1 - tx) + g(x1, y1) * tx) * ty;
  };
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let v = 0;
      let amp = 0.5;
      let total = 0;
      for (const o of octaves) {
        v += sample(o, x, y) * amp;
        total += amp;
        amp *= 0.55;
      }
      const grey = Math.round((v / total) * 255);
      const i = (y * size + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = grey;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const texture = new CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = RepeatWrapping;
  texture.colorSpace = SRGBColorSpace;
  return texture;
}

export type BallOptions = {
  exposure?: number;
  // For the one-off static-fallback render: keep the pixels readable after drawing.
  preserveDrawingBuffer?: boolean;
};

export type BallHandle = {
  resize: (cssWidth: number, cssHeight: number) => void;
  setActive: (active: boolean) => void; // false pauses the loop entirely
  renderAt: (rotationY: number) => void; // deterministic single frame (used for the static image)
  stats: () => { frames: number; renderer: string };
  dispose: () => void;
};

export function createBall(canvas: HTMLCanvasElement, options: BallOptions = {}): BallHandle {
  const renderer = new WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
    powerPreference: "low-power",
    failIfMajorPerformanceCaveat: true,
    preserveDrawingBuffer: options.preserveDrawingBuffer ?? false,
  });
  const gl = renderer.getContext();
  const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
  const gpu = debugInfo ? String(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL)) : "";
  if (SOFTWARE_RENDERER.test(gpu)) {
    renderer.dispose();
    renderer.forceContextLoss();
    throw new Error(`software WebGL (${gpu}) - using the static ball`);
  }
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_DPR));
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = options.exposure ?? 0.8;

  const scene = new Scene();
  const pmrem = new PMREMGenerator(renderer);
  const roomEnv = new RoomEnvironment();
  const envTarget = pmrem.fromScene(roomEnv, 0.04);
  scene.environment = envTarget.texture;
  scene.environmentIntensity = 0.55;

  // Cool key from the upper left front, blue rim from behind on the right; the lower-left
  // is left to fall off into shadow so the ball reads as a lit object.
  const key = new DirectionalLight(new Color("#dbe8ff"), 2.6);
  key.position.set(-3, 4, 5);
  const rim = new PointLight(new Color("#3d7bff"), 55, 0, 2);
  rim.position.set(4.2, 1.5, -3);
  scene.add(key, rim);

  const grain = grainTexture();
  const geometry = buildBallGeometry();
  const material = new MeshPhysicalMaterial({
    vertexColors: true,
    roughness: 0.42,
    metalness: 0,
    clearcoat: 0.55,
    clearcoatRoughness: 0.22,
    bumpMap: grain,
    bumpScale: 0.7,
  });
  const ball = new Mesh(geometry, material);
  const group = new Group();
  group.add(ball);
  group.rotation.x = 0.35;
  group.rotation.z = -0.2;
  scene.add(group);

  const camera = new PerspectiveCamera(28, 1, 0.1, 50);
  camera.position.set(0, 0, 6.2);

  let width = 1;
  let height = 1;
  let spin = 0.6;
  let active = true;
  let raf = 0;
  let last = 0;
  let frames = 0;
  let disposed = false;

  const draw = () => {
    group.rotation.y = spin;
    renderer.render(scene, camera);
    frames++;
  };

  const tick = (now: number) => {
    if (disposed || !active) return;
    raf = requestAnimationFrame(tick);
    const dt = now - last;
    if (dt < 1000 / MAX_FPS - 1) return; // 30fps cap
    last = now;
    spin += ROTATION_RAD_PER_SEC * Math.min(dt, 100) / 1000;
    draw();
  };

  const start = () => {
    cancelAnimationFrame(raf);
    last = performance.now();
    raf = requestAnimationFrame(tick);
  };
  start();

  return {
    resize(cssWidth, cssHeight) {
      width = Math.max(1, Math.round(cssWidth));
      height = Math.max(1, Math.round(cssHeight));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      draw();
    },
    setActive(next) {
      if (next === active || disposed) return;
      active = next;
      if (active) start();
      else cancelAnimationFrame(raf);
    },
    renderAt(rotationY) {
      spin = rotationY;
      draw();
    },
    stats() {
      const gl = renderer.getContext();
      const info = gl.getExtension("WEBGL_debug_renderer_info");
      return { frames, renderer: info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : "unknown" };
    },
    dispose() {
      disposed = true;
      cancelAnimationFrame(raf);
      geometry.dispose();
      material.dispose();
      grain.dispose();
      envTarget.dispose();
      roomEnv.traverse((o) => {
        const m = o as Mesh;
        if (m.isMesh) {
          m.geometry.dispose();
          (Array.isArray(m.material) ? m.material : [m.material]).forEach((mat) => mat.dispose());
        }
      });
      pmrem.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}
