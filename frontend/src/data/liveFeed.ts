import { create } from "zustand";
import type { LineState } from "../contract/types";
import { validateLineState } from "../contract/validate";
import { type LineDataSource, POLL_SECONDS, SOURCE_MODE, apiSource, mockSource } from "./sources";

/**
 * Carga de datos con sondeo: prueba la API y, si no responde, enseña el mock y sigue probando.
 * El resto del dashboard solo ve `state`, de dónde viene y un aviso de sistema si hay algo que contar.
 */
export type Connection = "connecting" | "online" | "fallback" | "offline";

export type NoticeKey = "newData" | "connected" | "lost" | "contract";

/** Mensaje del sistema: qué ha pasado y sus datos; el texto lo pone la interfaz en su idioma. */
export interface Notice {
  id: string;
  level: "info" | "ok" | "error";
  key: NoticeKey;
  params?: { source: "api" | "mock"; count: number; path: string };
}

interface DataState {
  state: LineState | null;
  source: LineDataSource | null;
  connection: Connection;
  lastOk: number | null;
  error: string | null;
  notice: Notice | null;
  refresh(): void;
  dismiss(): void;
}

export const useData = create<DataState>((set) => ({
  state: null,
  source: null,
  connection: "connecting",
  lastOk: null,
  error: null,
  notice: null,
  refresh: () => tick(true),
  dismiss: () => set({ notice: null }),
}));

const api = apiSource();
const mock = mockSource();
let timer: ReturnType<typeof setTimeout> | null = null;
let failures = 0;
let started = false;
let inflight: AbortController | null = null;

const say = (level: Notice["level"], key: NoticeKey, params?: Notice["params"]) =>
  useData.setState({ notice: { id: `${Date.now()}`, level, key, params } });

function schedule(seconds: number) {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => tick(false), seconds * 1000);
}

async function load(source: LineDataSource, signal: AbortSignal): Promise<void> {
  const res = await source.fetchLine(signal);
  const now = Date.now();
  if (res.notModified) {
    useData.setState({ lastOk: now });
    return;
  }
  const { state, issues } = validateLineState(res.data);
  if (!state) throw new Error(`no cumple el contrato (${issues[0]?.path}: ${issues[0]?.problem})`);
  if (issues.length) say("info", "contract", { source: source.kind, count: issues.length, path: issues[0].path });
  const prev = useData.getState();
  const same = prev.state && prev.source?.kind === source.kind && prev.state.meta.generated_at === state.meta.generated_at;
  if (same) {
    useData.setState({ lastOk: now });
    return;
  }
  if (prev.state && prev.source?.kind === source.kind) say("ok", "newData");
  useData.setState({ state, source, lastOk: now, error: null });
}

async function tick(manual: boolean) {
  inflight?.abort();
  const ctrl = new AbortController();
  inflight = ctrl;
  const timeout = setTimeout(() => ctrl.abort(), 8000);
  const current = useData.getState();
  try {
    if (SOURCE_MODE === "mock") {
      await load(mock, ctrl.signal);
      useData.setState({ connection: "fallback" });
      schedule(POLL_SECONDS);
      return;
    }
    await load(api, ctrl.signal);
    if (current.connection === "fallback" || current.connection === "offline") say("ok", "connected");
    failures = 0;
    useData.setState({ connection: "online" });
    schedule(POLL_SECONDS);
  } catch (err) {
    if (ctrl.signal.aborted && inflight !== ctrl) return; // la ha sustituido otra consulta
    failures += 1;
    const msg = err instanceof Error ? err.message : String(err);
    useData.setState({ error: msg });
    if (SOURCE_MODE === "auto" && !current.state) {
      // Sin API al arrancar: se enseña el mock y se sigue probando la API.
      try {
        await load(mock, ctrl.signal);
        useData.setState({ connection: "fallback" });
      } catch (e) {
        useData.setState({ connection: "offline", error: e instanceof Error ? e.message : String(e) });
      }
    } else if (current.connection === "online") {
      useData.setState({ connection: "offline" });
      say("error", "lost");
    } else if (!current.state) {
      useData.setState({ connection: "offline" });
    }
    // Reintentos con espera creciente (5 s, 10 s, 20 s… hasta el intervalo normal).
    schedule(manual ? POLL_SECONDS : Math.min(POLL_SECONDS, 5 * 2 ** Math.min(failures - 1, 3)));
  } finally {
    clearTimeout(timeout);
  }
}

export function startLiveFeed() {
  if (started) return;
  started = true;
  tick(false);
  // Al volver a la pestaña, se consulta enseguida en vez de esperar al siguiente intervalo.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") tick(false);
  });
}
