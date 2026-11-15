import type { Alert, AlertSeverity, AlertType } from "../contract/types";
import type { AlertFilters } from "../state/ui";

/**
 * Presentación de los avisos. Qué es un aviso lo decide el backend (campo `alerts` del contrato);
 * aquí solo se ordenan, se filtran y se cruzan con el tramo en que cae cada estación.
 */
export const SEVERITY: Record<AlertSeverity, { rank: number; css: string }> = {
  critica: { rank: 0, css: "#d43d43" },
  aviso: { rank: 1, css: "#c7810f" },
  info: { rank: 2, css: "#5b6470" },
};

/** Tipos de aviso, en el orden del filtro. Sus nombres están en i18n (`alertType`). */
export const ALERT_TYPES: AlertType[] = ["frena_linea", "parada_propia", "prediccion", "dato"];

export interface AlertView extends Alert {
  tramo: number; // -1 si la estación no cae en ningún tramo
  unread: boolean;
}

export function viewAlerts(alerts: Alert[] | undefined, tramoOf: (op: string) => number, read: Record<string, true>): AlertView[] {
  return (alerts ?? []).map((a) => ({ ...a, tramo: tramoOf(a.op), unread: !read[a.id] }));
}

/** Avisos de un día: los suyos y los que valen para todo el periodo. */
export const ofDay = (alerts: AlertView[], day: string) => alerts.filter((a) => a.day === day || a.day === null);

export function applyFilters(alerts: AlertView[], f: AlertFilters, day: string): AlertView[] {
  return alerts
    .filter((a) => (f.days === "todos" ? true : a.day === day || a.day === null))
    .filter((a) => f.severity === "todas" || a.severity === f.severity)
    .filter((a) => f.type === "todos" || a.type === f.type)
    .filter((a) => f.tramo < 0 || a.tramo === f.tramo)
    .filter((a) => !f.op || a.op === f.op)
    .filter((a) => !f.unread || a.unread)
    .sort(byUrgency);
}

/** Primero lo no leído, luego lo más grave, luego lo que más horas tiene en juego, luego lo más reciente. */
export function byUrgency(a: AlertView, b: AlertView): number {
  return (
    Number(b.unread) - Number(a.unread) ||
    SEVERITY[a.severity].rank - SEVERITY[b.severity].rank ||
    (b.hours ?? 0) - (a.hours ?? 0) ||
    (b.day ?? "").localeCompare(a.day ?? "") ||
    a.op.localeCompare(b.op)
  );
}

/** El aviso más grave de cada estación (para el icono sobre la máquina). */
export function worstByOp(alerts: AlertView[]): Map<string, AlertView> {
  const out = new Map<string, AlertView>();
  for (const a of alerts) {
    const cur = out.get(a.op);
    if (!cur) out.set(a.op, { ...a });
    else {
      const worse = SEVERITY[a.severity].rank < SEVERITY[cur.severity].rank;
      out.set(a.op, { ...(worse ? a : cur), unread: cur.unread || a.unread });
    }
  }
  return out;
}
