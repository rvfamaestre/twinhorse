/** Idiomas de la interfaz. Cada uno se nombra como se escribe en su propio idioma. */
export type Lang = "es" | "en" | "fr";
export type FlagId = "es" | "us" | "gb" | "fr";

export interface LangInfo {
  id: Lang;
  name: string; // en su propio idioma
  short: string;
  flags: FlagId[];
  locale: string; // para números y fechas
}

export const LANGS: LangInfo[] = [
  { id: "es", name: "Español", short: "ES", flags: ["es"], locale: "es-ES" },
  { id: "en", name: "English", short: "EN", flags: ["us", "gb"], locale: "en-GB" },
  { id: "fr", name: "Français", short: "FR", flags: ["fr"], locale: "fr-FR" },
];

export const LANG_IDS: Lang[] = LANGS.map((l) => l.id);
