// Contrasta la simulación con los totales reales. Uso: npm run sim:check
import { readFileSync } from "node:fs";
import type { LineState } from "../src/contract/types";
import { buildGraph } from "../src/domain/graph";
import { buildLayout, buildTramos } from "../src/domain/layout";
import { stateTotals } from "../src/sim/engine";
import { rowOf, simulateDay } from "../src/sim/day";

const state = JSON.parse(readFileSync(new URL("../public/mock/line_state.mock.json", import.meta.url), "utf8")) as LineState;
const g = buildGraph(state);
const lay = buildLayout(g);
const tr = buildTramos(g, lay, 8);
console.log(`nodos ${g.nodes.length}, aristas ${g.edges.length}, huecos ${g.slots.length}, ramas ${g.branches.map((b) => `${b.id}:${b.nodes.length}→${g.nodes[b.joins].op}`).join(" ")}`);
console.log("tramos:", tr.map((t) => `${t.name} [${t.label}] x=${t.x0.toFixed(0)}..${t.x1.toFixed(0)} n=${t.nodes.length}`).join(" | "));
const watch = (process.argv[2] ?? "ST-2390,PM2250,ST0259,ST-0260,ST_0265,ST-0270,ST-0830,ST-0840,ManutPul,ST-2002,ST-2001,PM-2020,ST_0015,ST_3300").split(",");
let err = 0, tot = 0;
const t0 = performance.now();
const days = process.argv[3] ? [process.argv[3]] : state.meta.days;
for (const day of days) {
  const run = simulateDay(state, g, lay, day);
  const sim = run.sim;
  let line = `${day}  motores sim ${run.made} / real ${run.target}  ritmo ×${run.pace.toFixed(2)}`;
  for (const n of g.nodes) {
    const row = rowOf(n, day);
    if (!row || sim.inputs[n.i].fixed >= 0) continue;
    const s = stateTotals(sim, n.i);
    const pair = [[s[2] / 3600, row.des ?? 0], [s[3] / 3600, row.sat ?? 0], [s[0] / 3600, row.tbf ?? 0], [s[1] / 3600, row.tap ?? 0]];
    for (const [a, b] of pair.slice(0, 2)) { err += Math.abs(a - b); tot += b; }
    if (day === days[days.length - 1] && watch.includes(n.op)) {
      line += `\n   ${n.op.padEnd(9)} trabaja ${pair[2][0].toFixed(1)}/${pair[2][1].toFixed(1)}  propia ${pair[3][0].toFixed(1)}/${pair[3][1].toFixed(1)}  sin piezas ${pair[0][0].toFixed(1)}/${pair[0][1].toFixed(1)}  bloqueada ${pair[1][0].toFixed(1)}/${pair[1][1].toFixed(1)}  sin registro ${(s[6] / 3600).toFixed(1)}  (sim/real, h)`;
    }
  }
  console.log(line);
}
console.log(`error medio en horas inducidas: ${((100 * err) / tot).toFixed(0)} % · ${((performance.now() - t0) / days.length).toFixed(1)} ms por día`);
