import type { Status } from "../contract/types";
import { STATE_HEX } from "../scene/palette";
import { S_BLOCKED, S_GAP, S_NODATA, S_OFF, S_OWN, S_STARVED, S_WORK, type SimState } from "../sim/engine";

/**
 * Color de cada estado: uno solo para la escena, la leyenda y los paneles. Cómo se nombra y se
 * explica cada uno en cada idioma está en i18n (`states`).
 */
export interface StateInfo {
  id: SimState;
  hex: number;
  css: string;
}

const css = (hex: number) => `#${hex.toString(16).padStart(6, "0")}`;
const info = (id: SimState, hex: number): StateInfo => ({ id, hex, css: css(hex) });

export const STATES: Record<SimState, StateInfo> = {
  [S_WORK]: info(S_WORK, STATE_HEX.work),
  [S_OWN]: info(S_OWN, STATE_HEX.own),
  [S_STARVED]: info(S_STARVED, STATE_HEX.starved),
  [S_BLOCKED]: info(S_BLOCKED, STATE_HEX.blocked),
  [S_OFF]: info(S_OFF, STATE_HEX.off),
  [S_NODATA]: info(S_NODATA, STATE_HEX.nodata),
  [S_GAP]: info(S_GAP, STATE_HEX.gap),
};

/** Estados que salen en la leyenda, en el orden en que conviene aprenderlos. */
export const LEGEND: SimState[] = [S_WORK, S_OWN, S_STARVED, S_BLOCKED, S_NODATA];

/** El veredicto del día que manda el backend, llevado a los mismos colores. */
export const DAY_STATE: Record<Status, SimState> = {
  ok: S_WORK,
  propia: S_OWN,
  inducida_anterior: S_STARVED,
  inducida_siguiente: S_BLOCKED,
  dato_no_fiable: S_NODATA,
  fuera_servicio: S_OFF,
};
