import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { type Deciles, type ForecastOptions, type ForecastResult, fetchOptions, runForecast } from "../data/forecast";
import { dayLong, dayShort, num } from "../domain/format";
import { useT } from "../i18n";
import { useUI } from "../state/ui";
import { useDash } from "./ctx";

/**
 * Predicción al momento: se elige una serie, cuántos días ve el modelo, cuántos predice y desde qué día.
 * Si el horizonte cae en días con datos, se compara con lo que pasó. La banda va en degradado
 * (intervalos centrales del 80, 60, 40 y 20 %) y nunca se pinta una línea central.
 */
const FAN: [keyof Deciles, keyof Deciles, number][] = [["p10", "p90", 80], ["p20", "p80", 60], ["p30", "p70", 40], ["p40", "p60", 20]];
const FAN_ALPHA = 0.1;
const tone = (k: number) => 1 - (1 - FAN_ALPHA) ** (k + 1);
const LINE_ID = "LINEA";

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(720);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => setW(Math.max(320, Math.round(el.getBoundingClientRect().width)));
    read();
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** Marcas «redondas» para el eje vertical. */
function ticks(lo: number, hi: number, n = 4): number[] {
  const span = hi - lo || 1;
  const raw = span / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Number(v.toFixed(6)));
  return out;
}

function Chart({ r, unit }: { r: ForecastResult; unit: string }) {
  const T = useT();
  const [box, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 380;
  const pad = { l: 52, r: 16, t: 28, b: 34 };
  const nc = r.context.dates.length;
  const nf = r.forecast.dates.length;
  const n = nc + nf;
  const dates = [...r.context.dates, ...r.forecast.dates];
  const real = [...r.context.values, ...r.actual];

  const all = [...real, ...r.forecast.p10, ...r.forecast.p90].filter((v): v is number => v != null);
  const hours = unit === "h";
  let lo = hours ? 0 : Math.min(...all);
  let hi = Math.max(...all);
  if (!hours) {
    const m = (hi - lo) * 0.12 || 1;
    lo -= m;
    hi += m;
  } else hi = hi * 1.08 || 1;
  const ys = ticks(lo, hi);
  const tickStep = ys.length > 1 ? ys[1] - ys[0] : 1;
  const tickDigits = tickStep >= 1 ? 0 : Number.isInteger(Math.round(tickStep * 1000) / 100) ? 1 : 2;
  lo = Math.min(lo, ys[0]);
  hi = Math.max(hi, ys[ys.length - 1]);

  const step = (width - pad.l - pad.r) / Math.max(1, n - 1);
  const x = (i: number) => pad.l + i * step;
  const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo)) * (height - pad.t - pad.b);
  const split = x(nc - 1) + step / 2;

  // Banda: un polígono por intervalo que nace en el último dato real (ahí no hay incertidumbre).
  const anchor = r.context.values[nc - 1];
  const band = (a: keyof Deciles, b: keyof Deciles) => {
    const top = r.forecast[b].map((v, k) => [x(nc + k), y(v ?? 0)]);
    const bot = r.forecast[a].map((v, k) => [x(nc + k), y(v ?? 0)]).reverse();
    const start = anchor != null ? [[x(nc - 1), y(anchor)]] : [];
    return `M${[...start, ...top, ...bot].map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join("L")}Z`;
  };

  // La serie real, cortada donde no hay dato.
  const segments: string[] = [];
  let cur = "";
  real.forEach((v, i) => {
    if (v == null) {
      if (cur) segments.push(cur);
      cur = "";
    } else cur += `${cur ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  if (cur) segments.push(cur);

  const every = Math.max(1, Math.ceil(n / Math.max(4, Math.floor((width - pad.l) / 64))));
  const outside = (k: number) => {
    const v = r.actual[k];
    return v != null && r.forecast.p10[k] != null && r.forecast.p90[k] != null && (v < r.forecast.p10[k]! || v > r.forecast.p90[k]!);
  };
  const fmt = (v: number | null | undefined) => (v == null ? "—" : `${num(v, hours ? 2 : 0)}${hours ? " h" : ""}`);

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.round((e.clientX - rect.left - pad.l) / step);
    setHover(i >= 0 && i < n ? i : null);
  };
  const h = hover;
  const fk = h != null && h >= nc ? h - nc : null;

  return (
    <div className="fc-chart" ref={box}>
      <svg width={width} height={height} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img"
        aria-label={T.fc.chartAria(nf)}>
        {ys.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={width - pad.r} y1={y(v)} y2={y(v)} className="grid" />
            <text x={pad.l - 10} y={y(v)} className="tick" textAnchor="end" dominantBaseline="middle">{num(v, tickDigits)}</text>
          </g>
        ))}
        {dates.map((d, i) => (i % every === 0 || i === nc ? (
          <text key={d} x={x(i)} y={height - 10} className="tick" textAnchor="middle">{dayShort(d)}</text>
        ) : null))}
        <line x1={split} x2={split} y1={pad.t - 14} y2={height - pad.b} className="split" />
        <text x={split + 8} y={pad.t - 10} className="tick">{T.fc.forecast}</text>
        <text x={split - 8} y={pad.t - 10} className="tick" textAnchor="end">{T.fc.history}</text>
        {FAN.map(([a, b], k) => <path key={a} d={band(a, b)} className="fan" fillOpacity={FAN_ALPHA} data-level={k} />)}
        {segments.map((d, k) => <path key={k} d={d} className="real" />)}
        {real.map((v, i) => (v == null ? null : <circle key={i} cx={x(i)} cy={y(v)} r={i >= nc ? 3.6 : 2.6} className="pt" />))}
        {r.actual.map((_, k) => (outside(k) ? <circle key={`o${k}`} cx={x(nc + k)} cy={y(r.actual[k]!)} r={8} className="ring" /> : null))}
        {h != null ? <line x1={x(h)} x2={x(h)} y1={pad.t} y2={height - pad.b} className="guide" /> : null}
      </svg>
      {h != null ? (
        <div className="fc-tip" style={{ left: Math.min(width - 190, Math.max(0, x(h) + 12)), top: 36 }}>
          <b>{dayLong(dates[h])}</b>
          <span>{T.fc.real} <em>{fmt(real[h])}</em></span>
          {fk != null ? (
            <>
              <span>80 % <em>{fmt(r.forecast.p10[fk])} – {fmt(r.forecast.p90[fk])}</em></span>
              <span>20 % <em>{fmt(r.forecast.p40[fk])} – {fmt(r.forecast.p60[fk])}</em></span>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: { id: T; label: string; disabled?: boolean }[]; onChange(v: T): void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} aria-pressed={value === o.id} disabled={o.disabled} onClick={() => onChange(o.id)}>{o.label}</button>
      ))}
    </div>
  );
}

export function ForecastView() {
  const T = useT();
  const { model } = useDash();
  const wanted = useUI((s) => s.forecastSeries);
  const [opts, setOpts] = useState<ForecastOptions | null>(null);
  const [optsError, setOptsError] = useState<string | null>(null);
  const [series, setSeries] = useState<string>("");
  const [metric, setMetric] = useState("tap_h");
  const [origin, setOrigin] = useState<string>("");
  const [context, setContext] = useState(10);
  const [horizon, setHorizon] = useState(5);
  const [modelId, setModelId] = useState("timesfm");
  const [result, setResult] = useState<ForecastResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sent = useRef(""); // la petición de la predicción que se ve

  // Opciones: se vuelven a pedir mientras TimesFM se carga en la API.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const o = await fetchOptions();
        if (!alive) return;
        setOpts(o);
        setOptsError(null);
        if (!o.models.find((m) => m.id === "timesfm")?.ready) timer = setTimeout(load, 2000);
      } catch (e) {
        if (!alive) return;
        setOptsError((e as Error).message);
        timer = setTimeout(load, 4000);
      }
    };
    load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  // Serie inicial: la que se pidió desde una ficha, o la que más frena la línea.
  useEffect(() => {
    if (!opts) return;
    const ids = new Set(opts.series.map((s) => s.id));
    const pick = wanted && ids.has(wanted) ? wanted : !series ? model.state.ranking.find((op) => ids.has(op)) ?? LINE_ID : null;
    if (pick) {
      setSeries(pick);
      setMetric(pick === LINE_ID ? "npr" : "tap_h");
    }
    if (!origin) setOrigin(opts.dates[opts.dates.length - 1]);
  }, [opts, wanted]); // eslint-disable-line react-hooks/exhaustive-deps

  const meta = opts?.series.find((s) => s.id === series);
  const metrics = opts?.metrics.filter((m) => meta?.metrics.includes(m.id)) ?? [];
  const maxContext = opts && origin ? opts.dates.indexOf(origin) + 1 : 16;
  const timesfm = opts?.models.find((m) => m.id === "timesfm");
  const unit = opts?.metrics.find((m) => m.id === metric)?.unit ?? "h";
  const lastDay = opts?.dates[opts.dates.length - 1];

  useEffect(() => {
    if (context > maxContext) setContext(maxContext);
  }, [maxContext, context]);
  useEffect(() => {
    if (meta && !meta.metrics.includes(metric)) setMetric(meta.metrics[0]);
  }, [meta, metric]);

  const request = useMemo(() => ({ series, metric, context: Math.min(context, maxContext), horizon, origin, model: modelId }),
    [series, metric, context, maxContext, horizon, origin, modelId]);

  const predict = async () => {
    if (!series || !origin) return;
    setBusy(true);
    setError(null);
    try {
      const r = await runForecast(request);
      sent.current = JSON.stringify(request);
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // La primera predicción sale sola (con la media si TimesFM aún se carga); las demás, al pulsar Predecir.
  useEffect(() => {
    if (!opts || !series || !origin || result || busy || error) return;
    if (modelId === "timesfm" && !timesfm?.ready) setModelId("media");
    else void predict();
  }, [opts, series, origin, modelId]); // eslint-disable-line react-hooks/exhaustive-deps
  const stale = result != null && JSON.stringify(request) !== sent.current;

  if (!opts) {
    return (
      <section className="fc">
        <div className="fc-empty">
          <h2>{optsError ? T.fc.needsApi : T.fc.connecting}</h2>
          {optsError ? <p>{T.fc.startA} <code>python -m backend.api</code> {T.fc.startB}</p> : null}
        </div>
      </section>
    );
  }

  // Las etiquetas de la API vienen en español: se traducen por su identificador.
  const metricName = (id: string) => T.fc.metrics[id] ?? opts.metrics.find((m) => m.id === id)?.label ?? id;
  const modelName = (id: string, fallback: string) => T.fc.models[id] ?? fallback;
  const seriesName = (id: string, fallback: string) => (id === LINE_ID ? T.fc.line : fallback);
  const metricLabel = metricName(metric);
  const unitLabel = unit === "h" ? "h" : T.fc.metrics.npr.toLowerCase();
  const future = origin === lastDay;
  const shown = result;

  return (
    <section className="fc">
      <aside className="fc-side" aria-label={T.fc.params}>
        <label className="field">
          <span>{T.fc.series}</span>
          <select value={series} onChange={(e) => setSeries(e.target.value)}>
            {opts.series.map((s) => <option key={s.id} value={s.id}>{seriesName(s.id, s.label)}</option>)}
          </select>
        </label>
        {metrics.length > 1 ? (
          <div className="field">
            <span>{T.fc.metric}</span>
            <Seg label={T.fc.metric} value={metric} onChange={setMetric} options={metrics.map((m) => ({ id: m.id, label: metricName(m.id) }))} />
          </div>
        ) : null}
        <label className="field">
          <span>{T.fc.from}</span>
          <select value={origin} onChange={(e) => setOrigin(e.target.value)}>
            {[...opts.dates].reverse().map((d) => (
              <option key={d} value={d}>{d === lastDay ? `${dayLong(d)} · ${T.fc.lastDay}` : dayLong(d)}</option>
            ))}
          </select>
          <small>{future ? T.fc.future : T.fc.past}</small>
        </label>
        <label className="field">
          <span>{T.fc.context} <b>{T.fc.days(Math.min(context, maxContext))}</b></span>
          <input type="range" min={opts.limits.min_context} max={maxContext} value={Math.min(context, maxContext)} onChange={(e) => setContext(Number(e.target.value))} />
          <small>{T.fc.contextHint}{origin ? T.fc.contextMax(dayShort(origin), maxContext) : ""}</small>
        </label>
        <label className="field">
          <span>{T.fc.horizon} <b>{T.fc.days(horizon)}</b></span>
          <input type="range" min={1} max={opts.limits.max_horizon} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
        </label>
        <div className="field">
          <span>{T.fc.model}</span>
          <Seg label={T.fc.model} value={modelId} onChange={setModelId}
            options={opts.models.map((m) => ({ id: m.id, label: m.id === "timesfm" && !m.ready ? T.fc.loading : modelName(m.id, m.label), disabled: !m.ready }))} />
        </div>
        <button className="primary" onClick={predict} disabled={busy || !series}>{busy ? T.fc.busy : T.fc.predict}</button>
        {error ? <p className="fc-error" role="alert">{error}</p> : null}
      </aside>

      <div className="fc-main">
        <header>
          <h2>{series === LINE_ID ? T.fc.line : series} · {metricLabel.toLowerCase()}</h2>
          {shown ? (
            <p>
              {T.fc.summary(shown.context.dates.length, shown.forecast.dates.length, modelName(shown.model, shown.model_label), num(shown.elapsed_ms, 0))}
              {stale ? <span className="stale">{T.fc.stale}</span> : null}
            </p>
          ) : <p>{T.fc.choose}</p>}
        </header>
        {shown ? (
          <div className={stale ? "fc-result stale" : "fc-result"}>
            <Chart r={shown} unit={unit} />
            <ul className="fc-key">
              {FAN.map(([, , p], k) => <li key={p}><i className="fan" style={{ opacity: tone(k) }} />{p} %</li>)}
              <li className="note">{T.fc.prob}</li>
              <li><i className="line" />{T.fc.realKey}</li>
              {shown.known ? <li><i className="ring" />{T.fc.outside}</li> : null}
            </ul>
            {shown.known ? (
              <dl className="fc-stats">
                <div><dt>{T.fc.inside}</dt><dd>{T.fc.insideOf(shown.inside_80, shown.known)}</dd></div>
                <div><dt>{T.fc.predicted}</dt><dd>{dayShort(shown.forecast.dates[0])} – {dayShort(shown.forecast.dates[shown.forecast.dates.length - 1])}</dd></div>
              </dl>
            ) : (
              <dl className="fc-stats">
                <div><dt>{T.fc.predicted}</dt><dd>{dayShort(shown.forecast.dates[0])} – {dayShort(shown.forecast.dates[shown.forecast.dates.length - 1])}</dd></div>
                <div><dt>{T.fc.firstBand}</dt><dd>{num(shown.forecast.p10[0], unit === "h" ? 2 : 0)} – {num(shown.forecast.p90[0], unit === "h" ? 2 : 0)} {unitLabel}</dd></div>
              </dl>
            )}
          </div>
        ) : null}
      </div>
    </section>
  );
}
