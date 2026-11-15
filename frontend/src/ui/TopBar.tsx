import { useEffect, useState } from "react";
import { type Estimate, type EstimateFactor, fetchEstimate } from "../data/forecast";
import { useData } from "../data/liveFeed";
import { dayLong, hours, num } from "../domain/format";
import { LEGEND, STATES } from "../domain/status";
import { type Dict, useT } from "../i18n";
import { LANGS } from "../i18n/langs";
import { rowOf } from "../sim/day";
import type { LineModel } from "../state/line";
import { useUI } from "../state/ui";
import { useDash } from "./ctx";
import { Flags } from "./flags";
import { IconBell, IconBrake, IconDown, IconHelp, IconMoon, IconSun } from "./icons";
import { Popover, usePopover } from "./Popover";

/** Las que frenaron la línea ese día (dato real), de la que más hace perder a la que menos. */
function brakesOf(model: LineModel, day: string) {
  return model.g.nodes
    .map((n) => ({ op: n.op, row: rowOf(n, day) }))
    .filter((x) => x.row?.blocks_line)
    .map((x) => ({ op: x.op, own: x.row!.tap ?? 0, induced: x.row!.induced_h ?? 0 }))
    .sort((a, b) => b.induced - a.induced || b.own - a.own);
}

/** Desplegable con la tabla de las máquinas que frenaron la línea y sus horas. Pulsar una lleva a ella. */
function BrakesMenu() {
  const T = useT();
  const { model, day } = useDash();
  const select = useUI((s) => s.select);
  const pop = usePopover();
  const brakes = brakesOf(model, day);
  const go = (op: string) => {
    select(op, true);
    pop.close();
  };
  return (
    <Popover
      pop={pop}
      className="brakes-pop"
      button={
        <button className={`pill-btn${pop.open ? " on" : ""}`} onClick={pop.toggle} aria-expanded={pop.open}
          aria-label={T.brakes.aria(brakes.length)} title={T.brakes.tip}>
          <IconBrake />
          <span>{T.brakes.button}</span>
          <b>{brakes.length}</b>
          <IconDown />
        </button>
      }
    >
      <header className="pop-head">
        <b>{T.brakes.head}</b>
        <small>{dayLong(day)} · {T.brakes.real}</small>
      </header>
      {brakes.length ? (
        <table className="brakes-table">
          <thead>
            <tr><th>{T.brakes.machine}</th><th>{T.brakes.own}</th><th>{T.brakes.induced}</th></tr>
          </thead>
          <tbody>
            {brakes.map((b) => (
              <tr key={b.op} onClick={() => go(b.op)}>
                <td><button onClick={(e) => { e.stopPropagation(); go(b.op); }}>{b.op}</button></td>
                <td>{hours(b.own)}</td>
                <td>{hours(b.induced)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="pop-empty">{T.brakes.none}</p>
      )}
    </Popover>
  );
}

/** Guías: la leyenda de estados (cada uno se explica animado y se enciende en la planta) y cómo moverse. */
function HelpMenu() {
  const T = useT();
  const pop = usePopover();
  const legend = useUI((s) => s.legend);
  const setLegend = useUI((s) => s.setLegend);
  return (
    <Popover
      pop={pop}
      className="help-pop"
      button={
        <button className={`icon-btn${pop.open ? " on" : ""}`} onClick={pop.toggle} aria-expanded={pop.open} aria-label={T.help.label} title={T.help.label}>
          <IconHelp />
        </button>
      }
    >
      <section>
        <h3>{T.help.legend}</h3>
        <ul className="help-legend">
          {LEGEND.map((id) => (
            <li key={id}>
              <button aria-pressed={legend === id} onClick={() => { setLegend(legend === id ? null : id); pop.close(); }}>
                <i className="dot" style={{ background: STATES[id].css }} />
                <span>{T.states[id].label}</span>
                <small>{T.states[id].term}</small>
              </button>
            </li>
          ))}
        </ul>
        <p className="help-note">{T.help.legendNote}</p>
      </section>
      <section>
        <h3>{T.help.move}</h3>
        <dl className="keys">
          {T.help.keys.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      </section>
      <section>
        <h3>{T.help.plant}</h3>
        <dl className="keys">
          {T.help.plantKeys.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      </section>
    </Popover>
  );
}

/** Idioma de la interfaz: cada uno escrito en su idioma y con su bandera (el inglés, con la de EE. UU. y la del Reino Unido). */
function LangMenu() {
  const T = useT();
  const lang = useUI((s) => s.lang);
  const setLang = useUI((s) => s.setLang);
  const pop = usePopover();
  const cur = LANGS.find((l) => l.id === lang) ?? LANGS[0];
  return (
    <Popover
      pop={pop}
      className="lang-pop"
      button={
        <button className={`pill-btn lang-btn${pop.open ? " on" : ""}`} onClick={pop.toggle} aria-expanded={pop.open}
          aria-label={`${T.lang.label}: ${cur.name}`} title={T.lang.label}>
          <Flags ids={cur.flags} />
          <span>{cur.short}</span>
          <IconDown />
        </button>
      }
    >
      <ul className="lang-list" role="listbox" aria-label={T.lang.label}>
        {LANGS.map((l) => (
          <li key={l.id}>
            <button role="option" aria-selected={l.id === lang} lang={l.id} onClick={() => { setLang(l.id); pop.close(); }}>
              <Flags ids={l.flags} />
              <span>{l.name}</span>
            </button>
          </li>
        ))}
      </ul>
    </Popover>
  );
}

function ThemeToggle() {
  const T = useT();
  const theme = useUI((s) => s.theme);
  const setTheme = useUI((s) => s.setTheme);
  const dark = theme === "dark";
  const label = dark ? T.theme.light : T.theme.dark;
  return (
    <button className="icon-btn" onClick={() => setTheme(dark ? "light" : "dark")} aria-label={label} title={label}>
      {dark ? <IconSun /> : <IconMoon />}
    </button>
  );
}

/**
 * Estimación del modelo para el día que se ve en «Ahora». Se pide a la API al entrar en «Ahora» o
 * al cambiar el día; mientras TimesFM se carga llega la media y se vuelve a pedir. Sin API, null.
 */
function useEstimate(day: string, live: boolean): Estimate | null {
  const [got, setGot] = useState<Estimate | null>(null);
  useEffect(() => {
    if (!live) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const ctl = new AbortController();
    const load = async () => {
      try {
        const e = await fetchEstimate(day, ctl.signal);
        if (!alive) return;
        setGot(e);
        if (e.model !== "timesfm") timer = setTimeout(load, 5000);
      } catch {
        if (alive) timer = setTimeout(load, 10000);
      }
    };
    load();
    return () => {
      alive = false;
      ctl.abort();
      clearTimeout(timer);
    };
  }, [day, live]);
  return live && got?.day === day ? got : null;
}

function factorValue(T: Dict, f: EstimateFactor): string {
  if (f.id === "dia_semana") return T.est.weekdays[Number(f.value)] ?? "—";
  if (typeof f.value === "boolean") return f.value ? T.est.yes : T.est.no;
  const unit = f.unit === "h" ? " h" : "";
  return `${num(f.value, 0)}${unit} · ${T.est.avg} ${num(f.mean, 0)}${unit}`;
}

/**
 * Motores del día. En «Histórico», los que salieron de verdad hasta la hora que se mira. En «Ahora»
 * el día no ha terminado, así que el total lo estima el modelo (TimesFM con lo que se sabía la víspera
 * y los factores que pueden influir) y lo hecho hasta ahora es ese total al ritmo normal del turno.
 */
function Motors() {
  const T = useT();
  const { snap, day, live } = useDash();
  const est = useEstimate(day, live);
  const pop = usePopover();
  const p50 = est?.deciles.p50;
  if (!est || p50 == null) {
    return (
      <div className="nav-motors" title={T.motors.tip}>
        <strong>{num(snap.made, 0)}</strong>
        <span>{T.motors.of(num(snap.target, 0))}</span>
      </div>
    );
  }
  const total = Math.round(p50);
  const frac = snap.target > 0 ? Math.min(1, snap.made / snap.target) : 0; // parte del turno ya hecha
  const soFar = Math.round(total * frac);
  const diff = est.actual != null ? Math.round(est.actual - p50) : null;
  return (
    <Popover
      pop={pop}
      align="center"
      anchorClassName="nav-motors-anchor"
      className="est-pop"
      button={
        <button className={`nav-motors est${pop.open ? " on" : ""}`} onClick={pop.toggle} aria-expanded={pop.open} title={T.est.tip}>
          <strong>≈ {num(soFar, 0)}</strong>
          <span>{T.est.of(num(total, 0))}</span>
          <IconDown />
        </button>
      }
    >
      <header className="pop-head">
        <b>{T.est.head}</b>
        <small>{dayLong(day)} · {est.model_label}</small>
      </header>
      <div className="est-main">
        <strong>{num(total, 0)}</strong>
        <span>{T.est.engines}</span>
      </div>
      <p className="est-band">{T.est.range(num(est.deciles.p10, 0), num(est.deciles.p90, 0))}</p>
      <dl className="facts">
        <div><dt>{T.est.soFar}</dt><dd>≈ {num(soFar, 0)}<small>{T.est.atPace}</small></dd></div>
        <div><dt>{T.est.history}</dt><dd>{T.est.days(est.context_days)}</dd></div>
      </dl>
      <h4 className="est-h">{T.est.factors}</h4>
      <dl className="facts est-factors">
        {est.factors.map((f) => (
          <div key={f.id}><dt>{T.est.f[f.id] ?? f.id}</dt><dd>{factorValue(T, f)}</dd></div>
        ))}
      </dl>
      {est.actual != null && diff != null ? (
        <p className="est-check">{T.est.check(num(est.actual, 0), `${diff > 0 ? "+" : ""}${num(diff, 0)}`)}</p>
      ) : null}
      <p className="est-note">{est.model === "timesfm" ? T.est.note : T.est.fallback}</p>
    </Popover>
  );
}

/** Barra de navegación: marca, línea, las dos pantallas, motores del día, guías, avisos, tema e idioma. */
function Nav() {
  const T = useT();
  const { model, dayAlerts } = useDash();
  const view = useUI((s) => s.view);
  const setView = useUI((s) => s.setView);
  const panel = useUI((s) => s.panel);
  const openAlerts = useUI((s) => s.openAlerts);
  const connection = useData((s) => s.connection);
  const { meta } = model.state;
  const unread = dayAlerts.filter((a) => a.unread && a.severity !== "info").length;
  return (
    <nav className="nav" aria-label={T.nav.main}>
      <span className="wordmark">LOSSIA</span>
      <span className="crumb">{meta.line.replace(/_/g, " ")}</span>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={view === "plant"} onClick={() => setView("plant")}>{T.nav.plant}</button>
        <button role="tab" aria-selected={view === "forecast"} onClick={() => setView("forecast")}>{T.nav.forecast}</button>
      </div>
      <Motors />
      <div className="nav-side">
        {connection === "offline" ? <span className="offline">{T.nav.offline}</span> : null}
        {view === "plant" ? (
          <>
            <HelpMenu />
            <BrakesMenu />
            <button className={`icon-btn${panel === "alerts" ? " on" : ""}`} onClick={openAlerts} aria-label={T.alertsBtn.aria(unread)} aria-pressed={panel === "alerts"} title={T.alertsBtn.title}>
              <IconBell />
              {unread ? <i className="badge" /> : null}
            </button>
          </>
        ) : null}
        <ThemeToggle />
        <LangMenu />
      </div>
    </nav>
  );
}

export function TopBar() {
  return (
    <header className="top">
      <Nav />
    </header>
  );
}
