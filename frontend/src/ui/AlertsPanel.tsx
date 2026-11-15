import type { AlertSeverity, AlertType } from "../contract/types";
import { ALERT_TYPES, type AlertView, SEVERITY, applyFilters } from "../domain/alerts";
import { dayLong, num } from "../domain/format";
import { type Dict, tramoName, useT } from "../i18n";
import type { Lang } from "../i18n/langs";
import { durationText } from "../state/clock";
import type { LineModel } from "../state/line";
import { NO_FILTERS, useUI } from "../state/ui";
import { useDash } from "./ctx";
import { IconClose } from "./icons";

const SHOWN = 120;

/**
 * Texto de un aviso en el idioma elegido. El backend los manda en español; en los otros idiomas se
 * componen con los mismos datos (tipo, máquina, día, horas, paradas y banda de la predicción).
 */
function alertText(T: Dict, lang: Lang, a: AlertView, model: LineModel): { title: string; detail: string } {
  if (lang === "es") return { title: a.title, detail: a.detail };
  const { g } = model;
  const node = g.index.get(a.op);
  const aux = g.auxIndex.get(a.op);
  const station = node != null ? g.nodes[node].station : aux != null ? g.aux[aux].station : null;
  const row = a.day && station ? station.daily.find((d) => d.day === a.day) : undefined;
  switch (a.type) {
    case "dato":
      return station?.status === "fuera_servicio"
        ? T.alertText.outOfService(a.op)
        : T.alertText.unreliable(a.op, (station?.flags ?? []).map((f) => f.replace(/_/g, " ")).join(", "));
    case "frena_linea":
      return T.alertText.brakes(a.op, num(a.hours ?? row?.induced_h, 1));
    case "parada_propia": {
      const tap = a.hours ?? row?.tap ?? null;
      const n = row?.nap ?? null;
      return T.alertText.own(a.op, num(tap, 1), n, n && tap ? durationText((3600 * tap) / n) : null);
    }
    case "prediccion": {
      const fc = station?.forecast?.metric === "tap_h" ? station.forecast : null;
      const k = fc && a.day ? fc.days.indexOf(a.day) : -1;
      return T.alertText.band(a.op, num(a.hours ?? row?.tap, 1), num(k >= 0 ? fc!.p90[k] : null, 1));
    }
    default:
      return { title: a.title, detail: a.detail };
  }
}

/** Avisos con filtros por gravedad, tipo, tramo, estación, día y leído. Pulsar uno lleva a la máquina y al día. */
export function AlertsPanel() {
  const T = useT();
  const lang = useUI((s) => s.lang);
  const { model, alerts, day, tramos } = useDash();
  const f = useUI((s) => s.filters);
  const setFilters = useUI((s) => s.setFilters);
  const closePanel = useUI((s) => s.closePanel);
  const markRead = useUI((s) => s.markRead);
  const markUnread = useUI((s) => s.markUnread);

  const list = applyFilters(alerts, f, day);
  const unread = list.filter((a) => a.unread);
  const ops = [...new Set(alerts.map((a) => a.op))].sort();
  const filtered = JSON.stringify(f) !== JSON.stringify(NO_FILTERS);

  const open = (a: AlertView) => {
    const ui = useUI.getState();
    if (a.day && a.day !== day) ui.setDay(a.day);
    ui.select(a.op, true);
    markRead([a.id]);
  };

  return (
    <aside className="panel" aria-label={T.alerts.title}>
      <header className="panel-head">
        <div>
          <h2>{T.alerts.title}</h2>
          <p>{T.alerts.count(list.length)} · {T.alerts.unread(unread.length)}</p>
        </div>
        <button className="icon-btn ghost" onClick={closePanel} aria-label={T.alerts.close}>
          <IconClose />
        </button>
      </header>

      <div className="filters">
        <div className="seg" role="group" aria-label={T.alerts.days}>
          <button aria-pressed={f.days === "dia"} onClick={() => setFilters({ days: "dia" })}>{dayLong(day)}</button>
          <button aria-pressed={f.days === "todos"} onClick={() => setFilters({ days: "todos" })}>{T.alerts.allDays}</button>
        </div>
        <div className="seg" role="group" aria-label={T.alerts.severity}>
          <button aria-pressed={f.severity === "todas"} onClick={() => setFilters({ severity: "todas" })}>{T.alerts.allF}</button>
          {(Object.keys(SEVERITY) as AlertSeverity[]).map((s) => (
            <button key={s} aria-pressed={f.severity === s} onClick={() => setFilters({ severity: s })}>
              <i className="dot" style={{ background: SEVERITY[s].css }} />{T.severity[s]}
            </button>
          ))}
        </div>
        <div className="selects">
          <label>
            <span>{T.alerts.type}</span>
            <select value={f.type} onChange={(e) => setFilters({ type: e.target.value as AlertType | "todos" })}>
              <option value="todos">{T.alerts.allM}</option>
              {ALERT_TYPES.map((t) => <option key={t} value={t}>{T.alertType[t]}</option>)}
            </select>
          </label>
          <label>
            <span>{T.alerts.tramo}</span>
            <select value={f.tramo} onChange={(e) => setFilters({ tramo: Number(e.target.value) })}>
              <option value={-1}>{T.alerts.allM}</option>
              {tramos.map((t) => <option key={t.i} value={t.i}>{tramoName(T, t)}</option>)}
            </select>
          </label>
          <label>
            <span>{T.alerts.station}</span>
            <select value={f.op} onChange={(e) => setFilters({ op: e.target.value })}>
              <option value="">{T.alerts.allF}</option>
              {ops.map((op) => <option key={op} value={op}>{op}</option>)}
            </select>
          </label>
        </div>
        <div className="filter-foot">
          <label className="check">
            <input type="checkbox" checked={f.unread} onChange={(e) => setFilters({ unread: e.target.checked })} />
            {T.alerts.onlyUnread}
          </label>
          {filtered ? <button className="link" onClick={() => setFilters(NO_FILTERS)}>{T.alerts.clear}</button> : null}
          <button className="link" disabled={!unread.length} onClick={() => markRead(unread.map((a) => a.id))}>{T.alerts.markAll}</button>
        </div>
      </div>

      <ul className="panel-body alerts">
        {list.length === 0 ? <li className="empty">{T.alerts.empty}</li> : null}
        {list.slice(0, SHOWN).map((a) => {
          const text = alertText(T, lang, a, model);
          const mark = a.unread ? T.alerts.markRead : T.alerts.markUnread;
          return (
            <li key={a.id} className={a.unread ? "unread" : ""}>
              <button className="alert" onClick={() => open(a)}>
                <i className="sev" style={{ background: SEVERITY[a.severity].css }} aria-label={T.severity[a.severity]} />
                <span className="txt">
                  <b>{text.title}</b>
                  <span>{text.detail}</span>
                  <small>{a.day ? dayLong(a.day) : T.alerts.period} · {tramos[a.tramo] ? tramoName(T, tramos[a.tramo]) : T.alerts.noTramo} · {T.alertType[a.type] ?? a.type}</small>
                </span>
              </button>
              <button className="read-toggle" onClick={() => (a.unread ? markRead([a.id]) : markUnread([a.id]))} title={mark} aria-label={mark}>
                <i className={a.unread ? "ring full" : "ring"} />
              </button>
            </li>
          );
        })}
        {list.length > SHOWN ? <li className="empty">{T.alerts.more(list.length - SHOWN)}</li> : null}
      </ul>
    </aside>
  );
}
