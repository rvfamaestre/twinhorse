/**
 * Motor de simulación de un periodo. Es puro y determinista: misma entrada, mismo resultado.
 *
 * Modelo: una línea con pulmones finitos entre estaciones. Cada estación trabaja una pieza
 * durante su ciclo, se para cuando le toca (paradas propias, en tiempo de trabajo acumulado)
 * y solo suelta la pieza si hay hueco delante. «Sin piezas» y «bloqueada» no se guionizan:
 * salen solas de la física, que es justo lo que se quiere enseñar.
 *
 * Se resuelve con la recurrencia clásica (max-plus) pieza a pieza, sin cola de eventos:
 *   empieza[n][j] = max(llegada de la pieza j, salida de la pieza anterior)
 *   acaba[n][j]   = empieza + ciclo + paradas que caen en esa pieza
 *   sale[n][j]    = max(acaba, cuando la siguiente estación deja hueco en la cinta)
 * Con esos tres vectores por estación, el estado de cualquier instante se consulta por
 * búsqueda binaria: avanzar, retroceder o saltar en el tiempo cuesta lo mismo.
 */

export const S_WORK = 0;
export const S_OWN = 1;
export const S_STARVED = 2;
export const S_BLOCKED = 3;
export const S_OFF = 4;
export const S_NODATA = 5;
export const S_GAP = 6;
export type SimState = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export interface SimNode {
  ins: number[];
  outs: number[];
  stride: number; // en un grupo en paralelo de m estaciones, cada una hace 1 de cada m piezas
  res: number;
}

export interface SimEdge {
  from: number;
  to: number;
  cap: number; // palés que caben esperando entre las dos
  tau: number; // s que tarda un palé en llegar a la espera de la siguiente
  stride: number;
  res: number;
  feed: boolean; // trae un subconjunto: la pieza se monta y el palé no sigue
}

export interface SimNet {
  nodes: SimNode[];
  edges: SimEdge[];
  topo: number[];
}

export interface NodeInput {
  pass: boolean; // no trabaja la pieza: la deja pasar (fuera de servicio, sin datos)
  fixed: SimState | -1; // estado que se enseña siempre; -1 = el que salga de la simulación
  cycle: number; // s de trabajo por pieza
  stopPos: Float32Array; // cuándo cae cada parada, en s de trabajo acumulado desde el inicio del periodo
  stopDur: Float32Array;
  stopKind: Uint8Array; // S_OWN | S_GAP
}

export interface DaySim {
  net: SimNet;
  inputs: NodeInput[];
  horizon: number;
  warmup: number;
  moveIn: number;
  n: Int32Array; // piezas calculadas en cada estación
  start: Float32Array[];
  fin: Float32Array[];
  dep: Float32Array[];
  stopT: Float32Array[]; // hora real de cada parada
  stopN: Int32Array; // cuántas paradas llegaron a ocurrir
}

export interface SimOptions {
  warmup?: number; // s previos sin paradas para que la línea arranque llena, como en planta
  moveIn?: number; // s que tarda el palé en entrar a la estación desde la espera
}

export function simulate(net: SimNet, inputs: NodeInput[], horizon: number, opts: SimOptions = {}): DaySim {
  const warm = opts.warmup ?? 3 * 3600;
  const moveIn = opts.moveIn ?? 4.5;
  const N = net.nodes.length;
  const service = inputs.map((i) => (i.pass ? moveIn + 1 : Math.max(i.cycle, moveIn + 1)));

  // Cota de piezas: las que podría hacer el cuello de botella sin pararse nunca.
  let slowest = moveIn + 1;
  for (let i = 0; i < N; i++) slowest = Math.max(slowest, service[i] / net.nodes[i].stride);
  const K = Math.min(40000, Math.ceil((horizon + warm) / slowest) + 24);

  const start: Float32Array[] = [];
  const fin: Float32Array[] = [];
  const dep: Float32Array[] = [];
  const stopT: Float32Array[] = [];
  for (let i = 0; i < N; i++) {
    const len = Math.ceil(K / net.nodes[i].stride) + 1;
    start.push(new Float32Array(len));
    fin.push(new Float32Array(len));
    dep.push(new Float32Array(len));
    stopT.push(new Float32Array(inputs[i].stopPos.length).fill(Infinity));
  }
  const n = new Int32Array(N);
  const stopN = new Int32Array(N);
  const first = new Int32Array(N).fill(-1); // primera pieza que empieza dentro del periodo
  const sources = net.topo.filter((i) => net.nodes[i].ins.length === 0 && net.nodes[i].stride === 1);

  for (let j = 0; j < K; j++) {
    for (const i of net.topo) {
      const nd = net.nodes[i];
      if (j % nd.stride !== nd.res) continue;
      const l = (j - nd.res) / nd.stride;

      let s = -warm;
      for (const e of nd.ins) {
        const ed = net.edges[e];
        if (j % ed.stride !== ed.res) continue;
        const p = net.nodes[ed.from];
        const a = dep[ed.from][(j - p.res) / p.stride] + ed.tau;
        if (a > s) s = a;
      }
      if (l > 0 && dep[i][l - 1] > s) s = dep[i][l - 1];

      const inp = inputs[i];
      let f = s + service[i];
      if (!inp.pass && s >= 0 && inp.stopPos.length) {
        if (first[i] < 0) first[i] = l;
        const w1 = (l - first[i] + 1) * inp.cycle;
        const w0 = w1 - inp.cycle;
        let k = stopN[i];
        let acc = 0;
        while (k < inp.stopPos.length && inp.stopPos[k] < w1) {
          stopT[i][k] = s + Math.max(0, inp.stopPos[k] - w0) + acc;
          acc += inp.stopDur[k];
          k++;
        }
        stopN[i] = k;
        f += acc;
      }

      let d = f;
      for (const e of nd.outs) {
        const ed = net.edges[e];
        if (j % ed.stride !== ed.res) continue;
        const jb = j - ed.stride * ed.cap;
        if (jb < 0) continue;
        const t = net.nodes[ed.to];
        const v = start[ed.to][(jb - t.res) / t.stride];
        if (v > d) d = v;
      }
      start[i][l] = s;
      fin[i][l] = f;
      dep[i][l] = d;
      n[i] = l + 1;
    }
    let done = sources.length > 0;
    for (const i of sources) if (start[i][j] <= horizon) done = false;
    if (done) break;
  }
  return { net, inputs, horizon, warmup: warm, moveIn, n, start, fin, dep, stopT, stopN };
}

/** Primer índice con arr[i] > t, en [0, len). */
export function upper(arr: Float32Array, len: number, t: number): number {
  let lo = 0;
  let hi = len;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] <= t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

export interface StationSample {
  state: SimState;
  piece: number; // índice de la pieza que tiene o acaba de soltar (-1 si ninguna)
  has: boolean; // hay un palé dentro
  progress: number; // 0..1 del trabajo de la pieza actual
  entered: number; // s desde que el palé empezó a entrar
  since: number; // cuándo empezó el estado actual
  until: number; // cuándo acaba (Infinity si no se sabe)
}

export const newStationSample = (): StationSample => ({ state: S_STARVED, piece: -1, has: false, progress: 0, entered: 0, since: 0, until: Infinity });

export function sampleStation(sim: DaySim, i: number, t: number, out: StationSample): StationSample {
  const inp = sim.inputs[i];
  const st = sim.start[i];
  const l = upper(st, sim.n[i], t) - 1;
  out.piece = l;
  out.progress = 0;
  out.entered = 0;
  out.until = Infinity;
  if (l < 0) {
    out.state = S_STARVED;
    out.has = false;
    out.since = -sim.warmup;
  } else if (t < sim.fin[i][l]) {
    out.has = true;
    out.entered = t - st[l];
    out.state = S_WORK;
    out.since = st[l];
    out.until = sim.fin[i][l];
    let stopped = 0;
    const T = sim.stopT[i];
    for (let k = upper(T, sim.stopN[i], t) - 1; k >= 0 && T[k] >= st[l]; k--) {
      const end = T[k] + inp.stopDur[k];
      if (t < end) {
        out.state = inp.stopKind[k] as SimState;
        out.since = T[k];
        out.until = end;
        stopped += t - T[k];
      } else {
        stopped += inp.stopDur[k];
        if (out.state === S_WORK && end > out.since) out.since = end;
      }
    }
    const work = inp.pass ? 1 : Math.max(inp.cycle, 1e-6);
    out.progress = Math.min(1, Math.max(0, (t - st[l] - stopped) / work));
  } else if (t < sim.dep[i][l]) {
    out.has = true;
    out.entered = t - st[l];
    out.progress = 1;
    out.state = S_BLOCKED;
    out.since = sim.fin[i][l];
    out.until = sim.dep[i][l];
  } else {
    out.has = false;
    out.state = S_STARVED;
    out.since = sim.dep[i][l];
    if (l + 1 < sim.n[i]) out.until = st[l + 1];
  }
  if (inp.fixed >= 0) out.state = inp.fixed as SimState;
  return out;
}

/** Relación entre la k-ésima pieza de una cinta y el índice local en cada extremo. */
function edgeIndex(sim: DaySim, e: number) {
  const ed = sim.net.edges[e];
  const f = sim.net.nodes[ed.from];
  const t = sim.net.nodes[ed.to];
  const af = ed.stride / f.stride;
  const bf = (ed.res - f.res) / f.stride;
  const at = ed.stride / t.stride;
  const bt = (ed.res - t.res) / t.stride;
  const nk = Math.max(0, Math.min(Math.floor((sim.n[ed.from] - 1 - bf) / af), Math.floor((sim.n[ed.to] - 1 - bt) / at)) + 1);
  return { ed, af, bf, at, bt, nk };
}

function upperK(arr: Float32Array, a: number, b: number, nk: number, t: number): number {
  let lo = 0;
  let hi = nk;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[a * mid + b] <= t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

export interface EdgeSample {
  count: number;
  pos: Float32Array; // distancia recorrida por cada palé desde el centro de la estación de origen
  piece: Int32Array; // índice global de la pieza
}

export const newEdgeSample = (max = 64): EdgeSample => ({ count: 0, pos: new Float32Array(max), piece: new Int32Array(max) });

/**
 * Palés que hay en una cinta en el instante t. `head` es dónde espera el primero,
 * `pitch` la separación en cola y `speed` la velocidad de la cinta.
 * `slots` limita los huecos visibles antes de `hold` (para el pulmón: el resto espera dentro).
 */
export function sampleEdge(sim: DaySim, e: number, t: number, speed: number, pitch: number, head: number, out: EdgeSample, slots = Infinity, hold = 0): EdgeSample {
  const { ed, af, bf, at, bt, nk } = edgeIndex(sim, e);
  const depF = sim.dep[ed.from];
  const stT = sim.start[ed.to];
  const kLo = upperK(stT, at, bt, nk, t);
  const kHi = upperK(depF, af, bf, nk, t) - 1;
  const prev = kLo > 0 ? stT[at * (kLo - 1) + bt] : -Infinity;
  const slide = Math.min(1, Math.max(0, 1 - ((t - prev) * speed) / pitch));
  let c = 0;
  for (let k = kLo; k <= kHi && c < out.pos.length; k++, c++) {
    const q = k - kLo;
    const slot = q < slots ? head - (q + slide) * pitch : hold;
    out.pos[c] = Math.max(0, Math.min(speed * (t - depF[af * k + bf]), slot));
    out.piece[c] = k * ed.stride + ed.res;
  }
  out.count = c;
  return out;
}

/** Piezas que han salido de una estación hasta el instante t, contando desde el inicio del periodo. */
export function producedAt(sim: DaySim, i: number, t: number): number {
  return Math.max(0, upper(sim.dep[i], sim.n[i], t) - upper(sim.dep[i], sim.n[i], 0));
}

/** Reparto del periodo por estado, en segundos (índice = SimState). Sirve para la tira del día y para medir la fidelidad. */
export function stateTotals(sim: DaySim, i: number, from = 0, to = sim.horizon): Float64Array {
  const out = new Float64Array(7);
  forEachSpan(sim, i, from, to, (s, a, b) => {
    out[s] += b - a;
  });
  return out;
}

/** Recorre los tramos de estado de una estación entre dos instantes, en orden. */
export function forEachSpan(sim: DaySim, i: number, from: number, to: number, fn: (state: SimState, t0: number, t1: number) => void): void {
  const inp = sim.inputs[i];
  if (inp.fixed >= 0) {
    fn(inp.fixed as SimState, from, to);
    return;
  }
  const st = sim.start[i];
  const emit = (s: SimState, a: number, b: number) => {
    const x = Math.max(a, from);
    const y = Math.min(b, to);
    if (y > x) fn(s, x, y);
  };
  let l = Math.max(0, upper(st, sim.n[i], from) - 1);
  if (st[l] > from) emit(S_STARVED, from, st[l]);
  const T = sim.stopT[i];
  let k = upper(T, sim.stopN[i], st[l]);
  while (k > 0 && T[k - 1] >= st[l]) k--;
  for (; l < sim.n[i] && st[l] < to; l++) {
    let cur = st[l];
    const f = sim.fin[i][l];
    for (; k < sim.stopN[i] && T[k] < f; k++) {
      emit(S_WORK, cur, T[k]);
      cur = T[k] + inp.stopDur[k];
      emit(inp.stopKind[k] as SimState, T[k], cur);
    }
    emit(S_WORK, cur, f);
    emit(S_BLOCKED, f, sim.dep[i][l]);
    emit(S_STARVED, sim.dep[i][l], l + 1 < sim.n[i] ? st[l + 1] : to);
  }
}

/**
 * Por qué está parada una estación que no tiene la culpa: sigue la cadena hasta la que
 * origina la espera. Devuelve los índices de estación, de la consultada a la causante.
 */
export function traceCause(sim: DaySim, i: number, t: number, max = 24): number[] {
  const chain = [i];
  const s = newStationSample();
  let cur = i;
  for (let step = 0; step < max; step++) {
    sampleStation(sim, cur, t, s);
    const raw = rawState(sim, cur, t, s);
    let next = -1;
    const nd = sim.net.nodes[cur];
    if (raw === S_BLOCKED) {
      // La frena la de delante: la cinta de salida que lleva su pieza.
      const j = s.piece * nd.stride + nd.res;
      for (const e of nd.outs) if (j % sim.net.edges[e].stride === sim.net.edges[e].res) next = sim.net.edges[e].to;
    } else if (raw === S_STARVED) {
      // La frena la de atrás: de todas sus entradas, la que más tarda en traer la pieza.
      const j = (s.piece + 1) * nd.stride + nd.res;
      let worst = -Infinity;
      for (const e of nd.ins) {
        const ed = sim.net.edges[e];
        if (j % ed.stride !== ed.res) continue;
        const p = sim.net.nodes[ed.from];
        const lp = (j - p.res) / p.stride;
        const a = lp < sim.n[ed.from] ? sim.dep[ed.from][lp] : Infinity;
        if (a > worst) {
          worst = a;
          next = ed.from;
        }
      }
    }
    if (next < 0 || chain.includes(next)) break;
    chain.push(next);
    cur = next;
  }
  return chain;
}

/** Estado físico, sin el estado fijo de las estaciones sin dato. */
function rawState(sim: DaySim, i: number, t: number, s: StationSample): SimState {
  if (sim.inputs[i].fixed < 0) return s.state;
  if (!s.has) return S_STARVED;
  return t >= sim.fin[i][Math.max(0, s.piece)] ? S_BLOCKED : S_WORK;
}
