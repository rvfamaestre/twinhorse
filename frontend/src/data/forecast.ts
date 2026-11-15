/**
 * Predicción al momento: la calcula la API (backend/api.py) con TimesFM o una referencia.
 * El navegador no ejecuta ningún modelo: manda la serie, la ventana y el horizonte, y pinta los deciles.
 */
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

export interface ForecastOptions {
  line: string;
  series: { id: string; label: string; metrics: string[] }[];
  metrics: { id: string; label: string; unit: string }[];
  dates: string[];
  models: { id: string; label: string; ready: boolean }[];
  limits: { min_context: number; max_horizon: number };
  quantiles: string[];
}

export interface ForecastRequest {
  series: string;
  metric: string;
  context: number;
  horizon: number;
  origin: string | null;
  model: string;
}

export type Deciles = Record<"p10" | "p20" | "p30" | "p40" | "p50" | "p60" | "p70" | "p80" | "p90", (number | null)[]>;

export interface ForecastResult {
  series: string;
  metric: string;
  model: string;
  model_label: string;
  context: { dates: string[]; values: (number | null)[] };
  forecast: { dates: string[] } & Deciles;
  actual: (number | null)[];
  inside_80: number;
  known: number;
  elapsed_ms: number;
}

async function asJson<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : `La API respondió ${res.status}`);
  }
  return body as T;
}

export async function fetchOptions(signal?: AbortSignal): Promise<ForecastOptions> {
  return asJson(await fetch(`${API_BASE}/forecast/options`, { signal, cache: "no-cache", credentials: "same-origin" }));
}

export async function runForecast(req: ForecastRequest, signal?: AbortSignal): Promise<ForecastResult> {
  return asJson(await fetch(`${API_BASE}/forecast`, {
    method: "POST",
    signal,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(req),
  }));
}

/** Factor que la estimación del día tiene en cuenta, con su valor (el de la víspera y la media, si es del pasado). */
export interface EstimateFactor {
  id: "dia_semana" | "tras_parada" | "vispera_parada" | "motores_previos" | "tap_linea" | "des_linea" | "sat_linea";
  value: number | boolean | null;
  mean?: number | null;
  unit?: string;
}

/** Motores previstos para un día con lo que se sabía la víspera (GET /api/estimate). */
export interface Estimate {
  day: string;
  context_days: number;
  model: string;
  model_label: string;
  covariates: boolean;
  deciles: { [K in keyof Deciles]: number | null };
  reference: { model: string; p50: number | null };
  actual: number | null;
  factors: EstimateFactor[];
  elapsed_ms: number;
}

export async function fetchEstimate(day: string, signal?: AbortSignal): Promise<Estimate> {
  return asJson(await fetch(`${API_BASE}/estimate?day=${encodeURIComponent(day)}`, { signal, cache: "no-cache", credentials: "same-origin" }));
}
