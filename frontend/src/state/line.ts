import { useEffect, useMemo, useState } from "react";
import type { LineState } from "../contract/types";
import { useData } from "../data/liveFeed";
import { type LineGraph, buildGraph } from "../domain/graph";
import { type Layout, type Tramo, buildLayout, layoutTramos } from "../domain/layout";
import { type DayRun, simulateDay } from "../sim/day";
import { S_BLOCKED, S_OWN, S_STARVED, newStationSample, producedAt, sampleStation, traceCause } from "../sim/engine";

/** La línea lista para pintar: datos, grafo y planta. Se recalcula solo cuando llegan datos nuevos. */
export interface LineModel {
  state: LineState;
  g: LineGraph;
  lay: Layout;
}

export function useLineModel(): LineModel | null {
  const state = useData((s) => s.state);
  return useMemo(() => {
    if (!state) return null;
    const g = buildGraph(state);
    return { state, g, lay: buildLayout(g) };
  }, [state]);
}

export function useViewport(): { w: number; h: number } {
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setSize({ w: window.innerWidth, h: window.innerHeight }));
    };
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return size;
}

/** Un tramo es lo que cabe nítido en pantalla: menos estaciones cuanto más estrecha. `lay` es la planta que se dibuja. */
export function useTramos(model: LineModel | null, lay: Layout | null, width: number): Tramo[] {
  const size = width >= 1500 ? 9 : width >= 1100 ? 7 : width >= 760 ? 5 : 3;
  return useMemo(() => (model && lay ? layoutTramos(model.g, lay, size) : []), [model, lay, size]);
}

const runs = new Map<string, DayRun>();

/** Simulación de un día, guardada: volver a un día ya visto no cuesta nada. */
export function dayRun(model: LineModel, day: string): DayRun {
  const key = `${model.state.meta.generated_at ?? ""}|${model.state.meta.line}|${day}`;
  let run = runs.get(key);
  if (!run) {
    if (runs.size >= 6) runs.delete(runs.keys().next().value!);
    run = simulateDay(model.state, model.g, model.lay, day);
    runs.set(key, run);
  }
  return run;
}

/** Foto del instante para la interfaz: quién está parada, quién espera y por culpa de quién. */
export interface Snap {
  t: number;
  day: string;
  states: Uint8Array; // estado de cada estación del flujo
  since: Float32Array; // desde cuándo
  cause: Int16Array; // estación que la tiene esperando (-1 si ninguna parada lo explica)
  own: number[]; // paradas ahora
  waiting: number; // esperando ahora por una parada ajena
  culprits: { node: number; waiting: number }[]; // de más a menos estaciones esperando
  made: number;
  target: number;
}

const sample = newStationSample();

export function takeSnap(model: LineModel, run: DayRun, t: number): Snap {
  const { g } = model;
  const sim = run.sim;
  const n = g.nodes.length;
  const states = new Uint8Array(n);
  const since = new Float32Array(n);
  const cause = new Int16Array(n).fill(-1);
  const own: number[] = [];
  for (let i = 0; i < n; i++) {
    sampleStation(sim, i, t, sample);
    states[i] = sample.state;
    since[i] = sample.since;
    if (sample.state === S_OWN) own.push(i);
  }
  const count = new Map<number, number>();
  let waiting = 0;
  for (let i = 0; i < n; i++) {
    if (states[i] !== S_STARVED && states[i] !== S_BLOCKED) continue;
    const chain = traceCause(sim, i, t);
    const end = chain[chain.length - 1];
    if (end === i || states[end] !== S_OWN) continue;
    cause[i] = end;
    waiting++;
    count.set(end, (count.get(end) ?? 0) + 1);
  }
  const culprits = [...count].map(([node, w]) => ({ node, waiting: w })).sort((a, b) => b.waiting - a.waiting || a.node - b.node);
  return { t, day: run.day, states, since, cause, own, waiting, culprits, made: producedAt(sim, run.sink, t), target: run.target };
}
