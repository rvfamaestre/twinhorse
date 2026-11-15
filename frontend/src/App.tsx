import { type CSSProperties, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { startLiveFeed, useData } from "./data/liveFeed";
import { ofDay, viewAlerts, worstByOp } from "./domain/alerts";
import { type Layout, type Tramo, snakeLayout } from "./domain/layout";
import { LineScene } from "./scene/Scene";
import { buildPlant } from "./scene/models";
import { advanceClock, clock } from "./state/clock";
import { type LineModel, dayRun, takeSnap, useLineModel, useTramos, useViewport } from "./state/line";
import { useUI } from "./state/ui";
import { AlertsPanel } from "./ui/AlertsPanel";
import { BottomBar } from "./ui/BottomBar";
import { LegendCard } from "./ui/Legend";
import { ForecastView } from "./ui/ForecastView";
import { EdgeNav, Hint, HoverTip, Notice, Splash } from "./ui/Overlays";
import { StationPanel } from "./ui/StationPanel";
import { TopBar } from "./ui/TopBar";
import { type Dash, DashCtx } from "./ui/ctx";

const PANEL_W = 400;
const GAP = 0; // barras y paneles van pegados al borde: sin tarjetas flotantes

/** Alto real de una barra, para que ni la cámara ni los paneles se metan debajo. */
function useHeight(selector: string, fallback: number): number {
  const [h, setH] = useState(fallback);
  useLayoutEffect(() => {
    const el = document.querySelector(selector);
    if (!el) return;
    const read = () => setH(Math.round(el.getBoundingClientRect().height));
    read();
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, [selector]);
  return h;
}

/** Atajos: ← → cambian de tramo, espacio pausa el histórico, V abre la vista general y Esc cierra lo último abierto. */
function useShortcuts(tramoCount: number) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName ?? "";
      const ui = useUI.getState();
      if (ui.view !== "plant") return; // la predicción usa el teclado para sus propios controles
      if (e.key === "Escape") {
        if (ui.legend != null) ui.setLegend(null);
        else if (ui.panel !== "none") ui.closePanel();
        else if (ui.overview) ui.setOverview(false);
        return;
      }
      // Con el foco en un control con teclas propias (deslizador, desplegable), mandan las suyas.
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || el?.isContentEditable) return;
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        const step = ui.overview ? 0 : e.key === "ArrowRight" ? 1 : -1;
        ui.goTramo(Math.min(tramoCount - 1, Math.max(0, ui.tramo + step)));
      } else if (e.key === " " && tag !== "BUTTON" && tag !== "SUMMARY") {
        if (ui.mode !== "history") return;
        e.preventDefault();
        ui.setPlaying(!ui.playing);
      } else if (e.key === "v" || e.key === "V") {
        ui.setOverview(!ui.overview);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tramoCount]);
}

/** Al cambiar entre recta y serpenteada se sigue mirando el mismo trozo de línea. */
function useKeepPlace(lay: Layout, tramos: Tramo[]) {
  const prev = useRef({ lay, tramos });
  useEffect(() => {
    const old = prev.current;
    prev.current = { lay, tramos };
    if (old.lay === lay) return;
    const ui = useUI.getState();
    if (ui.overview) {
      ui.setOverview(true);
      return;
    }
    const was = old.tramos[ui.tramo];
    const node = was?.nodes[0];
    const idx = was?.kind === "aux" ? tramos.findIndex((t) => t.kind === "aux") : node != null ? tramos.findIndex((t) => t.nodes.includes(node)) : -1;
    ui.goTramo(Math.max(0, idx));
  }, [lay, tramos]);
}

function Dashboard({ model }: { model: LineModel }) {
  const vp = useViewport();
  const shape = useUI((s) => s.shape);
  const theme = useUI((s) => s.theme);
  // La simulación usa siempre la planta recta (model.lay); esta es la que se dibuja.
  const lay = useMemo(() => (shape === "snake" ? snakeLayout(model.g, model.lay) ?? model.lay : model.lay), [model, shape]);
  const tramos = useTramos(model, lay, vp.w);
  useKeepPlace(lay, tramos);
  const mode = useUI((s) => s.mode);
  const picked = useUI((s) => s.day);
  const panel = useUI((s) => s.panel);
  const selected = useUI((s) => s.selected);
  const legend = useUI((s) => s.legend);
  const view = useUI((s) => s.view);
  const read = useUI((s) => s.read);
  const scrubs = useUI((s) => s.scrubs);
  const narrow = vp.w < 760;
  const compact = vp.w < 1440;

  const days = model.state.meta.days;
  const last = days[days.length - 1];
  const day = mode === "live" || !picked || !days.includes(picked) ? last : picked;
  const run = useMemo(() => dayRun(model, day), [model, day]);
  const plant = useMemo(() => buildPlant(model.g, lay, theme), [model, lay, theme]);

  const tramoOf = useMemo(() => {
    const map = new Map<string, number>();
    for (const t of tramos) {
      for (const i of t.nodes) map.set(model.g.nodes[i].op, t.i);
      for (const i of t.aux) map.set(model.g.aux[i].op, t.i);
    }
    return (op: string) => map.get(op) ?? -1;
  }, [model, tramos]);
  const alerts = useMemo(() => viewAlerts(model.state.alerts, tramoOf, read), [model, tramoOf, read]);
  const dayAlerts = useMemo(() => ofDay(alerts, day), [alerts, day]);
  const markers = useMemo(() => worstByOp(dayAlerts), [dayAlerts]);

  // Foto del instante, cuatro veces por segundo: la interfaz no necesita más.
  const [snapState, setSnap] = useState(() => takeSnap(model, run, clock.t));
  useEffect(() => {
    clock.horizon = run.sim.horizon;
    const tick = () => {
      advanceClock(0);
      setSnap(takeSnap(model, run, Math.min(clock.t, clock.horizon)));
    };
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [model, run, scrubs]);
  const snap = snapState.day === run.day && snapState.states.length === model.g.nodes.length ? snapState : takeSnap(model, run, clock.t);

  const topH = useHeight(".top", 110);
  const bottomH = useHeight(".bottom", 120);
  const open = panel !== "none";
  const insets = useMemo(
    () => narrow
      ? { top: topH + GAP * 2, right: 0, bottom: open ? Math.round(vp.h * 0.52) + GAP : bottomH + GAP * 2, left: 0 }
      : { top: topH + GAP * 2, right: open ? PANEL_W + GAP * 2 : 0, bottom: bottomH + GAP * 2, left: 0 },
    [narrow, open, topH, bottomH, vp.h],
  );
  useShortcuts(tramos.length);

  const dash: Dash = { model, tramos, tramoOf, run, day, live: mode === "live", snap, alerts, dayAlerts, narrow, compact };
  const vars = { "--top-h": `${topH}px`, "--bottom-h": `${bottomH}px`, "--panel-w": `${PANEL_W}px` } as CSSProperties;
  const cls = ["app", narrow && "narrow", compact && "compact", open && "with-panel", legend != null && "with-legend"].filter(Boolean).join(" ");

  return (
    <DashCtx.Provider value={dash}>
      <div className={cls} style={vars}>
        <LineScene model={model} lay={lay} theme={theme} plant={plant} run={run} tramos={tramos} insets={insets} alerts={markers} />
        {view === "plant" ? (
          <>
            <EdgeNav />
            <LegendCard />
            {panel === "station" && selected ? <StationPanel key={selected} op={selected} /> : null}
            {panel === "alerts" ? <AlertsPanel /> : null}
            <Hint />
            <BottomBar />
            <HoverTip />
          </>
        ) : (
          <ForecastView />
        )}
        <TopBar />
      </div>
    </DashCtx.Provider>
  );
}

export function App() {
  useEffect(startLiveFeed, []);
  const theme = useUI((s) => s.theme);
  const lang = useUI((s) => s.lang);
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
  }, [theme]);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const model = useLineModel();
  const connection = useData((s) => s.connection);
  const error = useData((s) => s.error);
  if (!model) return <Splash error={connection === "offline" ? error ?? "" : null} />;
  return (
    <>
      <Dashboard model={model} />
      <Notice />
    </>
  );
}
