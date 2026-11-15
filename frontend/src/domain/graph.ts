import type { Confidence, LineState, Station, TopologyLink, TopologyNote } from "../contract/types";

/**
 * Grafo de la línea: por dónde van las piezas. Sale de `topology` del contrato y, si la API
 * no la manda, de una serie simple por `order` (con los grupos en paralelo de `parallel_with`).
 * Aquí no hay ningún nombre de estación: vale para cualquier línea.
 */
export interface LNode {
  i: number;
  op: string;
  station: Station;
  role: "main" | "branch" | "lateral";
  slot: number; // hueco en el flujo principal, -1 si va por una rama
  member: number; // posición dentro del hueco cuando hay varias en paralelo
  branch: number;
  ins: number[];
  outs: number[];
  stride: number;
  res: number;
  rank: number; // 0..1: cuánto motor hay montado al llegar aquí
}

export interface LEdge {
  i: number;
  from: number;
  to: number;
  kind: TopologyLink["kind"];
  buffer: boolean;
  feed: boolean;
  stride: number;
  res: number;
  confidence?: Confidence;
}

export interface LBranch {
  id: string;
  nodes: number[]; // de la cabeza a la cola
  joins: number;
  lateral: boolean;
  confidence?: Confidence;
}

export interface LAux {
  i: number;
  op: string;
  station: Station;
  to: number; // estación a la que asiste, -1 si no se sabe
}

export interface LineGraph {
  nodes: LNode[];
  edges: LEdge[];
  topo: number[];
  slots: number[][];
  branches: LBranch[];
  aux: LAux[];
  notes: TopologyNote[];
  hypothesis: boolean; // la topología no viene confirmada
  serialFallback: boolean; // la API no mandó topología: se dibuja en serie
  index: Map<string, number>;
  auxIndex: Map<string, number>;
}

function fallbackLinks(flow: Station[]): TopologyLink[] {
  const sorted = [...flow].sort((a, b) => a.order - b.order);
  const seen = new Set<string>();
  const chain: string[][] = [];
  for (const s of sorted) {
    if (seen.has(s.op)) continue;
    const group = [s.op];
    if (s.parallel_with && sorted.some((x) => x.op === s.parallel_with)) group.push(s.parallel_with);
    group.forEach((op) => seen.add(op));
    chain.push(group);
  }
  // Lo que el orden mete entre dos en paralelo va después de la unión.
  const order = new Map(sorted.map((s) => [s.op, s.order]));
  chain.sort((a, b) => Math.min(...a.map((x) => order.get(x)!)) - Math.min(...b.map((x) => order.get(x)!)));
  const links: TopologyLink[] = [];
  for (let k = 1; k < chain.length; k++) {
    for (const from of chain[k - 1]) {
      for (const to of chain[k]) {
        links.push({ from, to, kind: chain[k - 1].length > 1 || chain[k].length > 1 ? "paralelo" : "serie" });
      }
    }
  }
  return links;
}

export function buildGraph(state: LineState): LineGraph {
  const flow = state.stations.filter((s) => s.group !== "manipulator");
  const index = new Map(flow.map((s, i) => [s.op, i]));
  const nodes: LNode[] = flow.map((station, i) => ({
    i, op: station.op, station, role: "main", slot: -1, member: 0, branch: -1, ins: [], outs: [], stride: 1, res: 0, rank: 0,
  }));

  const given = state.topology?.links?.filter((l) => index.has(l.from) && index.has(l.to));
  const serialFallback = !given?.length;
  const links = serialFallback ? fallbackLinks(flow) : given!;

  // Ramas: se remonta desde cada enlace de entrada (lateral o subconjunto) hasta su cabeza.
  const preds = new Map<number, number[]>();
  for (const l of links) {
    if (l.kind === "lateral" || l.kind === "subconjunto") continue;
    const to = index.get(l.to)!;
    preds.set(to, [...(preds.get(to) ?? []), index.get(l.from)!]);
  }
  const branches: LBranch[] = [];
  for (const l of links) {
    if (l.kind !== "lateral" && l.kind !== "subconjunto") continue;
    const chain: number[] = [];
    let cur: number | undefined = index.get(l.from)!;
    while (cur != null && !chain.includes(cur)) {
      chain.unshift(cur);
      cur = preds.get(cur)?.[0];
    }
    const b = branches.length;
    branches.push({ id: l.branch ?? `L${b + 1}`, nodes: chain, joins: index.get(l.to)!, lateral: l.kind === "lateral", confidence: l.confidence });
    for (const n of chain) {
      nodes[n].role = l.kind === "lateral" ? "lateral" : "branch";
      nodes[n].branch = b;
    }
  }

  // Aristas. Una estación sin enlaces se añade al final del flujo principal, para no perderla.
  const edges: LEdge[] = [];
  const addEdge = (from: number, to: number, l: Partial<TopologyLink>) => {
    const e: LEdge = {
      i: edges.length, from, to, kind: l.kind ?? "serie", buffer: !!l.buffer,
      feed: l.kind === "lateral" || l.kind === "subconjunto", stride: 1, res: 0, confidence: l.confidence,
    };
    edges.push(e);
    nodes[from].outs.push(e.i);
    nodes[to].ins.push(e.i);
  };
  for (const l of links) addEdge(index.get(l.from)!, index.get(l.to)!, l);
  const orphans = nodes.filter((n) => !n.ins.length && !n.outs.length);
  if (orphans.length && nodes.length > orphans.length) {
    let last = nodes.find((n) => n.role === "main" && !n.outs.length && !orphans.includes(n));
    for (const o of orphans.sort((a, b) => a.station.order - b.station.order)) {
      if (last) addEdge(last.i, o.i, {});
      last = o;
    }
  }

  // Orden topológico (Kahn) y nivel de cada estación del flujo principal.
  const indeg = nodes.map((n) => n.ins.length);
  const level = nodes.map(() => 0);
  const queue = nodes.filter((n) => !n.ins.length).sort((a, b) => a.station.order - b.station.order).map((n) => n.i);
  const topo: number[] = [];
  while (queue.length) {
    const i = queue.shift()!;
    topo.push(i);
    for (const e of nodes[i].outs) {
      const to = edges[e].to;
      if (nodes[i].role === "main" && nodes[to].role === "main") level[to] = Math.max(level[to], level[i] + 1);
      if (--indeg[to] === 0) queue.push(to);
    }
  }
  if (topo.length < nodes.length) nodes.forEach((n) => !topo.includes(n.i) && topo.push(n.i)); // ciclo en los datos: no se bloquea

  const slots: number[][] = [];
  for (const n of nodes) if (n.role === "main") (slots[level[n.i]] ??= []).push(n.i);
  const packed = slots.filter(Boolean);
  packed.forEach((members, s) => {
    members.sort((a, b) => nodes[a].station.order - nodes[b].station.order);
    members.forEach((i, m) => {
      nodes[i].slot = s;
      nodes[i].member = m;
      nodes[i].stride = members.length;
      nodes[i].res = m;
      nodes[i].rank = packed.length > 1 ? s / (packed.length - 1) : 0;
    });
  });
  for (const b of branches) for (const i of b.nodes) nodes[i].rank = nodes[b.joins].rank;
  for (const e of edges) {
    const side = nodes[e.from].stride > 1 ? nodes[e.from] : nodes[e.to];
    e.stride = side.stride;
    e.res = side.res;
  }

  const assists = new Map((state.topology?.assists ?? []).map((a) => [a.op, a.to]));
  const aux: LAux[] = state.stations
    .filter((s) => s.group === "manipulator")
    .map((station, i) => ({ i, op: station.op, station, to: index.get(assists.get(station.op) ?? "") ?? -1 }));

  return {
    nodes, edges, topo, slots: packed, branches, aux,
    notes: state.topology?.notes ?? [],
    hypothesis: serialFallback || state.topology?.hypothesis !== false,
    serialFallback,
    index,
    auxIndex: new Map(aux.map((a) => [a.op, a.i])),
  };
}
