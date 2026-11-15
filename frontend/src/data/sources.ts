import type { WhatIfRequest, WhatIfResult } from "../contract/types";

/**
 * Fuentes de datos intercambiables. El resto del dashboard no sabe de dónde vienen:
 * cambiar de mock a la API real, o a otra línea, no toca ningún componente.
 * Todo va al mismo origen (/api): sin claves en el navegador y sin servicios de terceros.
 */
export type SourceKind = "api" | "mock";

export interface FetchResult {
  data?: unknown;
  notModified?: boolean;
}

export interface LineDataSource {
  kind: SourceKind;
  label: string;
  fetchLine(signal: AbortSignal): Promise<FetchResult>;
  whatIf?(req: WhatIfRequest, signal?: AbortSignal): Promise<WhatIfResult>;
}

export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

export function apiSource(base = API_BASE): LineDataSource {
  let etag: string | null = null;
  return {
    kind: "api",
    label: "API",
    async fetchLine(signal) {
      const res = await fetch(`${base}/line`, {
        signal,
        credentials: "same-origin",
        cache: "no-cache",
        headers: { Accept: "application/json", ...(etag ? { "If-None-Match": etag } : {}) },
      });
      if (res.status === 304) return { notModified: true };
      if (!res.ok) throw new HttpError(res.status, `La API respondió ${res.status}`);
      if (!(res.headers.get("content-type") ?? "").includes("json")) throw new HttpError(res.status, "La API no devolvió JSON");
      etag = res.headers.get("ETag");
      return { data: await res.json() };
    },
    async whatIf(req, signal) {
      const res = await fetch(`${base}/whatif`, {
        method: "POST",
        signal,
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new HttpError(res.status, `What-if respondió ${res.status}`);
      return (await res.json()) as WhatIfResult;
    },
  };
}

export function mockSource(): LineDataSource {
  return {
    kind: "mock",
    label: "Datos de prueba",
    async fetchLine(signal) {
      const res = await fetch(`${import.meta.env.BASE_URL}mock/line_state.mock.json`, { signal, cache: "no-cache" });
      if (!res.ok) throw new HttpError(res.status, "No se encuentra el mock (ejecuta npm run mock)");
      return { data: await res.json() };
    },
  };
}

export type SourceMode = "auto" | "api" | "mock";
export const SOURCE_MODE = ((import.meta.env.VITE_DATA_SOURCE as string | undefined) ?? "auto") as SourceMode;
export const POLL_SECONDS = Number(import.meta.env.VITE_POLL_SECONDS ?? 30) || 30;
