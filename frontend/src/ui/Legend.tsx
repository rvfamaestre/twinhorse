import { useEffect, useRef } from "react";
import { STATES } from "../domain/status";
import { type Dict, useT } from "../i18n";
import { S_BLOCKED, S_NODATA, S_OWN, S_STARVED, S_WORK, type SimState } from "../sim/engine";
import { useUI } from "../state/ui";
import { useDash } from "./ctx";
import { IconClose } from "./icons";

/**
 * Mini línea de tres máquinas que enseña un estado. No es un dibujo fijo: es una simulación
 * diminuta con las mismas reglas que la grande (la máquina del centro se para un rato y
 * las de los lados sufren las consecuencias).
 */
const W = 320;
const H = 104;
const BELT = 62;
const MACHINES = [64, 160, 256];
const GAP = 21; // sitio que ocupa un palé en cola
const SPEED = 46;
const LOOP = 13;

interface Mini {
  pallets: number[]; // posición de cada palé en la cinta, de más adelantado a menos
  hold: (number | null)[]; // tiempo de trabajo que le queda al palé de cada máquina (null = vacía)
  idle: number[]; // segundos que lleva vacía
  spawn: number;
  t: number;
}

const fresh = (): Mini => ({ pallets: [230, 208, 130, 108, 30, 8], hold: [null, null, null], idle: [0, 0, 0], spawn: 0, t: 0 });

function step(m: Mini, dt: number, stops: boolean): SimState[] {
  m.t += dt;
  const phase = m.t % LOOP;
  const stopped = stops && phase > 3 && phase < 9.5;
  const states: SimState[] = [S_WORK, S_WORK, S_WORK];

  // Máquinas, de la última a la primera: así el hueco que deja una lo aprovecha la anterior.
  for (let k = 2; k >= 0; k--) {
    const x = MACHINES[k];
    if (m.hold[k] != null) {
      if (!(k === 1 && stopped)) m.hold[k] = Math.max(0, m.hold[k]! - dt);
      if (m.hold[k] === 0) {
        const ahead = m.pallets.filter((p) => p > x).reduce((a, p) => Math.min(a, p), Infinity);
        if (ahead - x >= GAP) {
          m.pallets.push(x + 1);
          m.hold[k] = null;
          m.idle[k] = 0;
        }
      }
    }
    states[k] = k === 1 && stopped ? S_OWN : m.hold[k] == null ? (m.idle[k] > 0.7 ? S_STARVED : S_WORK) : m.hold[k] === 0 ? S_BLOCKED : S_WORK;
    if (m.hold[k] == null) m.idle[k] += dt;
  }

  // Palés: avanzan hasta el de delante o hasta la entrada de una máquina ocupada.
  m.pallets.sort((a, b) => b - a);
  for (let i = 0; i < m.pallets.length; i++) {
    const p = m.pallets[i];
    let limit = i > 0 ? m.pallets[i - 1] - GAP : Infinity;
    const k = MACHINES.findIndex((x) => p <= x - GAP + 0.01 && p > x - 90);
    if (k >= 0) {
      const door = MACHINES[k] - GAP;
      if (p >= door - 0.5 && m.hold[k] == null && !(k === 1 && stopped)) {
        m.hold[k] = 0.75; // entra a trabajar
        m.pallets.splice(i--, 1);
        continue;
      }
      limit = Math.min(limit, door);
    }
    m.pallets[i] = Math.max(p, Math.min(p + SPEED * dt, limit));
  }
  m.pallets = m.pallets.filter((p) => p < W + 10);
  m.spawn -= dt;
  const tail = m.pallets.length ? m.pallets[m.pallets.length - 1] : Infinity;
  if (m.spawn <= 0 && tail > GAP - 8) {
    m.pallets.push(-8);
    m.spawn = 1.15;
  }
  return states;
}

const INK = {
  light: { belt: "#d9dde1", pallet: "#3a424b", body: "#eef0f2" },
  dark: { belt: "#3a3e44", pallet: "#c3c9cf", body: "#26292d" },
};

function draw(ctx: CanvasRenderingContext2D, m: Mini, states: SimState[], focus: SimState, ink: (typeof INK)["light"], words: Dict["mini"]) {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = ink.belt;
  ctx.fillRect(0, BELT + 5, W, 6);
  ctx.fillStyle = ink.pallet;
  for (const p of m.pallets) ctx.fillRect(p - 7, BELT - 9, 14, 14);
  ctx.font = '600 11px system-ui, -apple-system, "Segoe UI", sans-serif';
  ctx.textAlign = "center";
  MACHINES.forEach((x, k) => {
    const s = focus === S_NODATA && k === 1 ? S_NODATA : states[k];
    const on = s === focus;
    const color = STATES[s].css;
    if (on) {
      ctx.fillStyle = `${color}33`;
      ctx.beginPath();
      ctx.arc(x, BELT - 6, 34, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.fillStyle = ink.body;
    ctx.strokeStyle = on ? color : "#9aa3ad";
    ctx.lineWidth = on ? 3 : 1.5;
    ctx.beginPath();
    ctx.roundRect(x - 19, BELT - 30, 38, 38, 7);
    ctx.fill();
    ctx.stroke();
    if (m.hold[k] != null) {
      ctx.fillStyle = ink.pallet;
      ctx.fillRect(x - 7, BELT - 9, 14, 14);
    }
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, BELT - 20, 5.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = on ? color : "#8a929b";
    ctx.fillText(s === S_NODATA ? words.unknown : words[s] ?? "", x, BELT + 30);
  });
}

function MiniLine({ focus }: { focus: SimState }) {
  const T = useT();
  const ref = useRef<HTMLCanvasElement>(null);
  const theme = useUI((s) => s.theme);
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const m = fresh();
    const stops = focus !== S_WORK && focus !== S_NODATA;
    let raf = 0;
    let last = performance.now();
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (still) for (let i = 0; i < 360; i++) step(m, 1 / 60, stops); // sin animación: una foto en mitad de la parada
    const ink = INK[theme];
    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      draw(ctx, m, step(m, still ? 0 : dt, stops), focus, ink, T.mini);
      if (!still) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [focus, theme, T]);
  return <canvas ref={ref} className="mini" style={{ width: W, height: H }} role="img" aria-label={T.legend.anim(T.states[focus].label)} />;
}

/** Tarjeta que explica el estado pulsado en la leyenda. Mientras está abierta, la planta ilumina solo ese estado. */
export function LegendCard() {
  const T = useT();
  const legend = useUI((s) => s.legend);
  const setLegend = useUI((s) => s.setLegend);
  const { snap } = useDash();
  if (legend == null) return null;
  const info = { ...STATES[legend], ...T.states[legend] };
  const before = T.legend.now(0)[0];
  let count = 0;
  for (const s of snap.states) if (s === legend) count++;
  return (
    <section className="legend-card card" aria-label={T.legend.explain(info.label)}>
      <header>
        <i className="dot big" style={{ background: info.css }} />
        <h2>{info.label}</h2>
        <button className="icon-btn ghost" onClick={() => setLegend(null)} aria-label={T.legend.close}>
          <IconClose />
        </button>
      </header>
      <p>{info.plain}</p>
      <MiniLine focus={legend} />
      <p className="cause">{info.cause}</p>
      <p className="meta">
        {before} <b>{count}</b> {T.legend.now(count)[1]} {T.legend.term(info.term)}
      </p>
    </section>
  );
}
