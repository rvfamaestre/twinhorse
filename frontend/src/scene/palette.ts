/**
 * Colores de la planta. Regla: en la escena solo los estados llevan color vivo;
 * máquinas, suelo y personas van en neutros para que un estado anormal salte a la vista.
 */
export const C = {
  bg: 0xf5f5f5,
  floor: 0xd9d9d9,
  floorLine: 0xcbcbcb,
  walkway: 0xd0d0d0,
  white: 0xf3f4f5,
  wall: 0xeeeeee,
  wallBand: 0xd4d4d4,
  column: 0xe1e1e1,
  window: 0xe4e8eb,
  alu: 0xb9c0c7,
  steel: 0x8f979f,
  bed: 0x596169,
  body: 0xe2e5e8,
  bodyMid: 0xc3cad1,
  slate: 0x47535f,
  graphite: 0x2c3239,
  black: 0x1c1f23,
  accent: 0x3d6877,
  screen: 0x1d3145,
  mat: 0x2a2e33,
  binGrey: 0x8f9aa5,
  binTan: 0xc8aa7a,
  robot: 0xeef0f1,
  glass: 0xb7cfdc,
  curtain: 0xd6dadd,
  skin: 0xd9b28f,
  shirt: 0x5c7088,
  trousers: 0x303a46,
  cast: 0xa7aeb5,
  castLight: 0xc6ccd1,
  plastic: 0x23272c,
  shield: 0xd8dcdf,
  pallet: 0x77828d,
};

export type Theme = "light" | "dark";

/** Lo que cambia con el modo oscuro: la nave (fondo, suelo, paredes) y lo que se pinta en el suelo. Las máquinas no cambian. */
export interface Env {
  bg: number;
  floor: number;
  floorLine: number;
  walkway: number;
  wall: number;
  wallBand: number;
  column: number;
  window: number;
  pad: number; // suelo pintado bajo cada puesto
  joint: number; // juntas del suelo
  title: string; // rótulo de cada tramo en el pasillo
  ring: number; // anillo de la estación elegida
}

export const ENV: Record<Theme, Env> = {
  light: {
    bg: C.bg, floor: C.floor, floorLine: C.floorLine, walkway: C.walkway, wall: C.wall, wallBand: C.wallBand,
    column: C.column, window: C.window, pad: 0xb5babf, joint: 0xbdc1c5, title: "rgba(13,13,13,0.22)", ring: 0x1c1f23,
  },
  dark: {
    bg: 0x141517, floor: 0x26292d, floorLine: 0x3a3e44, walkway: 0x30343a, wall: 0x1d2024, wallBand: 0x2b2f34,
    column: 0x23262a, window: 0x2d3944, pad: 0x3a3f45, joint: 0x2f3337, title: "rgba(255,255,255,0.2)", ring: 0xf2f2f2,
  },
};

/** Colores de estado (los del plan del equipo). Los comparten la escena, la leyenda y los paneles. */
export const STATE_HEX = {
  work: 0x30a46c,
  own: 0xe5484d,
  starved: 0xf0a530,
  blocked: 0x3e8bf0,
  off: 0x5f6170,
  nodata: 0x8b8d98,
  gap: 0x9aa0a8,
};
