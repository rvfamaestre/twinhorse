/**
 * Comprueba la línea serpenteada con el mock: filas, curvas, que cada cinta (salvo las curvas) mida
 * lo mismo que en la recta, que no haya estaciones solapadas y que los tramos cubran la línea.
 * (La simulación no depende de la forma: usa siempre la planta recta.)
 *   npm run snake:check
 */
import { readFileSync } from "node:fs";
import type { LineState } from "../src/contract/types";
import { buildGraph } from "../src/domain/graph";
import { buildLayout, layoutTramos, snakeLayout } from "../src/domain/layout";

const state = JSON.parse(readFileSync(new URL("../public/mock/line_state.mock.json", import.meta.url), "utf-8")) as LineState;
const g = buildGraph(state);
const line = buildLayout(g);
const snake = snakeLayout(g, line);
let failures = 0;
const check = (ok: boolean, msg: string) => {
  if (!ok) failures++;
  console.log(`${ok ? "ok " : "MAL"} ${msg}`);
};

console.log(`huecos del flujo: ${g.slots.length} · estaciones: ${g.nodes.length} · cintas: ${g.edges.length} · manipuladores: ${g.aux.length}`);
check(snake != null, "se puede serpentear");
if (snake) {
  const rows = snake.snake!.rows;
  console.log(`filas: ${rows.map((r) => `[${r.a}, ${r.b})`).join(" ")}`);
  const curves = g.edges.filter((e) => Math.abs(snake.paths[e.i].len - line.paths[e.i].len) > 1e-6);
  check(curves.length === rows.length - 1, `curvas: ${curves.length} (una por cambio de fila)`);
  for (const e of curves) console.log(`    curva ${g.nodes[e.from].op} → ${g.nodes[e.to].op}: ${line.paths[e.i].len.toFixed(1)} m → ${snake.paths[e.i].len.toFixed(1)} m`);
  check(snake.inStub.every((p, i) => (p == null) === (line.inStub[i] == null) && (!p || Math.abs(p.len - line.inStub[i]!.len) < 1e-6)), "entradas de la línea con la misma longitud");
  check(snake.towers.length === line.towers.length, `pulmones: ${snake.towers.length}`);

  // Ninguna estación encima de otra.
  let overlaps = 0;
  for (let a = 0; a < g.nodes.length; a++) {
    for (let b = a + 1; b < g.nodes.length; b++) {
      const pa = snake.poses[a];
      const pb = snake.poses[b];
      if (Math.abs(pa.x - pb.x) < 2.6 && Math.abs(pa.z - pb.z) < 2.6) overlaps++;
    }
  }
  check(overlaps === 0, `estaciones solapadas: ${overlaps}`);

  const w = snake.bounds.x1 - snake.bounds.x0;
  const d = snake.bounds.z1 - snake.bounds.z0;
  console.log(`planta recta: ${(line.bounds.x1 - line.bounds.x0).toFixed(0)} × ${(line.bounds.z1 - line.bounds.z0).toFixed(0)} m · serpenteada: ${w.toFixed(0)} × ${d.toFixed(0)} m`);

  for (const size of [9, 7, 5, 3]) {
    const tr = layoutTramos(g, snake, size);
    const seen = new Set(tr.flatMap((t) => t.nodes));
    const missing = g.nodes.filter((n) => !seen.has(n.i)).map((n) => n.op);
    check(missing.length === 0, `tramos de ${size}: ${tr.length}${missing.length ? ` · sin tramo: ${missing.join(", ")}` : ""}`);
  }
  const straight = layoutTramos(g, line, 9);
  console.log(`tramos en recta (9): ${straight.length}`);
}
if (failures) {
  console.error(`${failures} comprobaciones fallidas`);
  process.exit(1);
}
