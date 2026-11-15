import { createContext, useContext } from "react";
import type { AlertView } from "../domain/alerts";
import type { Tramo } from "../domain/layout";
import type { DayRun } from "../sim/day";
import type { LineModel, Snap } from "../state/line";

/** Lo que comparten todos los paneles: la línea, el día que se mira y la foto del instante. */
export interface Dash {
  model: LineModel;
  tramos: Tramo[];
  tramoOf(op: string): number;
  run: DayRun;
  day: string;
  live: boolean;
  snap: Snap;
  alerts: AlertView[]; // todos
  dayAlerts: AlertView[]; // los del día que se mira
  narrow: boolean; // pantalla estrecha: los paneles van abajo
  compact: boolean; // poco ancho: etiquetas cortas
}

export const DashCtx = createContext<Dash | null>(null);

export function useDash(): Dash {
  const d = useContext(DashCtx);
  if (!d) throw new Error("Falta el contexto del dashboard");
  return d;
}
