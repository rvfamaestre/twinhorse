// Utilidades comunes de los vídeos. Cada escena es una función pura del tiempo: render(t) pinta el
// fotograma del segundo t sin depender del anterior, así que se puede grabar en paralelo y a saltos.

export const W = 1920;
export const H = 1080;

// Colores del dashboard (frontend/src/scene/palette.ts y styles.css)
export const C = {
  bg: "#ffffff",
  ink: "#0d0d0d",
  ink2: "#3d3d3d",
  muted: "#6b6b6b",
  faint: "#a3a3a3",
  line: "#e6e6e6",
  line2: "#cfcfcf",
  soft: "#f4f4f4",
  cell: "#dcdfe3",
  work: "#30a46c",
  own: "#e5484d",
  starved: "#f0a530",
  blocked: "#3e8bf0",
  nodata: "#8b8d98",
};

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, k) => a + (b - a) * k;
/** Avance 0..1 de un tramo que empieza en t0 y dura dur. */
export const prog = (t, t0, dur) => clamp((t - t0) / dur);

export const ease = {
  linear: (x) => x,
  outCubic: (x) => 1 - Math.pow(1 - x, 3),
  inOutCubic: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  outExpo: (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x)),
  inOutExpo: (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x < 0.5 ? Math.pow(2, 20 * x - 10) / 2 : (2 - Math.pow(2, -20 * x + 10)) / 2),
  outBack: (x) => 1 + 2.2 * Math.pow(x - 1, 3) + 1.2 * Math.pow(x - 1, 2),
};

/** Tramo con curva: 0 antes de t0, 1 al acabar. */
export const tween = (t, t0, dur, fn = ease.outExpo) => fn(prog(t, t0, dur));

const NS = "http://www.w3.org/2000/svg";

/** Crea un elemento SVG. `text` va como contenido; el resto como atributos. */
export function el(tag, attrs = {}, parent = null) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") e.textContent = v;
    else e.setAttribute(k, v);
  }
  if (parent) parent.appendChild(e);
  return e;
}

export function attrs(e, a) {
  for (const [k, v] of Object.entries(a)) e.setAttribute(k, v);
}

/** Entrada típica de las presentaciones de producto: sube un poco, se enfoca y aparece. */
export function reveal(e, t, t0, { dur = 0.9, dy = 18, blur = 8, out = null, outDur = 0.5 } = {}) {
  let p = tween(t, t0, dur);
  if (out != null) p *= 1 - tween(t, out, outDur, ease.inOutCubic);
  e.style.opacity = p.toFixed(4);
  e.style.filter = p < 0.999 && blur ? `blur(${((1 - p) * blur).toFixed(2)}px)` : "none";
  e.setAttribute("transform", `translate(0 ${(dy * (1 - p)).toFixed(2)})`);
  return p;
}

/** Números en español: 1.820, 2,6. */
export function num(v, d = 0) {
  const [i, f] = Math.abs(v).toFixed(d).split(".");
  const s = (v < 0 ? "-" : "") + i.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return f ? `${s},${f}` : s;
}

/** Mezcla dos colores #rrggbb. */
export function mix(a, b, k) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return "#" + pa.map((x, i) => Math.round(lerp(x, pb[i], clamp(k))).toString(16).padStart(2, "0")).join("");
}

/** Cámara muy lenta sobre todo el lienzo: da vida sin que se note. */
export function drift(g, t, dur, amount = 0.025) {
  const s = 1 + amount * ease.inOutCubic(clamp(t / dur));
  g.setAttribute("transform", `translate(${W / 2} ${H / 2}) scale(${s.toFixed(5)}) translate(${-W / 2} ${-H / 2})`);
}

/** Carga Inter antes de medir textos. */
export async function fonts() {
  await Promise.all([400, 500, 600, 700].map((w) => document.fonts.load(`${w} 20px Inter`)));
}

export async function loadData() {
  const r = await fetch("data.json");
  return r.json();
}

/**
 * Publica la escena. Abierta a mano se reproduce en bucle; con ?t=5 se queda en ese segundo.
 * El grabador (render.mjs) abre la página con ?render y llama a window.render(t) fotograma a fotograma.
 */
export async function mount(render, duration) {
  await document.fonts.ready;
  window.DURATION = duration;
  window.render = render;
  const q = new URLSearchParams(location.search);
  if (q.has("render")) {
    render(0);
  } else if (q.has("t")) {
    render(Number(q.get("t")));
  } else {
    const t0 = performance.now();
    const loop = (now) => {
      render(((now - t0) / 1000) % (duration + 1));
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }
  window.ready = true;
}
