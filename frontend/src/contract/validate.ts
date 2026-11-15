import type { LineState, Status } from "./types";

const STATUSES: Status[] = ["propia", "inducida_anterior", "inducida_siguiente", "dato_no_fiable", "fuera_servicio", "ok"];

export interface ContractIssue {
  path: string;
  problem: string;
}

/**
 * Comprobación ligera del contrato. No para el dashboard: devuelve los problemas
 * para que salgan como notificación y se pinte lo que sí se puede.
 */
export function validateLineState(data: unknown): { state: LineState | null; issues: ContractIssue[] } {
  const issues: ContractIssue[] = [];
  const d = data as Partial<LineState> | null;
  if (!d || typeof d !== "object") return { state: null, issues: [{ path: "/", problem: "la respuesta no es un objeto JSON" }] };
  if (!d.meta || !Array.isArray(d.meta.days)) issues.push({ path: "meta.days", problem: "falta la lista de días" });
  if (!Array.isArray(d.stations)) return { state: null, issues: [...issues, { path: "stations", problem: "falta la lista de estaciones" }] };

  d.stations.forEach((s, i) => {
    const at = `stations[${i}]${s?.op ? ` (${s.op})` : ""}`;
    if (!s?.op) issues.push({ path: at, problem: "estación sin nombre (op)" });
    if (typeof s?.order !== "number") issues.push({ path: `${at}.order`, problem: "sin orden en la línea" });
    if (!STATUSES.includes(s?.status as Status)) issues.push({ path: `${at}.status`, problem: `estado desconocido «${s?.status}»` });
    if (!s?.kpi) issues.push({ path: `${at}.kpi`, problem: "sin KPIs" });
    if (!Array.isArray(s?.daily)) issues.push({ path: `${at}.daily`, problem: "sin serie diaria" });
  });
  if (!Array.isArray(d.ranking)) issues.push({ path: "ranking", problem: "falta el ranking" });

  const state: LineState = {
    meta: {
      line: d.meta?.line ?? "línea",
      required_h: d.meta?.required_h ?? 22,
      targets: d.meta?.targets ?? { tcy_cmin: 80, dp_pct: 90 },
      days: d.meta?.days ?? [],
      ...d.meta,
    },
    stations: d.stations
      .filter((s) => s?.op && typeof s.order === "number")
      .map((s) => ({
        ...s,
        flags: s.flags ?? [],
        daily: Array.isArray(s.daily) ? s.daily : [],
        status: STATUSES.includes(s.status) ? s.status : "dato_no_fiable",
        penalty: s.penalty ?? { rank: null, own_h: 0, induced_on_neighbours_h: 0 },
        forecast: s.forecast ?? null,
        explanation: s.explanation ?? "",
      })),
    ranking: Array.isArray(d.ranking) ? d.ranking : [],
    ranking_own: d.ranking_own,
    quality: d.quality,
    topology: d.topology && Array.isArray(d.topology.links) ? d.topology : undefined,
    alerts: Array.isArray(d.alerts) ? d.alerts.filter((a) => a?.id && a?.op && a?.title) : undefined,
  };
  return { state, issues };
}
