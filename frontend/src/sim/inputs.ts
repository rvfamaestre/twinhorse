import type { DailyRow, Station } from "../contract/types";
import { type NodeInput, S_GAP, S_NODATA, S_OFF, S_OWN } from "./engine";

/**
 * Entradas de la simulación a partir de los totales reales del día.
 *
 * Del dato salen: el ciclo (horas trabajando / piezas), cuántas paradas propias hubo y
 * cuánto sumaron, y el tiempo sin registrar. Lo que el dato NO dice es a qué hora cayó cada
 * parada ni cuánto duró cada una: eso se reparte con un generador con semilla fija
 * (línea + día + estación), así que el mismo día se ve siempre igual.
 */

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Generador determinista (mulberry32). */
export function rng(seed: string): () => number {
  let a = hash(seed);
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const NONE: NodeInput = { pass: true, fixed: S_OFF, cycle: 0, stopPos: new Float32Array(0), stopDur: new Float32Array(0), stopKind: new Uint8Array(0) };

export const passInput = (fixed: typeof S_OFF | typeof S_NODATA): NodeInput => ({ ...NONE, fixed });

export interface InputContext {
  line: string;
  day: string;
  requiredH: number;
  lineCycle: number; // ciclo típico de la línea ese día, en s
  lineGapH: number; // horas que casi ninguna estación registra (descansos, relevos): no son de nadie en concreto
  minCycle: number;
  pace: number; // ajuste del ritmo de trabajo (1 = el del dato)
}

/** Ciclo típico de la línea: mediana de (horas trabajando / piezas) entre las estaciones con dato. */
export function lineCycleOf(rows: (DailyRow | undefined)[]): number {
  const c = rows
    .filter((r): r is DailyRow => !!r && !!r.tbf && pieces(r) > 0 && r.status !== "dato_no_fiable" && r.status !== "fuera_servicio")
    .map((r) => (r.tbf! * 3600) / pieces(r))
    .sort((a, b) => a - b);
  // Las estaciones en paralelo hacen la mitad de piezas: la mediana no se entera.
  return c.length ? c[c.length >> 1] : 50;
}

export const pieces = (r: DailyRow) => r.npr_ef ?? r.npr;

export const unrecorded = (r: DailyRow, requiredH: number) => Math.max(0, requiredH - ((r.tbf ?? 0) + (r.tap ?? 0) + (r.des ?? 0) + (r.sat ?? 0)));

/** Horas sin registrar comunes a la línea: la mediana entre estaciones. */
export function lineGapOf(rows: (DailyRow | undefined)[], requiredH: number): number {
  const u = rows.filter((r): r is DailyRow => !!r && !!r.tbf).map((r) => unrecorded(r, requiredH)).sort((a, b) => a - b);
  return u.length ? u[u.length >> 1] : 0;
}

export function nodeInput(st: Station, row: DailyRow | undefined, ctx: InputContext): NodeInput {
  if (!row || row.status === "fuera_servicio") return passInput(S_OFF);
  if (!row.tbf || pieces(row) <= 0) return passInput(S_NODATA);
  if (row.status === "dato_no_fiable") {
    // Sus tiempos no son de fiar: se dibuja trabajando al ritmo de la línea y marcada como dato dudoso.
    return { ...NONE, pass: false, fixed: S_NODATA, cycle: Math.max(ctx.minCycle, ctx.lineCycle * 0.8 * ctx.pace) };
  }
  // `pace` < 1 acelera el trabajo; las paradas se quedan en la misma pieza.
  const tbf = row.tbf * 3600 * ctx.pace;
  const cycle = Math.min(Math.max(tbf / pieces(row), ctx.minCycle), ctx.lineCycle * 4);
  const rand = rng(`${ctx.line}|${ctx.day}|${st.op}`);
  const pos: number[] = [];
  const dur: number[] = [];
  const kind: number[] = [];

  if (row.timeline?.length) {
    // Si algún día llega la hora real de cada parada, se usa tal cual.
    for (const span of row.timeline) {
      pos.push(Math.min(tbf, (span.t0 / ctx.requiredH) * tbf));
      dur.push(Math.max(0, span.t1 - span.t0) * 3600);
      kind.push(span.state === "propia" ? S_OWN : S_GAP);
    }
  } else {
    scatter(rand, Math.min(row.nap ?? 0, 4000), (row.tap ?? 0) * 3600, tbf, S_OWN, pos, dur, kind);
    // Horas que esta estación no registra y las demás sí. Sus vecinas las notan poco y cada vez menos con la
    // distancia, así que no pueden ser unos pocos bloques largos: se reparten en pausas cortas.
    const gap = unrecorded(row, ctx.requiredH) - ctx.lineGapH;
    if (gap >= 0.25) scatter(rand, Math.round((gap * 3600) / 75), gap * 3600, tbf, S_GAP, pos, dur, kind);
  }
  const idx = pos.map((_, i) => i).sort((a, b) => pos[a] - pos[b]);
  return {
    pass: false,
    fixed: -1,
    cycle,
    stopPos: Float32Array.from(idx, (i) => pos[i]),
    stopDur: Float32Array.from(idx, (i) => dur[i]),
    stopKind: Uint8Array.from(idx, (i) => kind[i]),
  };
}

/** Reparte `total` segundos en `count` paradas de duración desigual, en posiciones al azar de [0, span). */
function scatter(rand: () => number, count: number, total: number, span: number, kind: number, pos: number[], dur: number[], kinds: number[]): void {
  if (total <= 0) return;
  const n = Math.max(1, count);
  const w: number[] = [];
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const x = 0.35 - 0.65 * Math.log(1 - rand()); // duración desigual, sin colas muy largas
    w.push(x);
    sum += x;
  }
  for (let i = 0; i < n; i++) {
    pos.push(rand() * span);
    dur.push((w[i] / sum) * total);
    kinds.push(kind);
  }
}
