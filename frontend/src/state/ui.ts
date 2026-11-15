import { create } from "zustand";
import type { AlertSeverity, AlertType } from "../contract/types";
import { setFormatLang } from "../domain/format";
import { LANG_IDS, type Lang } from "../i18n/langs";
import type { Theme } from "../scene/palette";
import type { SimState } from "../sim/engine";

/**
 * Estado de la interfaz: dónde se está mirando (tramo, estación), en qué momento (en directo o
 * histórico) y qué paneles hay abiertos. Nada de datos de la línea: esos van en data/liveFeed.
 */
export type Mode = "live" | "history";
export type Panel = "none" | "station" | "alerts";
/** Qué pantalla se ve: la planta en 3D o la predicción. */
export type View = "plant" | "forecast";
/** Cómo se dibuja la línea: recta (como en el config) o serpenteada en filas. */
export type Shape = "line" | "snake";
/** Por qué se mueve la cámara: a un tramo, a la vista general, a una estación, o lo justo para que no la tape un panel. */
export type Fly = "tramo" | "overview" | "focus" | "reveal";
export const SPEEDS = [1, 10, 60, 600];

export interface AlertFilters {
  severity: AlertSeverity | "todas";
  type: AlertType | "todos";
  tramo: number; // -1 = todos
  op: string; // "" = todas
  days: "dia" | "todos";
  unread: boolean;
}

export const NO_FILTERS: AlertFilters = { severity: "todas", type: "todos", tramo: -1, op: "", days: "dia", unread: false };

const READ_KEY = "lossia.alertas.leidas";
const SHAPE_KEY = "lossia.forma";
const THEME_KEY = "lossia.tema";
const LANG_KEY = "lossia.idioma";
const FORECAST_HASH = "#prediccion";

/** La pantalla va en la URL (#prediccion) para poder enlazarla y para que sobreviva a recargar. */
function viewFromUrl(): View {
  return typeof location !== "undefined" && location.hash === FORECAST_HASH ? "forecast" : "plant";
}

function viewToUrl(view: View) {
  try {
    history.replaceState(null, "", `${location.pathname}${location.search}${view === "forecast" ? FORECAST_HASH : ""}`);
  } catch {
    /* sin historial (vista previa): no pasa nada */
  }
}

/** Preferencias de quien mira (forma de la línea, tema): solo en su navegador. */
function loadPref<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
  } catch {
    return fallback;
  }
}

function savePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* sin almacenamiento: dura lo que dura la pestaña */
  }
}

function loadRead(): Record<string, true> {
  try {
    const raw = localStorage.getItem(READ_KEY);
    return raw ? (JSON.parse(raw) as Record<string, true>) : {};
  } catch {
    return {}; // sin almacenamiento (modo privado): las leídas duran lo que dura la pestaña
  }
}

function saveRead(read: Record<string, true>) {
  try {
    localStorage.setItem(READ_KEY, JSON.stringify(read));
  } catch {
    /* no pasa nada */
  }
}

interface UI {
  view: View;
  shape: Shape;
  theme: Theme;
  lang: Lang;
  forecastSeries: string | null; // serie con la que se abre la predicción (null = la que toque)
  mode: Mode;
  day: string | null; // día elegido en histórico; null = el último con datos
  playing: boolean;
  speed: number;
  scrubs: number; // sube cada vez que se mueve el tiempo a mano, para refrescar al instante

  tramo: number;
  overview: boolean;
  flyId: number; // sube cuando hay que mover la cámara
  flyKind: Fly;

  selected: string | null;
  panel: Panel;
  legend: SimState | null;
  touched: boolean; // ya ha interactuado: se esconde la pista inicial

  filters: AlertFilters;
  read: Record<string, true>;

  setView(view: View): void;
  setShape(shape: Shape): void;
  setTheme(theme: Theme): void;
  setLang(lang: Lang): void;
  openForecast(series: string | null): void;
  goTramo(i: number): void;
  panTramo(i: number): void;
  setOverview(on: boolean): void;
  select(op: string | null, fly?: boolean): void;
  openAlerts(): void;
  closePanel(): void;
  setMode(mode: Mode): void;
  setDay(day: string): void;
  setPlaying(on: boolean): void;
  setSpeed(speed: number): void;
  scrubbed(): void;
  setLegend(s: SimState | null): void;
  setFilters(f: Partial<AlertFilters>): void;
  markRead(ids: string[]): void;
  markUnread(ids: string[]): void;
}

const startLang = loadPref<Lang>(LANG_KEY, LANG_IDS, "es");
setFormatLang(startLang);

export const useUI = create<UI>((set, get) => ({
  view: viewFromUrl(),
  shape: loadPref<Shape>(SHAPE_KEY, ["line", "snake"], "line"),
  theme: loadPref<Theme>(THEME_KEY, ["light", "dark"], "light"),
  lang: startLang,
  forecastSeries: null,
  mode: "live",
  day: null,
  playing: false,
  speed: 60,
  scrubs: 0,
  tramo: 0,
  overview: false,
  flyId: 0,
  flyKind: "tramo",
  selected: null,
  panel: "none",
  legend: null,
  touched: false,
  filters: NO_FILTERS,
  read: loadRead(),

  setView: (view) => {
    viewToUrl(view);
    set({ view, legend: null, touched: true });
  },
  setShape: (shape) => {
    savePref(SHAPE_KEY, shape);
    set({ shape, touched: true });
  },
  setTheme: (theme) => {
    savePref(THEME_KEY, theme);
    set({ theme });
  },
  setLang: (lang) => {
    savePref(LANG_KEY, lang);
    setFormatLang(lang); // antes de repintar: los números ya salen en el formato nuevo
    set({ lang });
  },
  openForecast: (series) => {
    viewToUrl("forecast");
    set({ view: "forecast", forecastSeries: series, legend: null, touched: true });
  },
  goTramo: (i) => set((s) => ({ tramo: i, overview: false, flyKind: "tramo", flyId: s.flyId + 1, touched: true })),
  panTramo: (i) => get().tramo !== i && set({ tramo: i }),
  setOverview: (on) => set((s) => ({ overview: on, flyKind: on ? "overview" : "tramo", flyId: s.flyId + 1, touched: true })),
  select: (op, fly = false) =>
    set((s) => ({
      selected: op,
      panel: op ? "station" : s.panel === "station" ? "none" : s.panel,
      overview: op && fly ? false : s.overview,
      flyKind: op && fly ? "focus" : "reveal",
      flyId: op ? s.flyId + 1 : s.flyId,
      touched: true,
    })),
  openAlerts: () => set((s) => ({ panel: s.panel === "alerts" ? "none" : "alerts", selected: null, touched: true })),
  closePanel: () => set({ panel: "none", selected: null }),
  setMode: (mode) => set((s) => ({ mode, playing: mode === "history", scrubs: s.scrubs + 1, touched: true })),
  setDay: (day) => set((s) => ({ day, mode: "history", scrubs: s.scrubs + 1, touched: true })),
  setPlaying: (on) => set({ playing: on }),
  setSpeed: (speed) => set({ speed }),
  scrubbed: () => set((s) => ({ scrubs: s.scrubs + 1 })),
  setLegend: (legend) => set({ legend, touched: true }),
  setFilters: (f) => set((s) => ({ filters: { ...s.filters, ...f } })),
  markRead: (ids) => {
    const cur = get().read;
    const fresh = ids.filter((id) => !cur[id]);
    if (!fresh.length) return;
    const read = { ...cur };
    for (const id of fresh) read[id] = true;
    saveRead(read);
    set({ read });
  },
  markUnread: (ids) => {
    const read = { ...get().read };
    for (const id of ids) delete read[id];
    saveRead(read);
    set({ read });
  },
}));
