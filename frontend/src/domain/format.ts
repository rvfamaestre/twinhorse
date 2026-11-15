import { LANGS, type Lang } from "../i18n/langs";

/** Números y fechas en el idioma de la interfaz (0,6 h en español y francés; 0.6 h en inglés). */
let lang: Lang = "es";
let locale = "es-ES";
const nf = (digits: number) => new Intl.NumberFormat(locale, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
let f0 = nf(0);
let f1 = nf(1);
const more = new Map<number, Intl.NumberFormat>();

/** Lo llama el estado de la interfaz al cambiar de idioma, antes de repintar. */
export function setFormatLang(next: Lang): void {
  lang = next;
  locale = LANGS.find((l) => l.id === next)?.locale ?? "es-ES";
  f0 = nf(0);
  f1 = nf(1);
  more.clear();
}

function fmt(digits: number): Intl.NumberFormat {
  if (digits === 0) return f0;
  if (digits === 1) return f1;
  let f = more.get(digits);
  if (!f) more.set(digits, (f = nf(digits)));
  return f;
}

export const num = (x: number | null | undefined, digits = 1) => (x == null || !Number.isFinite(x) ? "—" : fmt(digits).format(x));

export const hours = (x: number | null | undefined, digits = 1) => (x == null ? "—" : `${num(x, digits)} h`);
export const pct = (x: number | null | undefined) => (x == null ? "—" : `${num(x, 1)} %`);

const WEEKDAY: Record<Lang, string[]> = {
  es: ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"],
  en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  fr: ["dim", "lun", "mar", "mer", "jeu", "ven", "sam"],
};

export function parseDay(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export const dayShort = (day: string) => {
  const d = parseDay(day);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
};

export const weekday = (day: string) => WEEKDAY[lang][parseDay(day).getDay()];

export const dayLong = (day: string) => `${weekday(day)} ${dayShort(day)}`;

export function ago(ts: number | null, now = Date.now()): string {
  if (!ts) return "nunca";
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 5) return "ahora";
  if (s < 60) return `hace ${s} s`;
  const m = Math.round(s / 60);
  if (m < 60) return `hace ${m} min`;
  return `hace ${Math.round(m / 60)} h`;
}
