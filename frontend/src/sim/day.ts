import type { DailyRow, LineState } from "../contract/types";
import type { LineGraph } from "../domain/graph";
import { type Layout, MOVE_IN, SPEED } from "../domain/layout";
import { type DaySim, type SimNet, producedAt, simulate } from "./engine";
import { lineCycleOf, lineGapOf, nodeInput, pieces } from "./inputs";

export function buildNet(g: LineGraph, lay: Layout): SimNet {
  return {
    nodes: g.nodes.map((n) => ({ ins: n.ins, outs: n.outs, stride: n.stride, res: n.res })),
    edges: g.edges.map((e) => ({
      from: e.from, to: e.to, cap: lay.paths[e.i].cap, tau: lay.paths[e.i].head / SPEED, stride: e.stride, res: e.res, feed: e.feed,
    })),
    topo: g.topo,
  };
}

export const rowOf = (node: { station: { daily: DailyRow[] } }, day: string) => node.station.daily.find((d) => d.day === day);

/** Última estación del flujo principal: lo que sale por ella son los motores del día. */
export const sinkOf = (g: LineGraph) => g.slots[g.slots.length - 1]?.[0] ?? 0;

export interface DayRun {
  sim: DaySim;
  day: string;
  sink: number;
  target: number; // motores reales del día
  made: number; // motores del día simulado
  pace: number; // ajuste de ritmo aplicado
}

/**
 * Simula un día de la línea a partir de sus totales reales. Mismo día, mismo resultado.
 *
 * Las paradas se propagan más o menos según cuánto pulmón hay entre estaciones, y eso no está en
 * los datos. Para que el día simulado termine con los motores reales, el ritmo de trabajo se
 * ajusta con un único factor para toda la línea (unas pocas iteraciones).
 */
export function simulateDay(state: LineState, g: LineGraph, lay: Layout, day: string): DayRun {
  const rows = g.nodes.map((n) => rowOf(n, day));
  const net = buildNet(g, lay);
  const sink = sinkOf(g);
  const horizon = state.meta.required_h * 3600;
  const row = rows[sink];
  const target = row && row.status !== "fuera_servicio" && pieces(row) > 0 ? pieces(row) : 0;
  const base = { line: state.meta.line, day, requiredH: state.meta.required_h, lineCycle: lineCycleOf(rows), lineGapH: lineGapOf(rows, state.meta.required_h), minCycle: MOVE_IN + 2 };

  let pace = 1;
  let sim!: DaySim;
  let made = 0;
  for (let it = 0; it < 6; it++) {
    const ctx = { ...base, pace };
    sim = simulate(net, g.nodes.map((n, i) => nodeInput(n.station, rows[i], ctx)), horizon, { moveIn: MOVE_IN });
    made = producedAt(sim, sink, horizon);
    if (!target || !made || Math.abs(made - target) / target < 0.004) break;
    pace = Math.min(1.25, Math.max(0.5, pace * Math.pow(made / target, 1.15)));
  }
  return { sim, day, sink, target, made, pace };
}
