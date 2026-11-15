import { Canvas, type ThreeEvent, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { create } from "zustand";
import { type AlertView, SEVERITY } from "../domain/alerts";
import type { Layout, Tramo } from "../domain/layout";
import { tramoLabel, tramoName, useT } from "../i18n";
import type { DayRun } from "../sim/day";
import type { LineModel } from "../state/line";
import { useUI } from "../state/ui";
import { CameraRig, type Insets, view } from "./CameraRig";
import { Dynamic } from "./Dynamic";
import { type Plant, wallSpots } from "./models";
import { ENV, type Theme } from "./palette";

/** Estación bajo el puntero, para el rótulo flotante. */
export const useHover = create<{ op: string | null; x: number; y: number }>(() => ({ op: null, x: 0, y: 0 }));

const hex = (n: number) => `#${n.toString(16).padStart(6, "0")}`;

/** Luz principal con sombras. Sigue a la cámara para que la sombra sea nítida donde se está mirando. */
function Sun() {
  const light = useRef<THREE.DirectionalLight>(null);
  const scene = useThree((s) => s.scene);
  useEffect(() => {
    const l = light.current;
    if (!l) return;
    scene.add(l.target);
    return () => void scene.remove(l.target);
  }, [scene]);
  useFrame(() => {
    const l = light.current;
    if (!l) return;
    const half = Math.min(180, Math.max(30, view.span * 0.62));
    // Se mueve a saltos de un metro: si no, la sombra tiembla al arrastrar.
    const x = Math.round(view.x);
    const z = Math.round(view.z);
    l.position.set(x - 38, 70, z + 30);
    l.target.position.set(x, 0, z);
    l.target.updateMatrixWorld();
    const cam = l.shadow.camera;
    if (cam.right !== half) {
      cam.left = -half; cam.right = half; cam.top = half; cam.bottom = -half;
      cam.updateProjectionMatrix();
    }
  });
  return (
    <directionalLight ref={light} castShadow intensity={2.0} color={0xfff6ea} shadow-mapSize={[2048, 2048]} shadow-bias={-0.0006} shadow-normalBias={0.04}>
      <orthographicCamera attach="shadow-camera" args={[-60, 60, 60, -60, 1, 260]} />
    </directionalLight>
  );
}

/** Lo que no se mueve: nave, cintas y máquinas, en tres mallas. */
function StaticPlant({ plant }: { plant: Plant }) {
  const mats = useMemo(
    () => [
      new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8, metalness: 0.03 }),
      new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.45, metalness: 0.3 }),
      new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.15, metalness: 0, transparent: true, opacity: 0.3, depthWrite: false }),
    ],
    [],
  );
  useEffect(() => () => mats.forEach((m) => m.dispose()), [mats]);
  useEffect(() => () => plant.geos.forEach((geo) => geo?.dispose()), [plant]);
  return (
    <group>
      {plant.geos.map((geo, k) => (geo ? <mesh key={k} geometry={geo} material={mats[k]} castShadow={k < 2} receiveShadow={k < 2} /> : null))}
    </group>
  );
}

function plate(text: string, opts: { w: number; h: number; font: string; fg: string; bg?: string; sub?: string }): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = opts.w;
  c.height = opts.h;
  const ctx = c.getContext("2d")!;
  if (opts.bg) {
    ctx.fillStyle = opts.bg;
    ctx.beginPath();
    ctx.roundRect(2, 2, opts.w - 4, opts.h - 4, opts.h * 0.24);
    ctx.fill();
  }
  ctx.fillStyle = opts.fg;
  ctx.textBaseline = "middle";
  ctx.font = opts.font;
  if (opts.sub) {
    ctx.textAlign = "left";
    ctx.fillText(text, 8, opts.h * 0.34);
    ctx.font = opts.font.replace(/\d+px/, (m) => `${Math.round(parseInt(m) * 0.5)}px`).replace("800", "600");
    ctx.fillText(opts.sub, 10, opts.h * 0.8);
  } else {
    ctx.textAlign = "center";
    ctx.fillText(text, opts.w / 2, opts.h / 2 + 2, opts.w - 24);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

const FONT = '"Inter Variable", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

/** Rótulos pintados en el suelo: el nombre de cada puesto delante de él y el de cada tramo en el pasillo. */
function Labels({ model, lay, tramos, theme }: { model: LineModel; lay: Layout; tramos: Tramo[]; theme: Theme }) {
  const T = useT();
  const { g } = model;
  const names = useMemo(() => {
    const out: { key: string; x: number; z: number; w: number; tex: THREE.CanvasTexture }[] = [];
    const add = (key: string, text: string, x: number, z: number, w = 2.0) =>
      out.push({ key, x, z, w, tex: plate(text, { w: 320, h: 80, font: `700 44px ${FONT}`, fg: "#ffffff", bg: "rgba(13,13,13,0.86)" }) });
    for (const n of g.nodes) {
      const p = lay.poses[n.i];
      if (lay.face[n.i] === 0) add(n.op, n.op, p.x, p.z + 1.98);
      else add(n.op, n.op, p.x - 2.55, p.z);
    }
    for (const a of g.aux) add(a.op, a.op, lay.aux[a.i].x, lay.aux[a.i].z + 0.98, 1.7);
    lay.towers.forEach((t, k) => add(`pulmon${k}`, T.scene.buffer, t.x, t.z + 1.85, 1.7));
    return out;
  }, [g, lay, T]);
  useEffect(() => () => names.forEach((n) => n.tex.dispose()), [names]);

  const titles = useMemo(
    () => tramos.map((t) => ({
      key: `${t.i}-${t.x0}-${t.z0}`, title: t.title, sep: t.sep,
      tex: plate(tramoName(T, t), { w: 1024, h: 160, font: `600 84px ${FONT}`, fg: ENV[theme].title, sub: tramoLabel(T, t) }),
    })),
    [tramos, theme, T],
  );
  useEffect(() => () => titles.forEach((t) => t.tex.dispose()), [titles]);

  return (
    <group>
      {names.map((n) => (
        <mesh key={n.key} position={[n.x, 0.05, n.z]} rotation-x={-Math.PI / 2}>
          <planeGeometry args={[n.w, n.w / 4]} />
          <meshBasicMaterial map={n.tex} transparent depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
      {titles.map((t) => (
        <group key={t.key}>
          <mesh position={[t.title.x, 0.03, t.title.z]} rotation-x={-Math.PI / 2}>
            <planeGeometry args={[10, 1.5625]} />
            <meshBasicMaterial map={t.tex} transparent depthWrite={false} toneMapped={false} />
          </mesh>
          {t.sep ? (
            <mesh position={[t.sep.x, 0.02, (t.sep.z0 + t.sep.z1) / 2]} rotation-x={-Math.PI / 2}>
              <planeGeometry args={[0.1, t.sep.z1 - t.sep.z0]} />
              <meshBasicMaterial color={ENV[theme].floorLine} toneMapped={false} />
            </mesh>
          ) : null}
        </group>
      ))}
    </group>
  );
}

function markerTexture(color: string, glyph: string, unread: boolean): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const ctx = c.getContext("2d")!;
  ctx.beginPath();
  ctx.arc(64, 64, 54, 0, Math.PI * 2);
  ctx.fillStyle = unread ? color : "#ffffff";
  ctx.fill();
  ctx.lineWidth = 9;
  ctx.strokeStyle = unread ? "#ffffff" : color;
  ctx.stroke();
  ctx.fillStyle = unread ? "#ffffff" : color;
  ctx.font = `800 78px ${FONT}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(glyph, 64, 69);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/**
 * Carteles en la pared del fondo con los logos de HORSE y de la Cátedra de Industria Inteligente
 * (Comillas ICAI), alternados cada 28 m. HORSE, sobre blanco (su logo es negro); la cátedra, su
 * logo en blanco a sangre sobre el azul ICAI. Los ficheros van con el propio bundle (public/brand)
 * y se pintan a buena resolución en un canvas.
 */
const ICAI_BLUE = "#014593";
const BRANDS: { src: string; aspect: number; bg: string; cover: boolean }[] = [
  { src: "brand/horse.svg", aspect: 457.7 / 207.9, bg: "#ffffff", cover: false },
  { src: "brand/catedra-industria-inteligente.png", aspect: 288 / 125, bg: ICAI_BLUE, cover: true }, // blanco sobre transparente
];
const SIGN_W = 4.6;
const SIGN_H = 2.0;

async function brandTexture(src: string, aspect: number, bg: string, cover: boolean): Promise<THREE.CanvasTexture> {
  const img = new Image();
  img.src = `${import.meta.env.BASE_URL}${src}`;
  await img.decode();
  const W = 1024;
  const H = Math.round((W * SIGN_H) / SIGN_W);
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const ctx = c.getContext("2d")!;
  ctx.beginPath();
  ctx.roundRect(0, 0, W, H, 28);
  ctx.fillStyle = bg;
  ctx.fill();
  if (cover) {
    ctx.drawImage(img, 0, 0, W, H); // el logo ya trae sus márgenes: ocupa el cartel entero
  } else {
    const w = Math.min(W * 0.8, H * 0.66 * aspect);
    const h = w / aspect;
    ctx.drawImage(img, (W - w) / 2, (H - h) / 2, w, h);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function Brands({ lay }: { lay: Layout }) {
  const [tex, setTex] = useState<THREE.CanvasTexture[] | null>(null);
  useEffect(() => {
    let alive = true;
    let made: THREE.CanvasTexture[] = [];
    Promise.all(BRANDS.map((b) => brandTexture(b.src, b.aspect, b.bg, b.cover)))
      .then((t) => {
        made = t;
        if (alive) setTex(t);
        else t.forEach((x) => x.dispose());
      })
      .catch(() => {}); // sin logos la nave sigue igual
    return () => {
      alive = false;
      made.forEach((x) => x.dispose());
    };
  }, []);
  // Un hueco de cada dos, alternando: HORSE, la cátedra, HORSE…
  const spots = useMemo(() => wallSpots(lay).filter((_, k) => k % 2 === 1), [lay]);
  if (!tex) return null;
  return (
    <group>
      {spots.map((s, k) => (
        <mesh key={`${s.x}`} position={[s.x, s.y, s.z]}>
          <planeGeometry args={[SIGN_W, SIGN_H]} />
          <meshBasicMaterial map={tex[k % tex.length]} transparent toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}

/** Icono de aviso flotando sobre la máquina: relleno si está sin leer, hueco si ya se ha visto. */
function Markers({ model, plant, alerts }: { model: LineModel; plant: Plant; alerts: Map<string, AlertView> }) {
  const { g } = model;
  const tex = useMemo(() => {
    const out = new Map<string, THREE.CanvasTexture>();
    for (const [sev, s] of Object.entries(SEVERITY)) {
      for (const unread of [true, false]) out.set(`${sev}${unread}`, markerTexture(s.css, sev === "info" ? "i" : "!", unread));
    }
    return out;
  }, []);
  useEffect(() => () => tex.forEach((t) => t.dispose()), [tex]);
  const select = useUI((s) => s.select);
  return (
    <group>
      {[...alerts.values()].map((a) => {
        const node = g.index.get(a.op);
        const aux = g.auxIndex.get(a.op);
        const rig = node != null ? plant.rigs[node] : aux != null ? plant.auxRigs[aux] : null;
        if (!rig) return null;
        const size = a.unread ? 0.95 : 0.7;
        return (
          <sprite
            key={a.op}
            position={[rig.center.x, rig.top + 0.35, rig.center.z]}
            scale={[size, size, 1]}
            renderOrder={5}
            onClick={(e) => {
              if (e.delta > 5) return;
              e.stopPropagation();
              select(a.op);
            }}
          >
            <spriteMaterial map={tex.get(`${a.severity}${a.unread}`)} depthTest={false} transparent toneMapped={false} />
          </sprite>
        );
      })}
    </group>
  );
}

/** Zonas invisibles para elegir una estación con el ratón o el dedo. */
function Picker({ model, plant }: { model: LineModel; plant: Plant }) {
  const { g } = model;
  const ref = useRef<THREE.InstancedMesh>(null);
  const total = g.nodes.length + g.aux.length;
  const geo = useMemo(() => new THREE.BoxGeometry(1, 1, 1), []);
  const mat = useMemo(() => new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false }), []);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    plant.rigs.forEach((rig, i) => {
      m.compose(new THREE.Vector3(rig.center.x, 1.4, rig.center.z), q.setFromAxisAngle(up, rig.rot), new THREE.Vector3(2.7, 2.8, 2.8));
      mesh.setMatrixAt(i, m);
    });
    plant.auxRigs.forEach((rig, k) => {
      m.compose(new THREE.Vector3(rig.center.x, 1.5, rig.center.z - 0.5), q.identity(), new THREE.Vector3(1.1, 3.0, 2.2));
      mesh.setMatrixAt(g.nodes.length + k, m);
    });
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [plant, g]);
  useEffect(() => () => {
    geo.dispose();
    mat.dispose();
  }, [geo, mat]);

  const opAt = (id: number | undefined) => (id == null ? null : id < g.nodes.length ? g.nodes[id].op : g.aux[id - g.nodes.length]?.op ?? null);
  const hover = (e: ThreeEvent<PointerEvent>) => {
    if (e.pointerType === "touch") return;
    e.stopPropagation();
    useHover.setState({ op: opAt(e.instanceId), x: e.clientX, y: e.clientY });
    document.body.style.cursor = "pointer";
  };
  const leave = () => {
    useHover.setState({ op: null });
    document.body.style.cursor = "";
  };
  return (
    <instancedMesh
      key={total}
      ref={ref}
      args={[geo, mat, total]}
      frustumCulled={false}
      onPointerMove={hover}
      onPointerOut={leave}
      onClick={(e) => {
        if (e.delta > 5) return; // era un arrastre
        e.stopPropagation();
        const op = opAt(e.instanceId);
        if (op) useUI.getState().select(op);
      }}
    />
  );
}

export interface SceneProps {
  model: LineModel;
  lay: Layout; // la planta que se dibuja (recta o serpenteada); la simulación usa siempre model.lay
  theme: Theme;
  plant: Plant;
  run: DayRun;
  tramos: Tramo[];
  insets: Insets;
  alerts: Map<string, AlertView>;
}

export function LineScene({ model, lay, theme, plant, run, tramos, insets, alerts }: SceneProps) {
  return (
    <Canvas
      className="scene"
      shadows
      flat
      dpr={[1, 2]}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onPointerMissed={(e) => {
        if (e.type === "click") useUI.getState().select(null);
      }}
    >
      <color attach="background" args={[hex(ENV[theme].bg)]} />
      <ambientLight intensity={1.25} />
      <hemisphereLight args={[0xffffff, 0xb4b4b4, 0.7]} />
      <Sun />
      <StaticPlant plant={plant} />
      <Brands lay={lay} />
      <Labels model={model} lay={lay} tramos={tramos} theme={theme} />
      <Dynamic model={model} lay={lay} theme={theme} plant={plant} run={run} />
      <Markers model={model} plant={plant} alerts={alerts} />
      <Picker model={model} plant={plant} />
      <CameraRig model={model} lay={lay} tramos={tramos} insets={insets} />
    </Canvas>
  );
}
