import type { LineGraph } from "./graph";

/**
 * Dónde va cada cosa en planta (metros). El flujo principal corre de izquierda a derecha;
 * lo que entra de lado queda detrás, en carriles paralelos. Solo geometría: ni datos ni colores.
 */
export const PITCH = 3.4; // entre estaciones
export const SPEED = 0.2; // m/s de la cinta
export const PALLET_PITCH = 0.7; // entre palés en cola
export const WAIT = 0.9; // el primero espera a esta distancia del centro de la estación
export const MOVE_IN = WAIT / SPEED;
export const PARALLEL_SEP = 3.6;
export const LANE_LATERAL = -3.7;
export const LANE_BRANCH = -7.6;
export const LANE_STEP = -3.8;
export const BUFFER_GAP = 4.6; // hueco extra para el pulmón
export const BUFFER_CAP = 30;
export const TOWER_HALF = 1.15;
export const STUB_IN = 2.6;
export const STUB_OUT = 3.2;
export const AUX_Z = 2.85;

export interface Pose {
  x: number;
  z: number;
  rot: number; // giro en Y: 0 = el flujo va hacia +x; -π/2 = hacia +z
}

export interface Path {
  pts: number[]; // x0, z0, x1, z1…
  cum: number[]; // distancia acumulada en cada punto
  len: number;
  head: number; // dónde espera el primer palé
  cap: number;
  slots: number; // huecos de cola a la vista
  hold: number; // dónde esperan los que no se ven (dentro del pulmón)
  hidden: [number, number] | null;
}

/** Una fila de la línea serpenteada: los huecos [a, b) del flujo principal. */
export interface SnakeRow {
  a: number;
  b: number;
  start: number; // x (en planta) del borde por donde entran las piezas
  end: number; // x del borde por donde salen
  z0: number; // fondo de la fila
  aisle: number; // pasillo delante de la fila
}

export interface Snake {
  rows: SnakeRow[];
  nodeRow: number[];
  slotX: number[]; // x de cada hueco ya colocado en su fila
}

export interface Layout {
  poses: Pose[]; // `rot` es el rumbo del flujo (en una fila de vuelta, al revés)
  face: number[]; // giro del modelo de cada estación: siempre de cara al pasillo
  paths: Path[];
  inStub: (Path | null)[];
  outStub: (Path | null)[];
  aux: Pose[];
  towers: { edge: number; x: number; z: number }[];
  slotX: number[];
  auxBay: { x0: number; x1: number; z: number } | null;
  bounds: { x0: number; x1: number; z0: number; z1: number };
  aisles: number[]; // z de cada pasillo pintado
  snake: Snake | null;
}

export function makePath(pts: number[], opts: { buffer?: boolean } = {}): Path {
  const cum = [0];
  for (let i = 2; i < pts.length; i += 2) cum.push(cum[cum.length - 1] + Math.hypot(pts[i] - pts[i - 2], pts[i + 1] - pts[i - 1]));
  const len = cum[cum.length - 1];
  const head = len - WAIT;
  if (opts.buffer) {
    const mid = len / 2;
    const slots = Math.max(1, Math.floor((head - (mid + TOWER_HALF)) / PALLET_PITCH) + 1);
    return { pts, cum, len, head, cap: BUFFER_CAP, slots, hold: mid, hidden: [mid - TOWER_HALF, mid + TOWER_HALF] };
  }
  const cap = Math.max(1, Math.floor((head - 0.9 * PALLET_PITCH) / PALLET_PITCH) + 1);
  return { pts, cum, len, head, cap, slots: cap, hold: 0, hidden: null };
}

/** Punto y rumbo a una distancia `s` del inicio de un recorrido. */
export function pointAt(path: Path, s: number, out: { x: number; z: number; rot: number }): void {
  const { pts, cum } = path;
  let k = 1;
  while (k < cum.length - 1 && cum[k] < s) k++;
  const a = (k - 1) * 2;
  const seg = cum[k] - cum[k - 1] || 1;
  const u = Math.min(1, Math.max(0, (s - cum[k - 1]) / seg));
  const dx = pts[a + 2] - pts[a];
  const dz = pts[a + 3] - pts[a + 1];
  out.x = pts[a] + dx * u;
  out.z = pts[a + 1] + dz * u;
  out.rot = Math.atan2(-dz, dx);
}

export function buildLayout(g: LineGraph): Layout {
  const poses: Pose[] = g.nodes.map(() => ({ x: 0, z: 0, rot: 0 }));

  // Flujo principal: un hueco por nivel; más sitio alrededor de un paralelo y de un pulmón.
  const slotX: number[] = [];
  let x = 0;
  g.slots.forEach((members, s) => {
    if (s > 0) {
      const prev = g.slots[s - 1];
      const wide = members.length > 1 || prev.length > 1;
      const buffer = g.edges.some((e) => e.buffer && prev.includes(e.from) && members.includes(e.to));
      x += (wide ? PITCH * 1.3 : PITCH) + (buffer ? BUFFER_GAP : 0);
    }
    slotX.push(x);
    members.forEach((i, m) => {
      poses[i] = { x, z: ((members.length - 1) / 2 - m) * PARALLEL_SEP, rot: 0 };
    });
  });

  // Ramas: las de una estación, justo detrás de donde entran; las largas, en un carril paralelo libre.
  const lanes: [number, number][][] = [];
  const zOfBranch: number[] = [];
  g.branches.forEach((b, bi) => {
    const tx = poses[b.joins].x;
    const tz = poses[b.joins].z;
    if (b.nodes.length === 1) {
      zOfBranch[bi] = tz + LANE_LATERAL;
      poses[b.nodes[0]] = { x: tx, z: zOfBranch[bi], rot: -Math.PI / 2 };
      return;
    }
    const span: [number, number] = [tx - b.nodes.length * PITCH - STUB_IN - 1, tx + 1.5];
    let lane = 0;
    while ((lanes[lane] ?? []).some(([a, c]) => span[0] < c && a < span[1])) lane++;
    (lanes[lane] ??= []).push(span);
    zOfBranch[bi] = tz + LANE_BRANCH + lane * LANE_STEP;
    b.nodes.forEach((i, k) => {
      poses[i] = { x: tx - (b.nodes.length - k) * PITCH, z: zOfBranch[bi], rot: 0 };
    });
  });

  const towers: Layout["towers"] = [];
  const paths = g.edges.map((e) => {
    const a = poses[e.from];
    const b = poses[e.to];
    let pts: number[];
    if (e.feed && g.nodes[e.from].role === "branch") pts = [a.x, a.z, b.x, a.z, b.x, b.z];
    else if (a.z !== b.z && a.x !== b.x) {
      // Desvío hacia o desde un paralelo: sale recto, cruza en diagonal y entra recto.
      pts = [a.x, a.z, a.x + 0.9, a.z, b.x - 1.2, b.z, b.x, b.z];
    } else pts = [a.x, a.z, b.x, b.z];
    const path = makePath(pts, { buffer: e.buffer });
    if (e.buffer) towers.push({ edge: e.i, x: (a.x + b.x) / 2, z: (a.z + b.z) / 2 });
    return path;
  });

  const along = (p: Pose, d: number): [number, number] => [p.x + Math.cos(p.rot) * d, p.z - Math.sin(p.rot) * d];
  const inStub = g.nodes.map((n) => (n.ins.some((e) => !g.edges[e].feed) ? null : makePath([...along(poses[n.i], -STUB_IN), poses[n.i].x, poses[n.i].z])));
  const outStub = g.nodes.map((n) => (n.outs.length ? null : makePath([poses[n.i].x, poses[n.i].z, ...along(poses[n.i], STUB_OUT)])));

  // Manipuladores: delante de la estación a la que asisten; los que no se sabe, en una zona aparte al final.
  const endX = slotX.length ? slotX[slotX.length - 1] : 0;
  const loose = g.aux.filter((a) => a.to < 0);
  const bayX = endX + STUB_OUT + 4.5;
  const aux = g.aux.map((a) => {
    if (a.to >= 0) return { x: poses[a.to].x - 1.35, z: poses[a.to].z + AUX_Z, rot: 0 };
    return { x: bayX + loose.indexOf(a) * 2.9, z: 0.4, rot: 0 };
  });
  const auxBay = loose.length ? { x0: bayX - 1.8, x1: bayX + (loose.length - 1) * 2.9 + 1.8, z: 0 } : null;

  const zs = poses.map((p) => p.z);
  const bounds = {
    x0: -STUB_IN - 2,
    x1: auxBay ? auxBay.x1 + 1 : endX + STUB_OUT + 2,
    z0: Math.min(0, ...zs) - 2.2,
    z1: Math.max(0, ...zs) + 4.2,
  };
  return {
    poses, face: poses.map((p) => p.rot), paths, inStub, outStub, aux, towers, slotX, auxBay, bounds,
    aisles: [bounds.z1 + 1.5], snake: null,
  };
}

const TURN = 2.2; // lo que sale la cinta de la curva más allá de la última estación de la fila
const ROW_BACK = 2.2; // sitio detrás de la estación más retrasada de una fila
const ROW_FRONT = 4.2; // sitio delante (rótulos y manipuladores)
const ROW_GAP = 5.0; // del pasillo al fondo de la fila siguiente: las máquinas no tapan los rótulos

/**
 * La misma línea doblada en filas, como una serpiente: la fila 1 va hacia la derecha, la 2 vuelve
 * hacia la izquierda, y así. Solo cambia dónde se dibuja cada cosa: cada cinta conserva su
 * longitud salvo las curvas, así que la simulación (que usa la planta recta) no cambia.
 *
 * Se dobla por un hueco entre dos estaciones sueltas unidas por una cinta normal (sin paralelos ni
 * pulmón) y sin ninguna rama que lo cruce. Devuelve null si la línea es demasiado corta.
 */
export function snakeLayout(g: LineGraph, lay: Layout): Layout | null {
  const S = g.slots.length;
  if (S < 10) return null;
  const wanted = Math.max(2, Math.round(Math.sqrt(S / 4.5)));
  const cutX = (s: number) => (lay.slotX[s - 1] + lay.slotX[s]) / 2;
  const spans = g.branches
    .filter((b) => b.nodes.length > 1)
    .map((b) => [Math.min(...b.nodes.map((i) => lay.poses[i].x)) - STUB_IN - 1, lay.poses[b.joins].x + 1.5]);
  const foldable = (s: number) => {
    if (g.slots[s - 1].length !== 1 || g.slots[s].length !== 1) return false;
    const a = g.slots[s - 1][0];
    const b = g.slots[s][0];
    const e = g.edges.find((x) => x.from === a && x.to === b);
    if (!e || e.buffer) return false;
    const x = cutX(s);
    return !spans.some(([x0, x1]) => x > x0 && x < x1);
  };
  const cuts = [0];
  for (let k = 1; k < wanted; k++) {
    const ideal = Math.round((k * S) / wanted);
    let pick = -1;
    for (let d = 0; d <= 5 && pick < 0; d++) {
      for (const s of d ? [ideal + d, ideal - d] : [ideal]) {
        if (pick < 0 && s > cuts[cuts.length - 1] + 2 && s < S - 2 && foldable(s)) pick = s;
      }
    }
    if (pick > 0) cuts.push(pick);
  }
  if (cuts.length < 2) return null;
  cuts.push(S);
  const R = cuts.length - 1;

  const start = (r: number) => (r === 0 ? lay.slotX[0] - PITCH / 2 : cutX(cuts[r]));
  const end = (r: number) => (r === R - 1 ? lay.slotX[S - 1] + PITCH / 2 : cutX(cuts[r + 1]));
  const W = Math.max(...Array.from({ length: R }, (_, r) => end(r) - start(r)));
  const flip = (r: number) => r % 2 === 1;
  const rowOfSlot = (s: number) => {
    let r = 0;
    while (r < R - 1 && s >= cuts[r + 1]) r++;
    return r;
  };
  const rowOfX = (x: number) => {
    let r = 0;
    while (r < R - 1 && x >= cutX(cuts[r + 1])) r++;
    return r;
  };
  const nodeRow = g.nodes.map((n) => (n.slot >= 0 ? rowOfSlot(n.slot) : rowOfX(lay.poses[n.i].x)));
  const auxRow = g.aux.map((a) => (a.to >= 0 ? nodeRow[a.to] : R - 1));

  // Filas de atrás hacia delante, cada una con su pasillo.
  const zmin = new Array<number>(R).fill(0);
  const zmax = new Array<number>(R).fill(0);
  g.nodes.forEach((n) => {
    const r = nodeRow[n.i];
    zmin[r] = Math.min(zmin[r], lay.poses[n.i].z);
    zmax[r] = Math.max(zmax[r], lay.poses[n.i].z);
  });
  const zoff: number[] = [];
  const aisles: number[] = [];
  for (let r = 0; r < R; r++) {
    zoff.push(r === 0 ? 0 : aisles[r - 1] + ROW_GAP - (zmin[r] - ROW_BACK));
    aisles.push(zoff[r] + zmax[r] + ROW_FRONT + 1.5);
  }

  const tx = (r: number, x: number) => (flip(r) ? W - (x - start(r)) : x - start(r));
  const at = (r: number, x: number, z: number): [number, number] => [tx(r, x), z + zoff[r]];
  const mapPts = (r: number, pts: number[]) => {
    const out: number[] = [];
    for (let k = 0; k < pts.length; k += 2) out.push(...at(r, pts[k], pts[k + 1]));
    return out;
  };
  const heading = (r: number, rot: number) => (flip(r) ? Math.atan2(Math.sin(Math.PI - rot), Math.cos(Math.PI - rot)) : rot);

  const poses = g.nodes.map((n) => {
    const p = lay.poses[n.i];
    const r = nodeRow[n.i];
    const [x, z] = at(r, p.x, p.z);
    return { x, z, rot: heading(r, p.rot) };
  });
  const paths = g.edges.map((e) => {
    const ra = nodeRow[e.from];
    const rb = nodeRow[e.to];
    if (ra === rb) return makePath(mapPts(rb, lay.paths[e.i].pts), { buffer: e.buffer });
    // La curva: sale por el extremo de la fila, baja a la siguiente y entra de vuelta.
    const a = poses[e.from];
    const b = poses[e.to];
    const x = flip(ra) ? Math.min(a.x, b.x) - TURN : Math.max(a.x, b.x) + TURN;
    return makePath([a.x, a.z, x, a.z, x, b.z, b.x, b.z]);
  });
  const inStub = lay.inStub.map((p, i) => (p ? makePath(mapPts(nodeRow[i], p.pts)) : null));
  const outStub = lay.outStub.map((p, i) => (p ? makePath(mapPts(nodeRow[i], p.pts)) : null));
  const towers = lay.towers.map((t) => {
    const [x, z] = at(nodeRow[g.edges[t.edge].to], t.x, t.z);
    return { edge: t.edge, x, z };
  });
  const aux = lay.aux.map((p, k) => {
    const [x, z] = at(auxRow[k], p.x, p.z);
    return { x, z, rot: p.rot };
  });
  let auxBay: Layout["auxBay"] = null;
  if (lay.auxBay) {
    const a = tx(R - 1, lay.auxBay.x0);
    const b = tx(R - 1, lay.auxBay.x1);
    auxBay = { x0: Math.min(a, b), x1: Math.max(a, b), z: zoff[R - 1] };
  }

  const xs: number[] = [];
  for (const p of [...poses, ...aux]) xs.push(p.x);
  for (const p of [...paths, ...inStub, ...outStub]) if (p) for (let k = 0; k < p.pts.length; k += 2) xs.push(p.pts[k]);
  if (auxBay) xs.push(auxBay.x0, auxBay.x1);
  const bounds = {
    x0: Math.min(...xs) - 2.6,
    x1: Math.max(...xs) + 2.6,
    z0: zmin[0] - ROW_BACK,
    z1: aisles[R - 1] - 1.5,
  };
  const rows: SnakeRow[] = Array.from({ length: R }, (_, r) => ({
    a: cuts[r], b: cuts[r + 1], start: tx(r, start(r)), end: tx(r, end(r)), z0: zoff[r] + zmin[r] - ROW_BACK, aisle: aisles[r],
  }));
  const slotX = lay.slotX.map((x, s) => tx(rowOfSlot(s), x));
  return {
    poses, face: lay.face, paths, inStub, outStub, aux, towers, slotX: lay.slotX, auxBay, bounds, aisles,
    snake: { rows, nodeRow, slotX },
  };
}

export interface Tramo {
  i: number;
  label: string; // primera → última estación (el nombre, «Tramo 3», lo pone la interfaz en su idioma)
  kind: "line" | "aux";
  x0: number;
  x1: number;
  z0: number;
  z1: number;
  nodes: number[];
  aux: number[];
  title: { x: number; z: number }; // dónde va su rótulo, pintado en el pasillo
  sep: { x: number; z0: number; z1: number } | null; // raya en el suelo que lo separa del anterior
}

/** Tramos de la planta que se dibuja: recta o serpenteada. */
export function layoutTramos(g: LineGraph, lay: Layout, size: number): Tramo[] {
  return lay.snake ? buildSnakeTramos(g, lay, size) : buildTramos(g, lay, size);
}

/** Tramos de la línea serpenteada: cada fila se parte en trozos de unas `size` estaciones. */
function buildSnakeTramos(g: LineGraph, lay: Layout, size: number): Tramo[] {
  const sn = lay.snake!;
  const S = g.slots.length;
  const tramos: Tramo[] = [];
  sn.rows.forEach((row, r) => {
    const n = row.b - row.a;
    const count = Math.max(1, Math.round(n / Math.max(1, size)));
    for (let k = 0; k < count; k++) {
      const a = row.a + Math.round((k * n) / count);
      const b = row.a + Math.round(((k + 1) * n) / count) - 1;
      if (b < a) continue;
      const e0 = a === row.a ? row.start : (sn.slotX[a - 1] + sn.slotX[a]) / 2;
      const e1 = b === row.b - 1 ? row.end : (sn.slotX[b] + sn.slotX[b + 1]) / 2;
      let x0 = Math.min(e0, e1);
      let x1 = Math.max(e0, e1);
      const main = g.slots.slice(a, b + 1).flat();
      for (const i of main) {
        for (const stub of [a === 0 ? lay.inStub[i] : null, b === S - 1 ? lay.outStub[i] : null]) {
          if (!stub) continue;
          for (let p = 0; p < stub.pts.length; p += 2) {
            x0 = Math.min(x0, stub.pts[p] - 0.6);
            x1 = Math.max(x1, stub.pts[p] + 0.6);
          }
        }
      }
      const side = g.nodes
        .filter((nd) => nd.role !== "main" && sn.nodeRow[nd.i] === r && lay.poses[nd.i].x >= x0 && lay.poses[nd.i].x < x1)
        .map((nd) => nd.i);
      const nodes = [...main, ...side];
      const i = tramos.length;
      tramos.push({
        i, kind: "line",
        label: `${g.nodes[g.slots[a][0]].op} → ${g.nodes[g.slots[b][g.slots[b].length - 1]].op}`,
        x0, x1,
        z0: Math.min(...nodes.map((nd) => lay.poses[nd].z)) - 2.0,
        z1: Math.max(...nodes.map((nd) => lay.poses[nd].z)) + 3.6,
        nodes,
        aux: g.aux.filter((x) => x.to >= 0 && main.includes(x.to)).map((x) => x.i),
        title: { x: x0 + 5.6, z: row.aisle },
        sep: k > 0 ? { x: e0, z0: row.z0, z1: row.aisle + 1 } : null,
      });
    }
  });
  if (lay.auxBay) {
    const bay = lay.auxBay;
    tramos.push({
      i: tramos.length, kind: "aux", label: "",
      x0: bay.x0 - 1, x1: bay.x1 + 1, z0: bay.z - 2.4, z1: bay.z + 3.6, nodes: [],
      aux: g.aux.filter((x) => x.to < 0).map((x) => x.i),
      title: { x: bay.x0 + 4.6, z: lay.aisles[lay.aisles.length - 1] },
      sep: null,
    });
  }
  return tramos;
}

/**
 * Parte la línea en tramos de unas `size` estaciones del flujo principal. Es solo de presentación:
 * un tramo es lo que cabe nítido en pantalla, así que en un móvil son más cortos.
 */
export function buildTramos(g: LineGraph, lay: Layout, size: number): Tramo[] {
  const aisle = lay.aisles[0];
  const S = g.slots.length;
  const count = Math.max(1, Math.round(S / Math.max(1, size)));
  const cuts = Array.from({ length: count + 1 }, (_, k) => Math.round((k * S) / count));
  // Si un pulmón cae a un hueco del corte, el corte va al pulmón: es una frontera natural.
  const buffers = lay.towers.map((t) => g.nodes[g.edges[t.edge].to].slot).filter((s) => s > 0);
  for (let k = 1; k < count; k++) {
    const near = buffers.find((b) => Math.abs(b - cuts[k]) <= 1 && b > cuts[k - 1] && b < cuts[k + 1]);
    if (near != null) cuts[k] = near;
  }
  const tramos: Tramo[] = [];
  for (let k = 0; k < count; k++) {
    const a = cuts[k];
    const b = cuts[k + 1] - 1;
    if (b < a) continue;
    const x0 = a === 0 ? lay.slotX[0] - STUB_IN - 0.6 : (lay.slotX[a - 1] + lay.slotX[a]) / 2;
    const x1 = b === S - 1 ? lay.slotX[b] + STUB_OUT + 0.6 : (lay.slotX[b] + lay.slotX[b + 1]) / 2;
    const main = g.slots.slice(a, b + 1).flat();
    const side = g.nodes.filter((n) => n.role !== "main" && lay.poses[n.i].x >= x0 && lay.poses[n.i].x < x1).map((n) => n.i);
    const nodes = [...main, ...side];
    const first = g.nodes[g.slots[a][0]].op;
    const last = g.nodes[g.slots[b][g.slots[b].length - 1]].op;
    const i = tramos.length;
    tramos.push({
      i, kind: "line", label: `${first} → ${last}`, x0, x1,
      z0: Math.min(...nodes.map((n) => lay.poses[n].z)) - 2.0,
      z1: Math.max(...nodes.map((n) => lay.poses[n].z)) + 3.6,
      nodes,
      aux: g.aux.filter((x) => x.to >= 0 && main.includes(x.to)).map((x) => x.i),
      title: { x: x0 + 5.6, z: aisle },
      sep: i > 0 ? { x: x0, z0: lay.bounds.z0, z1: aisle + 1 } : null,
    });
  }
  if (lay.auxBay) {
    const x0 = lay.auxBay.x0 - 1;
    tramos.push({
      i: tramos.length, kind: "aux", label: "",
      x0, x1: lay.auxBay.x1 + 1, z0: -2.4, z1: 3.6, nodes: [],
      aux: g.aux.filter((x) => x.to < 0).map((x) => x.i),
      title: { x: x0 + 5.6, z: aisle },
      sep: tramos.length > 0 ? { x: x0, z0: lay.bounds.z0, z1: aisle + 1 } : null,
    });
  }
  return tramos;
}

export function tramoOfNode(tramos: Tramo[], node: number): number {
  return tramos.findIndex((t) => t.nodes.includes(node));
}
