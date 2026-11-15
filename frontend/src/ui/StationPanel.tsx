import { useEffect, useRef } from "react";
import type { DailyRow, Station } from "../contract/types";
import { dayLong, dayShort, hours, num } from "../domain/format";
import { DAY_STATE, STATES } from "../domain/status";
import { tramoName, useT } from "../i18n";
import { S_BLOCKED, S_GAP, S_OWN, S_STARVED, S_WORK, type SimState, forEachSpan } from "../sim/engine";
import { pieces, unrecorded } from "../sim/inputs";
import { durationText, scrubTo } from "../state/clock";
import { useUI } from "../state/ui";
import { useDash } from "./ctx";
import { IconClose } from "./icons";

const ORDER: SimState[] = [S_WORK, S_OWN, S_STARVED, S_BLOCKED, S_GAP];

/** Reparto de las horas del día según el dato real. */
function DayBar({ row, required }: { row: DailyRow; required: number }) {
  const T = useT();
  const parts: [SimState, number][] = [
    [S_WORK, row.tbf ?? 0], [S_OWN, row.tap ?? 0], [S_STARVED, row.des ?? 0], [S_BLOCKED, row.sat ?? 0], [S_GAP, unrecorded(row, required)],
  ];
  const total = parts.reduce((a, [, v]) => a + v, 0) || 1;
  return (
    <>
      <div className="bar" role="img" aria-label={parts.map(([s, v]) => `${T.states[s].label} ${num(v, 1)} ${T.panel.hours}`).join(", ")}>
        {parts.map(([s, v]) => (v > 0 ? <i key={s} style={{ width: `${(100 * v) / total}%`, background: STATES[s].css }} /> : null))}
      </div>
      <ul className="bar-key">
        {parts.map(([s, v]) => (v >= 0.05 ? <li key={s}><i className="dot" style={{ background: STATES[s].css }} />{T.states[s].label} <b>{hours(v)}</b></li> : null))}
      </ul>
    </>
  );
}

/** Cómo fue el día, hora a hora: en cada franja, qué parte del tiempo pasó en cada estado. Pulsar lleva a esa hora. */
function DayStrip({ node }: { node: number }) {
  const T = useT();
  const { run, snap } = useDash();
  const theme = useUI((s) => s.theme);
  const ref = useRef<HTMLCanvasElement>(null);
  const horizon = run.sim.horizon;
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const bins = Math.max(24, Math.floor(w / 3));
    const acc = new Float64Array(bins * 7);
    const size = horizon / bins;
    forEachSpan(run.sim, node, 0, horizon, (s, a, b) => {
      for (let k = Math.floor(a / size); k < bins && k * size < b; k++) {
        acc[k * 7 + s] += Math.min(b, (k + 1) * size) - Math.max(a, k * size);
      }
    });
    const bw = w / bins;
    const track = getComputedStyle(canvas).getPropertyValue("--track").trim() || "#dfe3e7";
    for (let k = 0; k < bins; k++) {
      let y = h;
      for (const s of ORDER) {
        const part = (acc[k * 7 + s] / size) * h;
        if (part <= 0) continue;
        ctx.fillStyle = s === S_WORK ? track : STATES[s].css;
        ctx.fillRect(k * bw, y - part, bw + 0.5, part);
        y -= part;
      }
    }
  }, [run, node, horizon, theme]);
  const goTo = (e: React.MouseEvent<HTMLButtonElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const ui = useUI.getState();
    if (ui.mode === "live") ui.setMode("history");
    ui.setPlaying(false);
    scrubTo(((e.clientX - box.left) / box.width) * horizon);
  };
  return (
    <button className="strip-day" onClick={goTo} title={T.panel.stripTip}>
      <canvas ref={ref} />
      <i className="cursor" style={{ left: `${(100 * snap.t) / horizon}%` }} />
      <span className="ticks"><span>0 h</span><span>{Math.round(horizon / 7200)} h</span><span>{Math.round(horizon / 3600)} h</span></span>
    </button>
  );
}

/** Los días uno al lado de otro: horas perdidas por cada causa. Pulsar un día lo abre. */
function DaysChart({ station, required }: { station: Station; required: number }) {
  const T = useT();
  const { day } = useDash();
  const setDay = useUI((s) => s.setDay);
  const rows = station.daily;
  const top = Math.max(1, ...rows.map((r) => (r.tap ?? 0) + (r.des ?? 0) + (r.sat ?? 0)));
  const fc = station.forecast?.metric === "tap_h" ? station.forecast : null;
  const p90 = new Map(fc ? fc.days.map((d, i) => [d, fc.p90[i]]) : []);
  return (
    <div className="chart" role="group" aria-label={T.panel.chart}>
      {rows.map((r) => {
        const over = p90.has(r.day) && (r.tap ?? 0) > p90.get(r.day)!;
        return (
          <button key={r.day} className={`col${r.day === day ? " on" : ""}`} onClick={() => setDay(r.day)}
            title={T.panel.colTip(dayLong(r.day), hours(r.tap), hours(r.des), hours(r.sat), num(required, 0), over)}>
            <span className="stack" style={{ height: `${(100 * ((r.tap ?? 0) + (r.des ?? 0) + (r.sat ?? 0))) / top}%` }}>
              {([[S_BLOCKED, r.sat], [S_STARVED, r.des], [S_OWN, r.tap]] as [SimState, number | null][]).map(([s, v]) =>
                v ? <i key={s} style={{ flexGrow: v, background: STATES[s].css }} /> : null)}
            </span>
            {over ? <b title={T.panel.overTip} /> : null}
            <em>{dayShort(r.day).slice(0, 2)}</em>
          </button>
        );
      })}
    </div>
  );
}

/**
 * Ficha para una inspección rápida: estado ahora, el día que se mira y el periodo entero.
 * Solo datos y gráficas, sin frases: todo sale de los números del contrato y de la reconstrucción.
 */
export function StationPanel({ op }: { op: string }) {
  const T = useT();
  const { model, day, snap, run, tramos, tramoOf, dayAlerts } = useDash();
  const { g, state } = model;
  const select = useUI((s) => s.select);
  const closePanel = useUI((s) => s.closePanel);
  const openForecast = useUI((s) => s.openForecast);
  const markRead = useUI((s) => s.markRead);
  const node = g.index.get(op);
  const aux = g.auxIndex.get(op);
  const station = node != null ? g.nodes[node].station : aux != null ? g.aux[aux].station : null;
  const mine = dayAlerts.filter((a) => a.op === op);
  const ids = mine.map((a) => a.id).join("|");
  // Abrir la ficha cuenta como leer sus avisos de ese día.
  useEffect(() => {
    if (ids) markRead(ids.split("|"));
  }, [ids, markRead]);
  if (!station) return null;

  const row = station.daily.find((d) => d.day === day);
  const tramo = tramos[tramoOf(op)];
  const required = state.meta.required_h;
  const days = state.meta.days.length;
  const now = node != null ? (snap.states[node] as SimState) : null;
  const culprit = node != null && snap.cause[node] >= 0 ? g.nodes[snap.cause[node]].op : null;
  const victims = node != null ? snap.culprits.find((c) => c.node === node)?.waiting ?? 0 : 0;
  const rankOwn = (state.ranking_own ?? []).indexOf(op) + 1;
  const secs = row?.nap && row.tap ? (3600 * row.tap) / row.nap : null;
  const dotState = now != null ? now : row ? DAY_STATE[row.status] : S_GAP;
  const dot = { css: STATES[dotState].css, label: T.states[dotState].label };

  return (
    <aside className="panel" aria-label={T.panel.aria(op)}>
      <header className="panel-head">
        <div>
          <h2><i className="dot big" style={{ background: dot.css }} title={dot.label} aria-label={dot.label} />{op}</h2>
          <p>{T.panel.kinds[station.kind ?? "auto"] ?? T.panel.kinds.other}{tramo ? ` · ${tramoName(T, tramo)}` : ""}</p>
        </div>
        <button className="icon-btn ghost" onClick={closePanel} aria-label={T.panel.close}>
          <IconClose />
        </button>
      </header>
      <div className="panel-body">
        {/* El estado ya lo dice el punto junto al nombre (y los avisos, la campana): aquí solo lo que no se repite. */}
        {culprit || victims ? (
          <dl className="facts">
            {culprit ? (
              <div>
                <dt>{T.panel.waitsFor}</dt>
                <dd><button className="link" onClick={() => select(culprit, true)}>{culprit}</button></dd>
              </div>
            ) : null}
            {victims ? <div><dt>{T.panel.waitedBy}</dt><dd>{T.panel.machines(victims)}</dd></div> : null}
          </dl>
        ) : null}

        <section>
          <h3>{dayLong(day)} <small>{T.panel.real}</small></h3>
          {row ? (
            <>
              <dl className="tiles">
                <div><dt>{T.panel.weighs}</dt><dd>{T.dayShort[row.status]}</dd></div>
                <div><dt>{T.panel.pieces}</dt><dd>{num(pieces(row), 0)}</dd></div>
                <div><dt>{T.panel.stops}</dt><dd>{num(row.nap, 0)}{secs ? <small> · {durationText(secs)}</small> : null}</dd></div>
              </dl>
              <DayBar row={row} required={required} />
              {node != null && run.sim.inputs[node].fixed < 0 ? (
                <>
                  <h4>{T.panel.hourly} <small>{T.panel.rebuilt}</small></h4>
                  <DayStrip node={node} />
                </>
              ) : null}
            </>
          ) : (
            <p className="muted">{T.panel.noData}</p>
          )}
        </section>

        <section>
          <h3>{T.panel.days(days)}</h3>
          <dl className="kpis">
            <div><dt>{T.panel.avail}</dt><dd>{num(station.kpi.dp, 0)} %<small>{T.panel.target(num(state.meta.targets.dp_pct, 1))}</small></dd></div>
            <div><dt>{T.panel.cycle}</dt><dd>{num(station.kpi.tcy, 0)} cmin<small>{T.panel.max(num(state.meta.targets.tcy_cmin, 0))}</small></dd></div>
            <div><dt>{T.panel.fpm}</dt><dd>{num(station.kpi.fpm, 0)}<small>{station.kpi.s_per_stop ? durationText(station.kpi.s_per_stop) : ""}</small></dd></div>
          </dl>
          <dl className="facts">
            <div>
              <dt>{T.panel.brakes}</dt>
              <dd>{station.penalty.rank ? T.panel.rank(station.penalty.rank) : "—"}{station.penalty.blocking_days ? <small> · {T.panel.ofDays(station.penalty.blocking_days, days)}</small> : null}</dd>
            </div>
            {rankOwn ? <div><dt>{T.panel.stopsRank}</dt><dd>{T.panel.rank(rankOwn)}</dd></div> : null}
          </dl>
          <DaysChart station={station} required={required} />
        </section>

        {node != null ? <button className="text-btn" onClick={() => openForecast(op)}>{T.panel.predict}</button> : null}
      </div>
    </aside>
  );
}
