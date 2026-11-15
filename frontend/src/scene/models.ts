import * as THREE from "three";
import type { LineGraph } from "../domain/graph";
import type { Layout, Path, Pose } from "../domain/layout";
import { Builder, GLASS, METAL } from "./builder";
import { C, ENV, type Env, type Theme } from "./palette";

/**
 * Modelos de la planta, hechos con cajas y cilindros por código: ni ficheros 3D ni texturas
 * externas. Lo fijo (nave, cintas, máquinas) se funde en tres geometrías; lo que se mueve
 * (palés, cabezales, operarios, luces) son piezas sueltas que la escena instancia.
 * Medidas en metros. Cada modelo se dibuja en el sitio que marque `Builder.at`, con el flujo hacia +x.
 */
export const BELT_Y = 0.66; // altura de la cinta
// Suelo pintado bajo cada puesto: cambia con el modo oscuro (se fija al construir la planta).
let PAD = ENV.light.pad;

export const TOOL_NONE = -1;
export const TOOL_PRESS = 0;
export const TOOL_ROBOT = 1;
export const TOOL_SPINDLE = 2;
export const TOOL_OPERATOR = 3;
export const TOOL_KINDS = 4;

/** Dónde van las piezas móviles de un puesto, ya en coordenadas de planta. */
export interface Rig {
  tool: number;
  pivot: THREE.Vector3;
  lamp: THREE.Vector3;
  rot: number;
  top: number; // altura libre encima, para el icono de aviso
  center: THREE.Vector3;
}

function hashOf(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const world = (p: Pose, lx: number, ly: number, lz: number) =>
  new THREE.Vector3(p.x + lx * Math.cos(p.rot) + lz * Math.sin(p.rot), ly, p.z - lx * Math.sin(p.rot) + lz * Math.cos(p.rot));

type Local = [number, number, number];

/** Celda automática: bancada, armario trasero, cerramiento de cristal, pantalla y baliza. */
function autoCell(b: Builder, tool: number): { pivot: Local; lamp: Local; top: number } {
  b.box(0, 0.012, 0.15, 2.8, 0.024, 2.9, PAD);
  b.box(0, 0.06, -0.1, 1.94, 0.12, 1.54, C.slate);
  b.box(0, 0.37, -0.1, 1.9, 0.5, 1.5, C.bodyMid);
  b.box(0, 1.42, -0.92, 1.9, 1.6, 0.42, C.body);
  b.box(0, 2.14, -0.705, 1.9, 0.1, 0.012, C.accent);
  for (let k = -1; k <= 1; k++) b.box(k * 0.6, 1.25, -0.705, 0.4, 0.62, 0.012, C.bodyMid);
  b.box(-0.93, 1.42, 0.62, 0.07, 1.6, 0.07, C.slate).box(0.93, 1.42, 0.62, 0.07, 1.6, 0.07, C.slate);
  b.box(0, 2.25, -0.15, 1.96, 0.06, 1.62, C.body);
  b.box(-0.94, 1.45, -0.05, 0.02, 1.5, 1.25, C.glass, GLASS).box(0.94, 1.45, -0.05, 0.02, 1.5, 1.25, C.glass, GLASS);
  b.box(0, 1.74, 0.63, 1.8, 0.94, 0.02, C.glass, GLASS);
  // Pantalla del operario, mirando al pasillo.
  b.box(-1.22, 0.6, 0.78, 0.06, 1.2, 0.06, C.steel, METAL);
  b.box(-1.22, 1.32, 0.78, 0.54, 0.42, 0.08, C.graphite).box(-1.22, 1.33, 0.825, 0.42, 0.3, 0.012, C.screen);
  b.cyl(0.8, 2.5, -0.9, 0.025, 0.46, C.steel, METAL);

  let pivot: Local = [0, 2.22, 0];
  if (tool === TOOL_ROBOT) {
    b.cyl(0, 0.9, -0.48, 0.2, 0.56, C.slate, 0, "y", 12);
    pivot = [0, 1.18, -0.48];
  } else {
    b.box(0, 2.02, 0, 0.36, 0.42, 0.36, C.bodyMid); // camisa por la que baja el cabezal
  }
  return { pivot, lamp: [0.8, 2.86, -0.9], top: 3.3 };
}

/** Puesto manual: mesa, estantería de cajas, pórtico con luz y herramienta colgada, y el operario. */
function manualPost(b: Builder): { pivot: Local; lamp: Local; top: number } {
  b.box(0, 0.012, 0.15, 2.8, 0.024, 2.9, PAD);
  b.box(0, 0.016, 1.05, 1.5, 0.03, 0.86, C.mat);
  b.box(0, 0.05, -0.02, 1.72, 0.1, 0.8, C.slate).box(0, 0.35, -0.02, 1.7, 0.52, 0.78, C.body);
  // Pórtico de aluminio.
  for (const sx of [-0.98, 0.98]) {
    b.box(sx, 1.25, -0.6, 0.06, 2.5, 0.06, C.alu, METAL).box(sx, 2.47, 0, 0.06, 0.06, 1.26, C.alu, METAL);
  }
  b.box(0, 2.44, 0.45, 1.9, 0.05, 0.18, C.white).box(0, 2.47, 0.05, 1.96, 0.05, 0.05, C.steel, METAL);
  b.box(0.4, 2.36, 0.05, 0.12, 0.16, 0.12, C.accent).cyl(0.4, 1.95, 0.05, 0.012, 0.68, C.black).box(0.4, 1.52, 0.05, 0.07, 0.22, 0.07, C.graphite);
  // Estantería de cajas por gravedad.
  for (const sx of [-0.9, 0.9]) b.box(sx, 0.95, -1.15, 0.04, 1.9, 0.55, C.alu, METAL);
  const bins = [C.binGrey, C.binTan, C.accent, C.binGrey];
  [0.45, 1.0, 1.55].forEach((y, row) => {
    b.box(0, y, -1.15, 1.8, 0.03, 0.55, C.alu, METAL);
    for (let k = 0; k < 4; k++) b.box(-0.63 + 0.42 * k, y + 0.115, -1.1, 0.34, 0.2, 0.4, bins[(k + row) % bins.length]);
  });
  b.box(-0.55, 2.12, -0.56, 0.04, 0.6, 0.04, C.steel, METAL);
  b.box(-0.55, 1.85, -0.52, 0.54, 0.36, 0.03, C.graphite).box(-0.55, 1.85, -0.5, 0.46, 0.28, 0.012, C.screen);
  b.cyl(0.98, 2.7, -0.6, 0.025, 0.4, C.steel, METAL);
  // Piernas del operario (el torso se mueve: es una pieza aparte).
  for (const sx of [-0.1, 0.1]) b.box(sx, 0.45, 1.0, 0.14, 0.82, 0.16, C.trousers).box(sx, 0.04, 0.96, 0.15, 0.08, 0.26, C.black);
  return { pivot: [0, 0.86, 1.0], lamp: [0.98, 3.0, -0.6], top: 3.45 };
}

/** Manipulador: columna con brazo y garra, de cara a la línea. */
function manipulator(b: Builder): { lamp: Local; top: number } {
  b.box(0, 0.012, 0, 1.2, 0.024, 1.2, PAD);
  b.cyl(0, 0.05, 0, 0.36, 0.1, C.slate, 0, "y", 14).cyl(0, 1.45, 0, 0.1, 2.8, C.robot, 0, "y", 12);
  b.box(0, 2.75, -0.95, 0.14, 0.16, 2.1, C.accent).box(0, 2.5, -0.35, 0.06, 0.06, 0.8, C.steel, METAL);
  b.box(0, 2.62, -1.7, 0.2, 0.12, 0.24, C.graphite).cyl(0, 2.15, -1.7, 0.012, 0.85, C.black);
  b.box(0, 1.68, -1.7, 0.36, 0.1, 0.26, C.steel, METAL);
  b.box(-0.16, 1.58, -1.7, 0.04, 0.14, 0.2, C.graphite).box(0.16, 1.58, -1.7, 0.04, 0.14, 0.2, C.graphite);
  return { lamp: [0, 2.98, 0], top: 3.4 };
}

/** Pulmón: torre cerrada donde esperan los palés; el nivel se ve en una columna al frente. */
function bufferTower(b: Builder): void {
  b.box(0, 0.012, 0.2, 3.0, 0.024, 2.6, PAD);
  b.box(0, 0.1, 0, 2.36, 0.2, 1.76, C.slate).box(0, 2.0, 0, 2.3, 3.6, 1.7, C.white);
  b.box(0, 3.72, 0, 2.32, 0.2, 1.72, C.accent);
  b.box(-1.152, 0.93, 0, 0.02, 0.5, 0.72, C.graphite).box(1.152, 0.93, 0, 0.02, 0.5, 0.72, C.graphite);
  b.box(0, GAUGE_Y0 + GAUGE_H / 2, 0.853, 0.36, GAUGE_H + 0.12, 0.012, C.graphite);
  b.box(-0.72, 2.1, 0.853, 0.5, 2.3, 0.012, C.glass, GLASS).box(0.72, 2.1, 0.853, 0.5, 2.3, 0.012, C.glass, GLASS);
}

export const GAUGE_Y0 = 0.55;
export const GAUGE_H = 2.9;
export const GAUGE_Z = 0.865;

/** Cinta a lo largo de un recorrido: cama, guías laterales y patas. */
function conveyor(b: Builder, path: Path): void {
  b.at(0, 0);
  const { pts } = path;
  for (let i = 2; i < pts.length; i += 2) {
    const ax = pts[i - 2];
    const az = pts[i - 1];
    const dx = pts[i] - ax;
    const dz = pts[i + 1] - az;
    const len = Math.hypot(dx, dz);
    if (len < 0.01) continue;
    const ry = Math.atan2(-dz, dx);
    const mx = ax + dx / 2;
    const mz = az + dz / 2;
    const nx = -dz / len;
    const nz = dx / len;
    b.box(mx, BELT_Y - 0.05, mz, len + 0.3, 0.1, 0.56, C.graphite, 0, ry);
    for (const side of [-0.3, 0.3]) b.box(mx + nx * side, BELT_Y + 0.03, mz + nz * side, len + 0.3, 0.1, 0.045, C.alu, METAL, ry);
    const legs = Math.max(1, Math.round(len / 1.7));
    for (let k = 0; k < legs; k++) {
      const u = (k + 0.5) / legs;
      b.box(ax + dx * u, (BELT_Y - 0.1) / 2, az + dz * u, 0.07, BELT_Y - 0.1, 0.5, C.steel, METAL, ry);
    }
  }
}

/** Nave: suelo con juntas, pasillo pintado y pared del fondo con ventanales. */
function shell(b: Builder, lay: Layout, env: Env): void {
  const x0 = lay.bounds.x0 - 12;
  const x1 = lay.bounds.x1 + 12;
  const zw = lay.bounds.z0 - 2.6;
  const zf = lay.bounds.z1 + 5.5;
  const cx = (x0 + x1) / 2;
  const len = x1 - x0;
  b.at(0, 0);
  // El suelo sigue más allá de lo que enseña la cámara: así nunca se ve el borde de la nave.
  const fx0 = x0 - 60;
  const fx1 = x1 + 60;
  const fz1 = zf + 40;
  b.box((fx0 + fx1) / 2, -0.06, (zw + fz1) / 2, fx1 - fx0, 0.12, fz1 - zw, env.floor);
  for (let x = Math.ceil(fx0 / 6) * 6; x < fx1; x += 6) b.box(x, 0.002, (zw + fz1) / 2, 0.035, 0.004, fz1 - zw, env.joint);
  // Un pasillo delante de cada fila (en la línea recta, uno solo).
  for (const aisle of lay.aisles) {
    b.box(cx, 0.006, aisle, len, 0.012, 1.9, env.walkway);
    b.box(cx, 0.008, aisle - 1.0, len, 0.016, 0.09, env.floorLine).box(cx, 0.008, aisle + 1.0, len, 0.016, 0.09, env.floorLine);
  }
  b.box(cx, 3.2, zw, len, 6.4, 0.3, env.wall).box(cx, 0.85, zw + 0.16, len, 0.5, 0.02, env.wallBand);
  for (let x = Math.ceil(x0 / 14) * 14; x < x1; x += 14) {
    b.box(x, 3.2, zw + 0.3, 0.5, 6.4, 0.5, env.column);
    b.box(x + 7, 4.2, zw + 0.16, 4.2, 1.7, 0.02, env.window);
  }
}

/**
 * Huecos de ventana de la pared del fondo (uno cada 14 m): ahí van los carteles con los logos.
 * Mismo reparto que `shell`, para que el cartel tape justo una ventana.
 */
export function wallSpots(lay: Layout): { x: number; y: number; z: number }[] {
  const x0 = lay.bounds.x0 - 12;
  const x1 = lay.bounds.x1 + 12;
  const zw = lay.bounds.z0 - 2.6;
  const out: { x: number; y: number; z: number }[] = [];
  for (let x = Math.ceil(x0 / 14) * 14; x < x1; x += 14) out.push({ x: x + 7, y: 4.2, z: zw + 0.19 });
  return out;
}

export interface Plant {
  geos: (THREE.BufferGeometry | null)[];
  rigs: Rig[]; // uno por estación del flujo
  auxRigs: Rig[]; // uno por manipulador
}

export function buildPlant(g: LineGraph, lay: Layout, theme: Theme = "light"): Plant {
  const env = ENV[theme];
  PAD = env.pad;
  const b = new Builder();
  shell(b, lay, env);
  lay.paths.forEach((p) => conveyor(b, p));
  lay.inStub.forEach((p) => p && conveyor(b, p));
  lay.outStub.forEach((p) => p && conveyor(b, p));
  for (const t of lay.towers) bufferTower(b.at(t.x, t.z));

  const rigs = g.nodes.map((n) => {
    // El modelo mira siempre al pasillo, aunque en una fila de vuelta las piezas vayan al revés.
    const pose = { ...lay.poses[n.i], rot: lay.face[n.i] };
    b.at(pose.x, pose.z, pose.rot);
    const manual = n.station.kind === "manual";
    const tool = manual ? TOOL_OPERATOR : hashOf(n.op) % 3;
    const m = manual ? manualPost(b) : autoCell(b, tool);
    return {
      tool, rot: pose.rot, top: m.top,
      pivot: world(pose, ...m.pivot), lamp: world(pose, ...m.lamp), center: new THREE.Vector3(pose.x, 0, pose.z),
    };
  });
  const auxRigs = g.aux.map((a) => {
    const pose = lay.aux[a.i];
    const m = manipulator(b.at(pose.x, pose.z, pose.rot));
    return { tool: TOOL_NONE, rot: pose.rot, top: m.top, pivot: world(pose, 0, 0, 0), lamp: world(pose, ...m.lamp), center: new THREE.Vector3(pose.x, 0, pose.z) };
  });
  return { geos: b.build(), rigs, auxRigs };
}

/** Pieza móvil de cada tipo de puesto, con el origen en su punto de giro. */
export function toolGeometry(tool: number): THREE.BufferGeometry {
  const b = new Builder().at(0, 0);
  if (tool === TOOL_PRESS) {
    b.box(0, -0.3, 0, 0.26, 0.6, 0.26, C.steel).box(0, -0.66, 0, 0.44, 0.12, 0.38, C.slate).cyl(0, -0.79, 0, 0.05, 0.14, C.alu);
  } else if (tool === TOOL_SPINDLE) {
    b.box(0, -0.16, 0, 0.3, 0.32, 0.3, C.accent).box(0, -0.37, 0, 0.52, 0.1, 0.42, C.slate);
    for (const sx of [-0.15, 0.15]) for (const sz of [-0.11, 0.11]) b.cyl(sx, -0.62, sz, 0.028, 0.42, C.alu);
  } else if (tool === TOOL_ROBOT) {
    b.cyl(0, 0.08, 0, 0.17, 0.16, C.robot, 0, "y", 12).box(0, 0.36, 0, 0.16, 0.5, 0.16, C.robot).ball(0, 0.62, 0, 0.12, C.slate);
    b.box(0, 0.62, 0.26, 0.13, 0.13, 0.52, C.robot).box(0, 0.42, 0.48, 0.1, 0.4, 0.1, C.slate).box(0, 0.2, 0.48, 0.24, 0.06, 0.14, C.graphite);
  } else {
    // Operario de cintura para arriba, mirando a la mesa (-z).
    b.box(0, 0.3, 0, 0.42, 0.6, 0.24, C.shirt).ball(0, 0.74, -0.01, 0.125, C.skin);
    b.box(0, 0.84, -0.02, 0.25, 0.07, 0.27, C.accent).box(0, 0.815, -0.18, 0.2, 0.02, 0.1, C.accent);
    for (const sx of [-0.26, 0.26]) b.box(sx, 0.38, -0.06, 0.1, 0.34, 0.12, C.shirt).box(sx * 0.96, 0.22, -0.3, 0.085, 0.085, 0.4, C.skin);
  }
  return b.single();
}

export const ENGINE_STAGES = 4; // del bloque desnudo al motor terminado
export const PART_VARIANT = ENGINE_STAGES; // palé de un subconjunto: lleva una pieza, no un motor

/** Palé con el motor en la fase de montaje `variant`; el origen es el centro de la base del palé. */
export function palletGeometry(variant: number): THREE.BufferGeometry {
  const b = new Builder().at(0, 0);
  b.box(0, 0.03, 0, 0.52, 0.06, 0.46, C.pallet).box(0, 0.075, 0, 0.3, 0.03, 0.24, C.graphite);
  if (variant === PART_VARIANT) {
    b.box(0, 0.14, 0, 0.32, 0.1, 0.2, C.castLight);
    for (const sx of [-0.09, 0.03, 0.15]) b.cyl(sx - 0.03, 0.21, 0, 0.035, 0.05, C.cast);
    return b.single();
  }
  b.box(0, 0.2, 0, 0.36, 0.22, 0.26, C.cast);
  if (variant >= 1) b.box(0, 0.35, 0, 0.36, 0.08, 0.24, C.castLight);
  if (variant >= 2) b.box(0, 0.41, 0, 0.34, 0.05, 0.2, C.plastic).box(0, 0.3, 0.165, 0.3, 0.1, 0.07, C.plastic);
  if (variant >= 3) {
    b.cyl(0.2, 0.2, 0.05, 0.075, 0.03, C.plastic, 0, "x", 12).cyl(0.2, 0.31, -0.07, 0.045, 0.03, C.alu, 0, "x", 10);
    b.box(0, 0.29, -0.155, 0.3, 0.13, 0.04, C.shield).cyl(-0.08, 0.45, 0, 0.03, 0.03, C.accent);
  }
  return b.single();
}

export const stageOf = (rank: number) => (rank < 0.25 ? 0 : rank < 0.5 ? 1 : rank < 0.78 ? 2 : 3);
