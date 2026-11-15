// Graba el gemelo 3D real (frontend en http://localhost:5173 y API en :8000) con un cursor que hace la demo.
//
//   node capture_gemelo.mjs                       figures/video/04_gemelo.mp4
//   node capture_gemelo.mjs --stills 3,9,20       solo PNG sueltos en esos segundos (para revisar)
//
// El reloj de la página es falso (page.clock) y las animaciones CSS se paran y se avanzan a mano, así que
// cada fotograma es exacto aunque hacer la captura tarde más que 1/60 s. Mismo guion, mismo vídeo.

import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, "..", "..", "figures", "video");
const URL_APP = process.env.LOSSIA_URL || "http://localhost:5173/";
const args = process.argv.slice(2);
const opt = (name, def) => (args.includes(`--${name}`) ? args[args.indexOf(`--${name}`) + 1] : def);
const stills = opt("stills", null)?.split(",").map(Number) ?? null;
const FPS = Number(opt("fps", stills ? 10 : 60));
const D = 43;
const DT = 1000 / FPS;

// Vista de 1536×864 a escala 1,25: sale a 1920×1080 con la interfaz un 25 % más grande, legible en un proyector
const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist", "--force-color-profile=srgb"] });
const page = await browser.newPage({ viewport: { width: 1536, height: 864 }, deviceScaleFactor: 1.25 });
page.on("pageerror", (e) => console.error("página:", e.message));
await page.addInitScript(() => {
  localStorage.setItem("lossia.forma", "snake");
  localStorage.setItem("lossia.tema", "light");
  localStorage.setItem("lossia.idioma", "es");
  // Cursor dibujado en la página (las capturas no incluyen el del sistema)
  window.__cursor = (x, y, opacity, ripple) => {
    let c = document.getElementById("__cur");
    if (!c) {
      c = document.createElement("div");
      c.id = "__cur";
      c.style.cssText = "position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:0;height:0";
      c.innerHTML =
        '<div id="__rip" style="position:absolute;left:-22px;top:-22px;width:44px;height:44px;border-radius:50%;background:rgba(13,13,13,.18)"></div>' +
        '<svg width="28" height="28" viewBox="0 0 28 28" style="position:absolute;left:-4px;top:-3px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))">' +
        '<path d="M4 3 L4 23 L9.4 17.9 L13 26 L16.6 24.4 L13.1 16.6 L20.6 16.6 Z" fill="#0d0d0d" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg>';
      document.documentElement.appendChild(c);
    }
    c.style.transform = `translate(${x}px, ${y}px)`;
    c.style.opacity = opacity;
    const r = document.getElementById("__rip");
    r.style.opacity = ripple > 0 && ripple < 1 ? (0.9 * (1 - ripple)).toFixed(3) : 0;
    r.style.transform = `scale(${(0.3 + 0.9 * ripple).toFixed(3)})`;
  };
});
// install() deja correr el tiempo real mientras carga la línea; luego pauseAt() lo para y desde ahí
// solo avanza con runFor(), un fotograma cada vez
await page.clock.install({ time: new Date("2026-11-14T10:29:00") });
const cdp = await page.context().newCDPSession(page);
await page.goto(URL_APP);
await page.waitForSelector(".tramos", { timeout: 60000 });
await page.waitForTimeout(2000);
await page.clock.pauseAt(new Date("2026-11-14T10:29:55"));

// Animaciones CSS al ritmo del reloj falso: la línea de tiempo del documento parada y avanzada a mano
await cdp.send("Animation.enable");
await cdp.send("Animation.setPlaybackRate", { playbackRate: 0 });
async function tick(ms) {
  await page.clock.runFor(ms);
  await page.evaluate((ms) => {
    for (const a of document.getAnimations()) a.currentTime = (a.currentTime ?? 0) + ms;
  }, ms);
}
const run = async (s) => {
  for (let t = 0; t < s * 1000; t += DT) await tick(DT);
};

// Arranque: vista general asentada
await run(1);
await page.keyboard.press("v");
await run(3);

// --- Guion ---------------------------------------------------------------------------------
const rect = (sel, text) =>
  page.evaluate(([sel, text]) => {
    const el = [...document.querySelectorAll(sel)].find((e) => !text || e.textContent.includes(text));
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, [sel, text]);
const center = { x: 768, y: 470 };
const cursor = { x: 1180, y: 700, opacity: 0, ripple: -1 };
const moves = [];
const actions = [];
const moveTo = (t0, dur, target) => moves.push({ t0, dur, target });
const at = (t, fn) => actions.push({ t, fn });
const click = (t, target, travel = 1.0) => {
  moveTo(t - travel - 0.12, travel, target);
  at(t, async () => {
    cursor.rippleAt = tNow;
    await page.mouse.down();
    await page.mouse.up();
  });
};
const sel = (s, text) => () => rect(s, text);
let tNow = 0;

const S = {
  zoom: [0.2, 4.4], // acercamiento lento a la planta
  est: 5.8, estClose: 9.2, // motores del día que estima TimesFM y los factores que pesan
  brakes: 10.6, row: 12.2, // «Frenan» → ST-0260: vuela a la máquina y abre su ficha
  close: 18.2,
  history: 20.0, speed: 21.2, // histórico a ×600
  help: 28.6, starved: 30.0, // la leyenda que enseña: solo las máquinas sin piezas
  helpClose: 34.2,
  dark: 35.6, overview: 37.2,
};
at(4.4, async () => (cursor.show = true));
click(S.est, sel(".nav-motors.est"), 1.3);
moveTo(S.est + 0.9, 1.4, async () => {
  const r = await rect(".est-pop .est-factors");
  return r ? { x: r.x + 60, y: r.y } : null;
});
at(S.estClose, () => page.keyboard.press("Escape"));
click(S.brakes, sel(".pop-anchor .pill-btn", "Frenan"), 1.3);
click(S.row, sel(".brakes-table button", "ST-0260"), 0.9);
moveTo(S.row + 1.6, 1.4, async () => ({ x: 1290, y: 520 }));
at(S.close, () => page.keyboard.press("Escape"));
click(S.history, sel(".time .seg button", "Histórico"), 1.2);
click(S.speed, sel("select.speed"), 0.8);
at(S.speed + 0.25, () =>
  page.evaluate(() => {
    const s = document.querySelector("select.speed");
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(s, "600");
    s.dispatchEvent(new Event("change", { bubbles: true }));
  }),
);
moveTo(S.speed + 1.0, 1.2, async () => ({ x: 1010, y: 640 }));
click(S.help, sel('button[aria-label="Ayuda y leyenda"]'), 1.2);
click(S.starved, sel(".help-legend button", "Sin piezas"), 0.8);
moveTo(S.starved + 0.8, 1.2, async () => ({ x: 1120, y: 600 }));
at(S.helpClose, () => page.keyboard.press("Escape"));
click(S.dark, sel('button[aria-label="Modo oscuro"]'), 1.1);
at(S.overview, () => page.keyboard.press("v"));
moveTo(S.overview + 0.3, 1.4, async () => ({ x: 1600, y: 980 }));
at(S.overview + 1.6, async () => (cursor.hide = true));

const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const clamp = (x) => Math.min(1, Math.max(0, x));

// --- Grabación -----------------------------------------------------------------------------
const frames = Math.round(D * FPS) + 1;
let ff = null;
if (!stills) {
  fs.mkdirSync(OUT, { recursive: true });
  ff = spawn("ffmpeg", [
    "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
    "-movflags", "+faststart", path.join(OUT, "04_gemelo.mp4"),
  ], { stdio: ["pipe", "ignore", "pipe"] });
  ff.stderr.on("data", () => {});
}
const started = Date.now();
let last = null;
for (let f = 0; f < frames; f++) {
  tNow = f / FPS;
  for (const a of actions.filter((a) => !a.done && a.t <= tNow)) {
    a.done = true;
    await a.fn();
  }
  for (const m of moves.filter((m) => !m.from && m.t0 <= tNow)) {
    m.from = { x: cursor.x, y: cursor.y };
    m.to = (await m.target()) ?? m.from;
  }
  const m = moves.filter((m) => m.from && m.t0 <= tNow).at(-1);
  if (m) {
    const k = ease(clamp((tNow - m.t0) / m.dur));
    const dx = m.to.x - m.from.x, dy = m.to.y - m.from.y;
    const arc = Math.sin(Math.PI * k) * 0.08;
    cursor.x = m.from.x + dx * k - dy * arc;
    cursor.y = m.from.y + dy * k + dx * arc;
  }
  cursor.opacity = cursor.hide ? Math.max(0, cursor.opacity - 3 / FPS) : cursor.show ? Math.min(1, cursor.opacity + 3 / FPS) : 0;
  const ripple = cursor.rippleAt != null ? clamp((tNow - cursor.rippleAt) / 0.45) : -1;
  if (cursor.opacity > 0 && (!last || last.x !== cursor.x || last.y !== cursor.y)) await page.mouse.move(cursor.x, cursor.y);
  last = { x: cursor.x, y: cursor.y };
  await page.evaluate(([x, y, o, r]) => window.__cursor(x, y, o, r), [cursor.x, cursor.y, cursor.opacity, ripple]);
  // Acercamiento lento con la rueda, hacia el centro de la planta
  if (tNow >= S.zoom[0] && tNow < S.zoom[1]) {
    if (cursor.opacity === 0) await page.mouse.move(center.x, center.y);
    await page.mouse.wheel(0, -42 / FPS);
  }

  if (!stills) ff.stdin.write(await page.screenshot({ type: "png" }));
  else if (stills.some((s) => Math.abs(s - tNow) < 0.5 / FPS)) {
    const file = path.join(os.tmpdir(), "lossia-video", `04_gemelo_t${tNow.toFixed(1)}.png`);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await page.screenshot({ path: file, type: "png" });
    console.log(file);
  }
  await tick(DT);
  if (f % 120 === 0) process.stdout.write(`\r04_gemelo: ${f}/${frames}`);
}

if (ff) {
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
  await page.screenshot({ path: path.join(OUT, "04_gemelo.png"), type: "png" });
  const mb = (fs.statSync(path.join(OUT, "04_gemelo.mp4")).size / 1e6).toFixed(1);
  console.log(`\r04_gemelo: ${frames} fotogramas, ${D} s, ${mb} MB, ${((Date.now() - started) / 1000).toFixed(0)} s de grabación`);
}
await browser.close();
