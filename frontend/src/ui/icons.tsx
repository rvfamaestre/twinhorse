/** Iconos mínimos en SVG, sin librerías ni fuentes de iconos. */
const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2.2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;

export const IconLeft = () => <svg {...base}><path d="M15 5l-7 7 7 7" /></svg>;
export const IconRight = () => <svg {...base}><path d="M9 5l7 7-7 7" /></svg>;
export const IconClose = () => <svg {...base}><path d="M6 6l12 12M18 6L6 18" /></svg>;
export const IconPlay = () => <svg {...base} fill="currentColor" stroke="none"><path d="M8 5.5v13l11-6.5z" /></svg>;
export const IconPause = () => <svg {...base} fill="currentColor" stroke="none"><path d="M7 5h4v14H7zM13 5h4v14h-4z" /></svg>;
export const IconBell = () => <svg {...base}><path d="M6 16V11a6 6 0 1112 0v5l1.5 2h-15zM10 20.5h4" /></svg>;
export const IconMap = () => <svg {...base}><path d="M3 7h18v10H3zM8 7v10M16 7v10" /></svg>;
export const IconGo = () => <svg {...base} width={14} height={14}><path d="M5 12h13M13 6l6 6-6 6" /></svg>;
export const IconHelp = () => <svg {...base}><circle cx="12" cy="12" r="9" /><path d="M9.6 9.3a2.5 2.5 0 014.8.9c0 1.7-2.4 2.2-2.4 3.8M12 17.3v.2" /></svg>;
export const IconMoon = () => <svg {...base}><path d="M19.5 14.5A7.5 7.5 0 019.5 4.5a7.5 7.5 0 1010 10z" /></svg>;
export const IconSun = () => <svg {...base}><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4" /></svg>;
export const IconBrake = () => <svg {...base}><path d="M4 6h16M4 12h16M4 18h10" /></svg>;
export const IconCalendar = () => <svg {...base}><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></svg>;
export const IconDown = () => <svg {...base} width={14} height={14}><path d="M6 9l6 6 6-6" /></svg>;
