import { tramoLabel, tramoName, useT } from "../i18n";
import { clockText, scrubTo, wallClockText } from "../state/clock";
import { SPEEDS, type Shape, useUI } from "../state/ui";
import { useDash } from "./ctx";
import { DayPicker } from "./DayPicker";
import { IconLeft, IconPause, IconPlay, IconRight } from "./icons";

/** Tramos: anterior, siguiente y salto directo. «Todo» enseña la línea entera. */
function TramoNav() {
  const T = useT();
  const { tramos } = useDash();
  const tramo = useUI((s) => s.tramo);
  const overview = useUI((s) => s.overview);
  const goTramo = useUI((s) => s.goTramo);
  const setOverview = useUI((s) => s.setOverview);
  const last = tramos.length - 1;
  return (
    <nav className="tramos" aria-label={T.tramos.nav}>
      <button className="icon-btn ghost" onClick={() => goTramo(Math.max(0, tramo - 1))} disabled={!overview && tramo === 0} aria-label={T.tramos.prev}>
        <IconLeft />
      </button>
      {tramos.map((t) => (
        <button key={t.i} className={`tramo${!overview && t.i === tramo ? " on" : ""}`} onClick={() => goTramo(t.i)}
          aria-current={!overview && t.i === tramo ? "true" : undefined} title={`${tramoName(T, t)}: ${tramoLabel(T, t)}`}>
          {t.kind === "aux" ? "M" : t.i + 1}
        </button>
      ))}
      <button className="icon-btn ghost" onClick={() => goTramo(Math.min(last, tramo + 1))} disabled={!overview && tramo === last} aria-label={T.tramos.next}>
        <IconRight />
      </button>
      <button className={`tramo wide${overview ? " on" : ""}`} onClick={() => setOverview(!overview)} aria-pressed={overview} title={T.tramos.allTip}>{T.tramos.all}</button>
    </nav>
  );
}

/** Forma de la línea: recta, como en el config, o serpenteada en filas. Se puede cambiar en cualquier momento. */
function ShapePick() {
  const T = useT();
  const shape = useUI((s) => s.shape);
  const setShape = useUI((s) => s.setShape);
  return (
    <select className="shape-pick" value={shape} onChange={(e) => setShape(e.target.value as Shape)} aria-label={T.shape.label} title={T.shape.tip}>
      <option value="line">{T.shape.line}</option>
      <option value="snake">{T.shape.snake}</option>
    </select>
  );
}

/** Cuándo: la hora actual sobre el último día con datos, o cualquier día y hora del histórico. */
function TimeControls() {
  const T = useT();
  const { live, snap, run } = useDash();
  const mode = useUI((s) => s.mode);
  const playing = useUI((s) => s.playing);
  const speed = useUI((s) => s.speed);
  const setMode = useUI((s) => s.setMode);
  const setPlaying = useUI((s) => s.setPlaying);
  const setSpeed = useUI((s) => s.setSpeed);
  const horizon = run.sim.horizon;
  const ended = snap.t >= horizon;
  return (
    <div className="time">
      <ShapePick />
      <div className="seg" role="group" aria-label={T.time.moment}>
        <button aria-pressed={mode === "live"} onClick={() => setMode("live")} title={T.time.liveTip}>{T.time.live}</button>
        <button aria-pressed={mode === "history"} onClick={() => setMode("history")}>{T.time.history}</button>
      </div>
      {live ? null : (
        <>
          <button className="icon-btn" onClick={() => { if (ended) scrubTo(0); setPlaying(!playing || ended); }} aria-label={playing ? T.time.pause : T.time.play}>
            {playing ? <IconPause /> : <IconPlay />}
          </button>
          <select className="speed" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} aria-label={T.time.speed}>
            {SPEEDS.map((s) => <option key={s} value={s}>×{s}</option>)}
          </select>
          <input className="scrub" type="range" min={0} max={horizon} step={30} value={Math.round(snap.t)}
            onChange={(e) => scrubTo(Number(e.target.value))} aria-label={T.time.hour} aria-valuetext={clockText(snap.t)} />
        </>
      )}
      <span className="clock">{live ? wallClockText() : clockText(snap.t)}</span>
      <DayPicker />
    </div>
  );
}

/** Barra de abajo: tramos y tiempo. La leyenda de estados está en «?», arriba. */
export function BottomBar() {
  return (
    <footer className="bottom">
      <TramoNav />
      <TimeControls />
    </footer>
  );
}
