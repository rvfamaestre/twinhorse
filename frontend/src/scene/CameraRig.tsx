import { MapControls, OrthographicCamera } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { MapControls as MapControlsImpl } from "three-stdlib";
import type { Layout, Tramo } from "../domain/layout";
import type { LineModel } from "../state/line";
import { useUI } from "../state/ui";

/**
 * Cámara isométrica fija (no gira: así nadie se pierde). Se mueve de tramo en tramo con un
 * vuelo corto, y dentro de la escena se puede arrastrar y hacer zoom con libertad.
 * `insets` es el sitio que ocupan los paneles: la cámara encuadra en lo que queda libre.
 *
 * Ratón y trackpad:
 * - Arrastrar mueve la planta. Un arrastre largo (o un deslizamiento horizontal con dos dedos)
 *   pasa al tramo siguiente o al anterior, salvo con zoom de cerca, donde el arrastre es libre.
 * - Rueda, deslizar dos dedos en vertical o pellizcar: zoom hacia el puntero, proporcional al gesto.
 * - Lo que se mueve a mano no se deshace cuando cambia el alto de una barra o se abre un panel.
 */
export interface Insets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

const AZ = 0.42; // giro respecto al frente de la línea
const EL = 0.62; // inclinación
const DIST = 220;
const HEIGHT = 3.3; // alto de lo que hay que encuadrar
const DIR = new THREE.Vector3(-Math.sin(AZ) * Math.cos(EL), Math.sin(EL), Math.cos(AZ) * Math.cos(EL));
const RIGHT = new THREE.Vector3(Math.cos(AZ), 0, Math.sin(AZ));
const FWD = new THREE.Vector3(Math.sin(AZ), 0, -Math.cos(AZ));
const SIN_EL = Math.sin(EL);
const COS_EL = Math.cos(EL);
const NONE: Insets = { top: 0, right: 0, bottom: 0, left: 0 };
const TRAMO_FILL = 0.8;
const FREE_ZOOM = 1.25; // por encima de este zoom (respecto al encuadre del tramo) el arrastre no cambia de tramo
const SWIPE_IDLE_MS = 250;
// Lo que ocupa una estación alrededor de su centro (m): ancho, fondo, rótulo delante y alto con la baliza y el aviso.
const SEL_BOX = { x: 2.2, back: -1.6, front: 2.6, top: 3.9 };
const SEL_PAD_X = 64; // px libres a los lados: ahí van los botones de tramo anterior y siguiente
const SEL_PAD_Y = 16;

/** Lo que ve la cámara ahora, para quien lo necesite sin pasar por React (la luz, por ejemplo). */
export const view = { x: 0, z: 0, zoom: 30, span: 60 };

interface Box {
  x0: number;
  x1: number;
  z0: number;
  z1: number;
}

/** Punto de mira y zoom para que una zona de la planta quepa en la parte libre de la pantalla. */
function fit(box: Box, w: number, h: number, ins: Insets, fill: number): { target: THREE.Vector3; zoom: number } {
  let r0 = Infinity, r1 = -Infinity, u0 = Infinity, u1 = -Infinity;
  for (const x of [box.x0, box.x1]) {
    for (const z of [box.z0, box.z1]) {
      for (const y of [0, HEIGHT]) {
        const r = x * RIGHT.x + z * RIGHT.z;
        const u = (x * FWD.x + z * FWD.z) * SIN_EL + y * COS_EL;
        r0 = Math.min(r0, r); r1 = Math.max(r1, r); u0 = Math.min(u0, u); u1 = Math.max(u1, u);
      }
    }
  }
  const availW = Math.max(160, w - ins.left - ins.right);
  const availH = Math.max(160, h - ins.top - ins.bottom);
  const zoom = Math.min((availW * fill) / (r1 - r0), (availH * 0.94) / (u1 - u0));
  const r = (r0 + r1) / 2 - (ins.left - ins.right) / 2 / zoom;
  const u = (u0 + u1) / 2 - (ins.bottom - ins.top) / 2 / zoom;
  return { target: new THREE.Vector3().addScaledVector(RIGHT, r).addScaledVector(FWD, u / SIN_EL), zoom };
}

/** Tramo más cercano a un punto de la planta (el que lo contiene, si lo hay). */
function nearestTramo(tramos: Tramo[], x: number, z: number): number {
  let best = 0;
  let bd = Infinity;
  for (const t of tramos) {
    const cx = Math.min(t.x1, Math.max(t.x0, x));
    const cz = Math.min(t.z1, Math.max(t.z0, z));
    const d = (x - cx) ** 2 + (z - cz) ** 2;
    if (d < bd - 1e-9) {
      bd = d;
      best = t.i;
    }
  }
  return best;
}

interface Gesture {
  x: number;
  z: number;
  tramo: number;
}

export function CameraRig({ model, lay, tramos, insets }: { model: LineModel; lay: Layout; tramos: Tramo[]; insets: Insets }) {
  const controls = useRef<MapControlsImpl>(null);
  const { camera, size, gl } = useThree();
  const goal = useRef<{ target: THREE.Vector3; zoom: number } | null>(null);
  const first = useRef(true);
  const manual = useRef(false); // se ha movido a mano desde el último vuelo
  const seen = useRef<{ fly: number; tramos: Tramo[] | null; lay: Layout | null }>({ fly: -1, tramos: null, lay: null });
  const gesture = useRef<Gesture | null>(null);
  const swipe = useRef<(Gesture & { dx: number; timer: ReturnType<typeof setTimeout> | null }) | null>(null);
  const flyId = useUI((s) => s.flyId);
  const { g } = model;

  const limits = useMemo(() => {
    const all = fit(lay.bounds, size.width, size.height, NONE, 0.98);
    return { min: all.zoom * 0.75, max: 150 };
  }, [lay, size.width, size.height]);

  const centerOf = (op: string | null): { x: number; z: number } | null => {
    if (!op) return null;
    const node = g.index.get(op);
    if (node != null) return lay.poses[node];
    const aux = g.auxIndex.get(op);
    return aux != null ? lay.aux[aux] : null;
  };

  useEffect(() => {
    const ui = useUI.getState();
    const ctl = controls.current;
    const cam = camera as THREE.OrthographicCamera;
    if (!ctl || !tramos.length) return;
    const fresh = seen.current.fly !== flyId || seen.current.tramos !== tramos;
    if (seen.current.lay && seen.current.lay !== lay) first.current = true; // planta nueva: se salta sin vuelo
    seen.current = { fly: flyId, tramos, lay };
    // Solo han cambiado las barras, un panel o la ventana: lo movido a mano se respeta.
    if (!fresh && manual.current) return;

    if (ui.flyKind === "reveal" && !first.current) {
      // Se ha elegido una estación en la escena: la cámara se mueve lo justo para que se vea entera
      // (de la base al icono de aviso, con su rótulo) en el hueco que dejan las barras y la ficha.
      const c = centerOf(ui.selected);
      if (!c) return;
      const from = goal.current?.target ?? ctl.target;
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (const ox of [-SEL_BOX.x, SEL_BOX.x]) {
        for (const oz of [SEL_BOX.back, SEL_BOX.front]) {
          for (const y of [0, SEL_BOX.top]) {
            const dx = c.x + ox - from.x;
            const dz = c.z + oz - from.z;
            const sx = size.width / 2 + (dx * RIGHT.x + dz * RIGHT.z) * cam.zoom;
            const sy = size.height / 2 - ((dx * FWD.x + dz * FWD.z) * SIN_EL + y * COS_EL) * cam.zoom;
            x0 = Math.min(x0, sx); x1 = Math.max(x1, sx); y0 = Math.min(y0, sy); y1 = Math.max(y1, sy);
          }
        }
      }
      const left = insets.left + SEL_PAD_X;
      const right = size.width - insets.right - SEL_PAD_X;
      const top = insets.top + SEL_PAD_Y;
      const bottom = size.height - insets.bottom - SEL_PAD_Y;
      // Si no cabe entera (mucho zoom), se centra.
      const px = x1 - x0 > right - left ? (x0 + x1 - left - right) / 2 : Math.max(0, x1 - right) + Math.min(0, x0 - left);
      const py = y1 - y0 > bottom - top ? (y0 + y1 - top - bottom) / 2 : Math.max(0, y1 - bottom) + Math.min(0, y0 - top);
      if (Math.abs(px) > 0.5 || Math.abs(py) > 0.5) {
        goal.current = {
          zoom: cam.zoom,
          target: ctl.target.clone().addScaledVector(RIGHT, px / cam.zoom).addScaledVector(FWD, -py / cam.zoom / SIN_EL),
        };
      }
      return;
    }

    manual.current = false;
    if (ui.overview) {
      goal.current = fit(lay.bounds, size.width, size.height, insets, 0.97);
      return;
    }
    let ti = Math.min(ui.tramo, tramos.length - 1);
    if (ui.flyKind === "focus" && ui.selected) {
      const node = g.index.get(ui.selected);
      const aux = g.auxIndex.get(ui.selected);
      const found = tramos.findIndex((t) => (node != null && t.nodes.includes(node)) || (aux != null && t.aux.includes(aux)));
      if (found >= 0) ti = found;
    }
    if (ti !== ui.tramo) ui.panTramo(ti);
    goal.current = fit(tramos[ti], size.width, size.height, insets, TRAMO_FILL);
  }, [flyId, tramos, lay, size.width, size.height, insets.top, insets.right, insets.bottom, insets.left]);

  useFrame((_, dt) => {
    const ctl = controls.current;
    const cam = camera as THREE.OrthographicCamera;
    if (!ctl) return;
    const to = goal.current;
    if (to) {
      const k = first.current ? 1 : 1 - Math.exp(-Math.min(dt, 0.1) * 5.5);
      ctl.target.lerp(to.target, k);
      cam.zoom += (to.zoom - cam.zoom) * k;
      if (ctl.target.distanceTo(to.target) < 0.02 && Math.abs(to.zoom - cam.zoom) < 0.002 * to.zoom) {
        ctl.target.copy(to.target);
        cam.zoom = to.zoom;
        goal.current = null;
      }
      first.current = false;
      cam.position.copy(ctl.target).addScaledVector(DIR, DIST);
      cam.updateProjectionMatrix();
      ctl.update();
    }
    view.x = ctl.target.x;
    view.z = ctl.target.z;
    view.zoom = cam.zoom;
    view.span = size.width / cam.zoom;
  });

  const onChange = () => {
    const ctl = controls.current;
    if (!ctl || goal.current) return; // durante un vuelo manda el vuelo
    // No se deja salir de la nave.
    const b = lay.bounds;
    const x = Math.min(b.x1, Math.max(b.x0, ctl.target.x));
    const z = Math.min(b.z1, Math.max(b.z0, ctl.target.z));
    if (x !== ctl.target.x || z !== ctl.target.z) {
      ctl.target.set(x, 0, z);
      camera.position.copy(ctl.target).addScaledVector(DIR, DIST);
    }
    // Al moverse, el tramo activo es el que queda en el centro.
    const ui = useUI.getState();
    if (ui.overview || !tramos.length) return;
    ui.panTramo(nearestTramo(tramos, x, z));
  };

  /** Fin de un arrastre o de un deslizamiento: si ha sido largo, al tramo de al lado; si no, se vuelve a encuadrar. */
  const settle = (from: Gesture) => {
    const ui = useUI.getState();
    const ctl = controls.current;
    const cam = camera as THREE.OrthographicCamera;
    const t = tramos[from.tramo];
    if (!ctl || !t || ui.overview) return;
    if (cam.zoom > fit(t, size.width, size.height, insets, TRAMO_FILL).zoom * FREE_ZOOM) return; // de cerca, arrastre libre
    const ddx = ctl.target.x - from.x;
    const ddz = ctl.target.z - from.z;
    const sx = (ddx * RIGHT.x + ddz * RIGHT.z) * cam.zoom; // píxeles que se ha movido la planta
    const sy = (ddx * FWD.x + ddz * FWD.z) * SIN_EL * cam.zoom;
    if (Math.hypot(sx, sy) < 6) return;
    const now = nearestTramo(tramos, ctl.target.x, ctl.target.z);
    const long = Math.abs(sx) > Math.max(60, size.width * 0.12) && Math.abs(sx) > Math.abs(sy);
    if (now !== from.tramo) ui.goTramo(now);
    else if (long) ui.goTramo(Math.min(tramos.length - 1, Math.max(0, from.tramo + (sx > 0 ? 1 : -1))));
    else ui.goTramo(from.tramo);
  };

  // drei vuelve a conectar los controles (y corta el arrastre en curso) si cambian estas funciones;
  // la escena se repinta cuatro veces por segundo, así que se le pasan unas que no cambian nunca.
  const handlers = useRef({ change: () => {}, start: () => {}, end: () => {} });
  handlers.current = {
    change: () => onChange(),
    start: () => {
      goal.current = null;
      manual.current = true;
      gesture.current = controls.current ? here() : null;
      useUI.setState({ touched: true });
    },
    end: () => {
      const from = gesture.current;
      gesture.current = null;
      if (from) settle(from);
    },
  };
  const stable = useMemo(() => ({
    change: () => handlers.current.change(),
    start: () => handlers.current.start(),
    end: () => handlers.current.end(),
  }), []);

  const here = (): Gesture => ({ x: controls.current!.target.x, z: controls.current!.target.z, tramo: useUI.getState().tramo });

  // Rueda y trackpad: se atienden aquí (antes que los controles) para que el zoom sea proporcional al gesto.
  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const ctl = controls.current;
    const cam = camera as THREE.OrthographicCamera;
    if (!ctl) return;
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
    const dx = e.deltaX * unit;
    const dy = e.deltaY * unit;
    goal.current = null;
    manual.current = true;
    useUI.setState({ touched: true });

    if (!e.ctrlKey && Math.abs(dx) > Math.abs(dy) * 1.2) {
      // Dos dedos en horizontal: se recorre la línea, y al soltar se encuadra el tramo.
      if (!swipe.current) swipe.current = { ...here(), dx: 0, timer: null };
      const sw = swipe.current;
      sw.dx += dx;
      ctl.target.addScaledVector(RIGHT, dx / cam.zoom);
      cam.position.copy(ctl.target).addScaledVector(DIR, DIST);
      ctl.update();
      onChange();
      if (sw.timer) clearTimeout(sw.timer);
      sw.timer = setTimeout(() => {
        swipe.current = null;
        settle(sw);
      }, SWIPE_IDLE_MS);
      return;
    }

    // Pellizco (llega con ctrl) más sensible que la rueda o el deslizamiento vertical.
    const z0 = cam.zoom;
    const z1 = Math.min(limits.max, Math.max(limits.min, z0 * Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0015))));
    if (Math.abs(z1 - z0) < 1e-6) return;
    const rect = gl.domElement.getBoundingClientRect();
    const px = e.clientX - rect.left - rect.width / 2;
    const py = e.clientY - rect.top - rect.height / 2;
    const f = 1 / z0 - 1 / z1; // el punto bajo el puntero se queda quieto
    ctl.target.addScaledVector(RIGHT, px * f).addScaledVector(FWD, (-py / SIN_EL) * f);
    ctl.target.y = 0;
    cam.zoom = z1;
    cam.position.copy(ctl.target).addScaledVector(DIR, DIST);
    cam.updateProjectionMatrix();
    ctl.update();
    onChange();
  };
  const wheelRef = useRef(onWheel);
  wheelRef.current = onWheel;
  useEffect(() => {
    const el = gl.domElement.parentElement ?? gl.domElement;
    const handler = (e: WheelEvent) => wheelRef.current(e);
    el.addEventListener("wheel", handler, { capture: true, passive: false });
    return () => el.removeEventListener("wheel", handler, { capture: true });
  }, [gl]);
  useEffect(() => () => {
    if (swipe.current?.timer) clearTimeout(swipe.current.timer);
  }, []);

  return (
    <>
      <OrthographicCamera makeDefault position={[DIR.x * DIST, DIR.y * DIST, DIR.z * DIST]} zoom={30} near={1} far={640} />
      <MapControls
        ref={controls}
        makeDefault
        enableRotate={false}
        enableDamping={false}
        screenSpacePanning={false}
        zoomToCursor
        zoomSpeed={1.1}
        minZoom={limits.min}
        maxZoom={limits.max}
        mouseButtons={{ LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN }}
        touches={{ ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_PAN }}
        onStart={stable.start}
        onChange={stable.change}
        onEnd={stable.end}
      />
    </>
  );
}
