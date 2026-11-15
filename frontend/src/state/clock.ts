import { num } from "../domain/format";
import { useUI } from "./ui";

/**
 * Reloj de la simulación: el segundo del día que se está viendo. Vive fuera de React porque
 * cambia en cada fotograma; la interfaz lo lee unas pocas veces por segundo (state/snapshot).
 */
export const clock = { t: 0, horizon: 22 * 3600 };

/** En directo: el día avanza con la hora real (medianoche = inicio, medianoche siguiente = fin). */
export function liveSeconds(horizon: number, now = new Date()): number {
  const s = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds() + now.getMilliseconds() / 1000;
  return (s / 86400) * horizon;
}

export function advanceClock(dt: number): void {
  const ui = useUI.getState();
  if (ui.mode === "live") {
    clock.t = liveSeconds(clock.horizon);
  } else if (ui.playing) {
    clock.t += Math.min(dt, 0.25) * ui.speed; // una pestaña en segundo plano no da un salto al volver
    if (clock.t >= clock.horizon) {
      clock.t = clock.horizon;
      ui.setPlaying(false);
    }
  }
}

export function scrubTo(t: number): void {
  clock.t = Math.min(clock.horizon, Math.max(0, t));
  useUI.getState().scrubbed();
}

/** «07:42» a partir de los segundos transcurridos del día de producción. */
export function clockText(t: number): string {
  const m = Math.floor(Math.max(0, t) / 60);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function wallClockText(now = new Date()): string {
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

export function durationText(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 90) return `${s} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${num(s / 3600, 1)} h`;
}
