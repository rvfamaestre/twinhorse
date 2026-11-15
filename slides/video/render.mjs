// Graba las escenas de scenes/*.html en MP4 (1920×1080, H.264) fotograma a fotograma.
//
//   node render.mjs                     todas las escenas
//   node render.mjs 01_paradoja         solo esa
//   node render.mjs 01_paradoja --stills 2,5,9   PNG sueltos en esos segundos (para revisar)
//
// Salida: figures/video/<escena>.mp4 y <escena>.png (último fotograma, por si el vídeo no carga).
// Usa el Chrome instalado (playwright-core no descarga navegadores) y ffmpeg del PATH.

import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCENES = path.join(HERE, "scenes");
const OUT = path.resolve(HERE, "..", "..", "figures", "video");

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : def;
};
const FPS = Number(opt("fps", 60));
const WORKERS = Number(opt("workers", 4));
const stills = opt("stills", null);
const names = args.filter((a, i) => !a.startsWith("--") && !(i > 0 && args[i - 1].startsWith("--")));
const all = fs.readdirSync(SCENES).filter((f) => /^\d\d_.*\.html$/.test(f)).map((f) => f.replace(/\.html$/, ""));
const todo = names.length ? names : all;

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".woff2": "font/woff2" };
const server = http.createServer((req, res) => {
  const file = path.join(SCENES, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!file.startsWith(SCENES) || !fs.existsSync(file)) return res.writeHead(404).end();
  res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--force-color-profile=srgb", "--font-render-hinting=none"] });

async function open(name) {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on("pageerror", (e) => console.error(`[${name}]`, e.message));
  await page.goto(`${base}/${name}.html?render`);
  await page.waitForFunction(() => window.ready === true, null, { timeout: 30000 });
  return page;
}

const shot = async (page, t, file) => {
  await page.evaluate((t) => window.render(t), t);
  await page.screenshot({ path: file, type: "png" });
};

function ffmpeg(argv) {
  return new Promise((resolve, reject) => {
    const p = spawn("ffmpeg", argv, { stdio: ["ignore", "ignore", "pipe"] });
    let err = "";
    p.stderr.on("data", (d) => (err += d));
    p.on("close", (code) => (code === 0 ? resolve() : reject(new Error(err.slice(-2000)))));
  });
}

fs.mkdirSync(OUT, { recursive: true });
for (const name of todo) {
  const started = Date.now();
  if (stills) {
    const page = await open(name);
    for (const s of stills.split(",").map(Number)) {
      const file = path.join(os.tmpdir(), "lossia-video", `${name}_t${s}.png`);
      fs.mkdirSync(path.dirname(file), { recursive: true });
      await shot(page, s, file);
      console.log(file);
    }
    await page.close();
    continue;
  }
  const tmp = path.join(os.tmpdir(), "lossia-video", name);
  fs.rmSync(tmp, { recursive: true, force: true });
  fs.mkdirSync(tmp, { recursive: true });
  const pages = await Promise.all(Array.from({ length: WORKERS }, () => open(name)));
  const duration = await pages[0].evaluate(() => window.DURATION);
  const frames = Math.round(duration * FPS) + 1;
  let done = 0;
  await Promise.all(
    pages.map(async (page, w) => {
      for (let i = w; i < frames; i += WORKERS) {
        await shot(page, i / FPS, path.join(tmp, `f${String(i).padStart(5, "0")}.png`));
        if (++done % 120 === 0) process.stdout.write(`\r${name}: ${done}/${frames}`);
      }
      await page.close();
    }),
  );
  const mp4 = path.join(OUT, `${name}.mp4`);
  await ffmpeg([
    "-y", "-framerate", String(FPS), "-i", path.join(tmp, "f%05d.png"),
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-tune", "animation",
    "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
    "-movflags", "+faststart", mp4,
  ]);
  fs.copyFileSync(path.join(tmp, `f${String(frames - 1).padStart(5, "0")}.png`), path.join(OUT, `${name}.png`));
  fs.rmSync(tmp, { recursive: true, force: true });
  const mb = (fs.statSync(mp4).size / 1e6).toFixed(1);
  console.log(`\r${name}: ${frames} fotogramas, ${duration} s, ${mb} MB, ${((Date.now() - started) / 1000).toFixed(0)} s de grabación`);
}

await browser.close();
server.close();
