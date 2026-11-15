/**
 * Contrato JSON entre el backend (Rol 1 + Rol 2) y el dashboard (Rol 3).
 * Es el mismo de la sección «Arquitectura y contrato de datos» del plan.
 * Los campos marcados como «extensión» los propone el Rol 3 y son opcionales:
 * si la API no los manda, el dashboard sigue funcionando.
 */

export type Status =
  | "propia"
  | "inducida_anterior"
  | "inducida_siguiente"
  | "dato_no_fiable"
  | "fuera_servicio"
  | "ok";

export type Group = "main" | "subassembly" | "manipulator";

export interface Kpi {
  dp: number | null; // %
  tcy: number | null; // cmin
  fpm: number | null; // paradas propias cada 1.000 piezas
  tbf_h: number;
  tap_h: number;
  des_h: number;
  sat_h: number;
  s_per_stop?: number | null; // extensión: segundos por parada propia
}

export interface Penalty {
  rank: number | null;
  own_h: number;
  induced_on_neighbours_h: number;
  blocking_days?: number; // extensión: días que cumple la regla de las flechas
  blocked_neighbours?: string[]; // extensión: vecinas a las que frena
}

export interface DailyRow {
  day: string; // ISO yyyy-mm-dd
  tbf: number | null;
  tap: number | null;
  des: number | null;
  sat: number | null;
  npr: number;
  npr_ef?: number; // extensión: piezas con el contador corregido (el del pipeline de limpieza)
  nap?: number;
  dp?: number | null;
  status: Status;
  flags?: string[]; // extensión
  timeline?: TimelineSpan[]; // extensión: paradas reales con su hora, si algún día las hay (MES). Sustituye a la simulación.
  blocks_line?: boolean; // extensión: ese día cumple la regla de las flechas
  induced_h?: number; // extensión: horas que hace perder a sus vecinas ese día
}

/** Extensión: tramo horario real de un estado. `t0` y `t1` en horas desde el inicio del periodo. */
export interface TimelineSpan {
  t0: number;
  t1: number;
  state: "propia" | "sin_registro";
}

export interface Forecast {
  metric: string; // tap_h, des_h…
  model?: string; // extensión: chronos-2, mock…
  context_days?: string[];
  days: string[];
  p10: number[];
  p50: number[];
  p90: number[];
}

export interface Station {
  op: string;
  order: number;
  group: Group;
  parallel_with: string | null;
  uvt?: string | null; // extensión: unidad de trabajo, cuando la planta la confirme
  branch?: string | null; // extensión: a qué rama (subconjunto) pertenece
  kind?: StationKind | null; // extensión: tipo de puesto, solo para dibujarlo
  kpi: Kpi;
  status: Status;
  flags: string[];
  in_ranking?: boolean;
  penalty: Penalty;
  explanation: string;
  daily: DailyRow[];
  forecast: Forecast | null;
}

export type StationKind = "auto" | "manual" | "manipulator";
export type Confidence = "alta" | "media" | "baja" | "config";

/** Extensión: por dónde van las piezas. El config solo da el orden, así que es una hipótesis. */
export interface TopologyLink {
  from: string;
  to: string;
  kind: "serie" | "paralelo" | "lateral" | "subconjunto";
  buffer?: boolean; // hay un pulmón entre las dos
  branch?: string;
  confidence?: Confidence;
}

export interface TopologyNote {
  title: string;
  detail: string;
  ops: string[];
  confidence: Confidence;
}

export interface Topology {
  hypothesis: boolean; // true: deducida de los datos; false: confirmada por la planta
  links: TopologyLink[];
  assists?: { op: string; to: string | null; confidence?: Confidence; evidence?: string }[];
  notes?: TopologyNote[];
}

export interface QualityRule {
  regla: string;
  que_pasa: string;
  filas: number;
  operaciones: number;
  donde: string;
  decision: string;
}

/** Extensión: avisos ya decididos por el backend. El dashboard solo los ordena, filtra y marca como leídos. */
export type AlertSeverity = "critica" | "aviso" | "info";
export type AlertType = "frena_linea" | "parada_propia" | "prediccion" | "dato";

export interface Alert {
  id: string; // estable entre cargas: sirve para recordar cuáles se han leído
  day: string | null; // null = vale para todo el periodo
  op: string;
  severity: AlertSeverity;
  type: AlertType;
  title: string;
  detail: string;
  hours?: number | null; // horas en juego, para ordenar
}

export interface LineState {
  meta: {
    line: string;
    required_h: number;
    targets: { tcy_cmin: number; dp_pct: number };
    days: string[];
    excluded_days?: string[]; // extensión
    generated_at?: string; // extensión: para saber si hay datos nuevos
    source?: string; // extensión: mock | api
    provisional?: string[]; // extensión: campos que aún son de prueba
  };
  stations: Station[];
  ranking: string[]; // «frena la línea» (índice de penalización)
  ranking_own?: string[]; // extensión: «se para mucho» (horas propias)
  quality?: QualityRule[]; // extensión: tabla de calidad del dato
  topology?: Topology; // extensión: sin ella, la línea se dibuja en serie por `order`
  alerts?: Alert[]; // extensión: sin ella, no hay avisos
}

export interface WhatIfRequest {
  op: string;
  dp_target: number;
}

export interface WhatIfResult {
  op: string;
  dp_target: number;
  motors_per_day_now: number;
  motors_per_day_after: number;
  gain_per_day: number;
  bottleneck?: string;
  note?: string;
}
