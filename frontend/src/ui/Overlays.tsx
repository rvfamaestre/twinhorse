import { useEffect } from "react";
import { useData } from "../data/liveFeed";
import { STATES } from "../domain/status";
import { tramoName, useT } from "../i18n";
import type { SimState } from "../sim/engine";
import { useHover } from "../scene/Scene";
import { durationText } from "../state/clock";
import { useUI } from "../state/ui";
import { useDash } from "./ctx";
import { IconClose, IconLeft, IconRight } from "./icons";

/** Bordes de la escena: los tramos vecinos quedan difuminados y tocarlos lleva a ellos. */
export function EdgeNav() {
  const T = useT();
  const { tramos } = useDash();
  const tramo = useUI((s) => s.tramo);
  const overview = useUI((s) => s.overview);
  const goTramo = useUI((s) => s.goTramo);
  if (overview) return null;
  const prev = tramos[tramo - 1];
  const next = tramos[tramo + 1];
  return (
    <>
      {prev ? (
        <button className="edge left" onClick={() => goTramo(tramo - 1)} aria-label={T.tramos.go(tramoName(T, prev))} title={`${tramoName(T, prev)} (←)`}>
          <span><IconLeft /></span>
        </button>
      ) : null}
      {next ? (
        <button className="edge right" onClick={() => goTramo(tramo + 1)} aria-label={T.tramos.go(tramoName(T, next))} title={`${tramoName(T, next)} (→)`}>
          <span><IconRight /></span>
        </button>
      ) : null}
    </>
  );
}

/** Rótulo que sigue al ratón: qué máquina es y cómo está ahora. */
export function HoverTip() {
  const T = useT();
  const { op, x, y } = useHover();
  const { model, snap } = useDash();
  if (!op) return null;
  const node = model.g.index.get(op);
  const state = node != null ? (snap.states[node] as SimState) : null;
  const left = Math.min(window.innerWidth - 230, x + 16);
  const top = Math.max(8, y - 44);
  return (
    <div className="tip" style={{ left, top }} role="tooltip">
      <b>{op}</b>
      {state != null ? (
        <span><i className="dot" style={{ background: STATES[state].css }} />{T.states[state].label}{state !== 0 ? ` · ${durationText(snap.t - snap.since[node!])}` : ""}</span>
      ) : (
        <span>{T.tip.manipulator}</span>
      )}
    </div>
  );
}

/** Pista para quien llega por primera vez. Se va en cuanto toca algo. */
export function Hint() {
  const T = useT();
  const touched = useUI((s) => s.touched);
  const { narrow } = useDash();
  if (touched) return null;
  return <p className="hint">{narrow ? T.hint.touch : T.hint.click}</p>;
}

/** Mensajes del sistema (datos nuevos, conexión perdida). Uno cada vez. */
export function Notice() {
  const T = useT();
  const notice = useData((s) => s.notice);
  const dismiss = useData((s) => s.dismiss);
  useEffect(() => {
    if (!notice || notice.level === "error") return;
    const id = setTimeout(dismiss, 6000);
    return () => clearTimeout(id);
  }, [notice, dismiss]);
  if (!notice) return null;
  const p = notice.params;
  const text = notice.key === "contract" && p ? T.notice.contract(T.notice.sources[p.source], p.count, p.path) : notice.key === "contract" ? "" : T.notice[notice.key];
  return (
    <div className={`notice card ${notice.level}`} role="status">
      <span>{text}</span>
      <button className="icon-btn ghost" onClick={dismiss} aria-label={T.notice.close}>
        <IconClose />
      </button>
    </div>
  );
}

export function Splash({ error }: { error: string | null }) {
  const T = useT();
  const refresh = useData((s) => s.refresh);
  return (
    <div className="splash">
      <div className="card">
        <h1>{error != null ? T.splash.empty : T.splash.loading}</h1>
        {error != null ? (
          <>
            <p>{error || T.splash.failed}</p>
            <button className="primary" onClick={refresh}>{T.splash.retry}</button>
          </>
        ) : null}
      </div>
    </div>
  );
}
