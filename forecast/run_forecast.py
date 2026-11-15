"""Prediccion por linea con TimesFM 3.0. Desde la raiz del repo:

    python forecast/run_forecast.py backtest                      # todas las lineas
    python forecast/run_forecast.py backtest --line VLL_MONTAJE_L5
    python forecast/run_forecast.py backtest --sin-timesfm        # solo referencias, en segundos
    python forecast/run_forecast.py predict --horizon 5 --off 2026-10-30

backtest escribe en forecast/output/<linea>/ el informe BACKTEST.md y las tablas, y su figura en
figures/forecast/<linea>/.
predict usa, para cada metrica, la variante que gano el backtest y escribe forecasts.csv y
forecast.json (el campo `forecast` de cada estacion para el JSON del dashboard).
"""

import argparse
import os
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.pipeline import ingest  # noqa: E402
from backend.pipeline.settings import LINES_DIR  # noqa: E402
from eda import plots as style  # noqa: E402  (misma paleta y tipografia que el EDA)
from eda.plots import fmt  # noqa: E402
from forecast import backtest, series  # noqa: E402

OUT = ROOT / "forecast" / "output"
FIGURES = ROOT / "figures" / "forecast"
METRIC_LABEL = {"tap_h": "TAP (h)", "des_h": "DES (h)", "sat_h": "SAT (h)", "npr": "piezas al día"}
MODEL_LABEL = {"ultimo_valor": "último valor", "media": "media", "timesfm": "TimesFM",
               "timesfm_calendario": "TimesFM + calendario", "timesfm_vecinas": "TimesFM + calendario + vecinas"}


def md_table(df: pd.DataFrame) -> str:
    rows = ["| " + " | ".join(df.columns) + " |", "| " + " | ".join("---" for _ in df.columns) + " |"]
    rows += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(rows)


def pct(x: float, signed: bool = False) -> str:
    if pd.isna(x):
        return ""
    v = round(100 * x)
    return f"{'+' if signed and v > 0 else ''}{fmt(v, 0)} %"


def overall_timesfm(scores: pd.DataFrame, order: list[str]) -> str | None:
    """La variante de TimesFM que mejor sale de media frente a la referencia (semana)."""
    s = scores[(scores["escenario"] == "semana") & scores["modelo"].str.startswith("timesfm")]
    if s.empty:
        return None
    mean = s.groupby("modelo")["mejora"].mean()
    return max(mean.index, key=lambda m: (round(mean[m], 3), -order.index(m)))


# ---------------------------------------------------------------- figura

def band_figure(panel: series.Panel, preds: pd.DataFrame, tfm: str, path: Path) -> Path:
    """Contexto, dias reales de la semana de prueba y la banda de una variante de TimesFM en degradado."""
    import matplotlib.pyplot as plt

    tap_total = panel.values["tap_h"].sum().sort_values(ascending=False)
    cases = [("npr", series.LINE_ID)] + [("tap_h", op) for op in tap_total.index[:2]]
    week = preds[preds["escenario"] == "semana"]
    fig, axes = plt.subplots(1, len(cases), figsize=(4.2 * len(cases), 3.4), gridspec_kw={"wspace": 0.35})
    for ax, (metric, sid) in zip(np.atleast_1d(axes), cases):
        hist = panel.values[metric][sid]
        p = week[(week["metrica"] == metric) & (week["serie"] == sid)]
        m = p[p["modelo"] == tfm].sort_values("fecha")
        x = np.arange(len(hist))
        pos = {d: i for i, d in enumerate(hist.index)}
        xt = [pos[d] for d in m["fecha"]]
        style.fan(ax, xt, m, style.BAND_C)
        ax.plot(x, hist.to_numpy(), color=style.INK, linewidth=1.2, marker="o", markersize=3, label="real")
        ax.axvline(min(xt) - 0.5, color=style.AXIS, linewidth=1)
        ax.set_xticks(x[::3], [d.strftime("%d/%m") for d in hist.index[::3]])
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        if metric != series.LINE_METRIC:  # horas: el cero importa; piezas: se veria plano
            ax.set_ylim(bottom=0)
        ax.set_title(f"{'Línea' if sid == series.LINE_ID else sid} · {METRIC_LABEL[metric]}", fontsize=9.5)
    handles, labels = style.fan_legend(style.BAND_C, MODEL_LABEL[tfm])
    real_h, real_l = np.atleast_1d(axes)[0].get_legend_handles_labels()
    fig.legend(handles + real_h, labels + real_l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- informe

def score_table(scores: pd.DataFrame, escenario: str, order: list[str]) -> str:
    s = scores[scores["escenario"] == escenario].copy()
    s["o"] = s["modelo"].map({m: i for i, m in enumerate(order)})
    s = s.sort_values(["metrica", "o"])
    return md_table(pd.DataFrame({
        "Métrica": s["metrica"].map(METRIC_LABEL), "Modelo": s["modelo"].map(MODEL_LABEL),
        "Error medio": [fmt(v, 0 if m == "npr" else 2) for v, m in zip(s["mae"], s["metrica"])],
        "Frente a la mejor referencia": ["" if mo in backtest.BASELINES else pct(v, signed=True)
                                         for v, mo in zip(s["mejora"], s["modelo"])],
        "Dentro de p10–p90": s["cobertura"].map(pct),
        "Series en que gana": s["gana"].map(pct),
    }))


def reading(scores: pd.DataFrame, order: list[str]) -> list[str]:
    """Una linea por escenario con quien gana en cada metrica, y otra con la banda mejor calibrada."""
    out = []
    for esc, label in [("dia", "A un día vista"), ("semana", "A la semana")]:
        s = scores[scores["escenario"] == esc].set_index(["metrica", "modelo"])
        parts = []
        for metric, model in backtest.best_variants(scores, order, esc).items():
            ref = s.loc[metric].loc[list(backtest.BASELINES)]["mae"].idxmin()
            mae, ref_mae = s.loc[(metric, model), "mae"], s.loc[(metric, ref), "mae"]
            d = 0 if metric == "npr" else 2
            if model in backtest.BASELINES:
                parts.append(f"en {METRIC_LABEL[metric]} la {MODEL_LABEL[model]} ({fmt(mae, d)} de error)")
            else:
                parts.append(f"en {METRIC_LABEL[metric]} {MODEL_LABEL[model]} ({fmt(mae, d)}, "
                             f"un {pct(1 - mae / ref_mae)} menos que la {MODEL_LABEL[ref]})")
        out.append(f"- **{label} gana** " + "; ".join(parts) + ".")
    station = scores[scores["metrica"] != series.LINE_METRIC]
    cov = station.groupby("modelo")["cobertura"].mean()
    best_cal = (cov - 0.8).abs().idxmin()
    out.append(f"- **Banda mejor calibrada:** {MODEL_LABEL[best_cal]}. El {pct(cov[best_cal])} de los días reales "
               f"cae dentro de su p10–p90 (lo ideal es el 80 %). Con la media cae el {pct(cov['media'])}.")
    worst = cov.drop(index=list(backtest.BASELINES), errors="ignore")
    if len(worst) and cov[worst.idxmin()] < 0.65:
        out.append(f"- **{MODEL_LABEL[worst.idxmin()]} tiene la banda demasiado estrecha:** solo el "
                   f"{pct(cov[worst.idxmin()])} de los días cae dentro. Con tan poca historia, "
                   "las covariables estrechan la banda sin mejorar la predicción.")
    return out


def long_stop_share(preds: pd.DataFrame, long: pd.DataFrame, model: str) -> tuple[float, int]:
    """Parte del error de TAP (semana) que cae en estacion-dias con paradas largas."""
    p = preds[(preds["escenario"] == "semana") & (preds["metrica"] == "tap_h") & (preds["modelo"] == model)]
    err = (p["p50"] - p["real"]).abs()
    keys = set(zip(long["Operacion"], long["fecha"]))
    mask = np.array([(o, f) in keys for o, f in zip(p["serie"], p["fecha"])])
    return (err[mask].sum() / err.sum() if err.sum() else 0.0), int(mask.sum())


def write_backtest(panel: series.Panel, variants, out_dir: Path, fig_dir: Path, reuse: bool = False) -> pd.DataFrame:
    order = [v.name for v in variants]
    saved = out_dir / "backtest_predicciones.csv"
    if reuse and saved.exists():
        preds = pd.read_csv(saved, parse_dates=["fecha"])
        preds = preds[preds["modelo"].isin(order)]
    else:
        preds = backtest.run(panel, variants)
    scores = backtest.score(preds)
    best = backtest.best_variants(scores, order)
    long = series.long_stops(panel)
    out_dir.mkdir(parents=True, exist_ok=True)
    preds.to_csv(out_dir / "backtest_predicciones.csv", index=False)
    scores.round(4).to_csv(out_dir / "backtest_metricas.csv", index=False)
    long.round({"tap_h": 2, "s_por_parada": 0}).to_csv(out_dir / "paradas_largas.csv", index=False)
    tfm = overall_timesfm(scores, order)
    fig = band_figure(panel, preds, tfm, fig_dir / "backtest_bandas.png") if tfm else None

    ctx, test = backtest.week_split(panel.dates)
    tfm_tap = [m for m in order if m.startswith("timesfm")]
    share_txt = ""
    if tfm_tap and len(long):
        share, n = long_stop_share(preds, long, best["tap_h"] if best["tap_h"] in tfm_tap else tfm_tap[-1])
        share_txt = (f"\nLas paradas largas pesan mucho en el error: los {n} estación-días de la semana de prueba con "
                     f"paradas de más de {series.LONG_STOP_S // 60} min de media se llevan el {pct(share)} del error de TAP. "
                     "Son eventos sueltos (posibles intervenciones planificadas) que ningún modelo puede anticipar "
                     "con datos diarios. Están en `paradas_largas.csv`.\n")
    text = f"""# Backtest · {panel.line}

Para regenerarlo: `python forecast/run_forecast.py backtest --line {panel.line}`.

- Contexto: {len(ctx)} días con producción, del {ctx[0]:%d/%m} al {ctx[-1]:%d/%m}. Prueba: {len(test)} días, del {test[0]:%d/%m} al {test[-1]:%d/%m}.
- Series: TAP, DES y SAT de {panel.values['tap_h'].shape[1]} estaciones del flujo principal, y las piezas al día de la línea.
- Modelos: {', '.join(MODEL_LABEL[m] for m in order)}. Covariables de calendario: día de la semana, primer día tras una parada y víspera de parada. Vecinas: el TAP de la estación anterior para predecir DES y el de la siguiente para SAT.

## Qué gana

{chr(10).join(reading(scores, order))}
{share_txt}
{f'![Bandas de predicción]({Path(os.path.relpath(fig, out_dir)).as_posix()})' if fig else ''}

{f'En la figura, {MODEL_LABEL[tfm]} predice la semana de prueba de golpe: la línea, y las dos estaciones con más parada propia.' if fig else ''}

## Semana completa: {len(test)} días de golpe

{score_table(scores, 'semana', order)}

## A un día vista

{score_table(scores, 'dia', order)}

Error medio: en horas para TAP, DES y SAT, en piezas para la línea. Lo ideal en «Dentro de p10–p90» es un 80 %.
«Series en que gana»: estaciones en que el modelo falla menos que las dos referencias.

## Ficheros

- `backtest_predicciones.csv`: cada predicción con sus deciles (p10 a p90) y el valor real.
- `backtest_metricas.csv`: la tabla de arriba.
- `paradas_largas.csv`: estación-días con paradas largas.
"""
    (out_dir / "BACKTEST.md").write_text(text, encoding="utf-8")
    return scores


def write_forecast(panel: series.Panel, variants, scores: pd.DataFrame, horizon: int, off, out_dir: Path,
                   force: str | None = None) -> pd.DataFrame:
    escenario = "dia" if horizon == 1 else "semana"
    best = backtest.best_variants(scores, [v.name for v in variants], escenario)
    if force:
        best = {m: force for m in best}
    by_name = {v.name: v for v in variants}
    target = series.future_dates(panel.dates[-1], horizon, set(panel.off_dates) | set(off))
    parts = [backtest.forecast(panel, by_name[model], panel.dates, target, metrics=[metric], extra_off=off)
             for metric, model in best.items()]
    fc = pd.concat(parts, ignore_index=True).rename(columns={"serie": "op"})
    fc = fc[["op", "fecha", "metrica", "p10", "p50", "p90", "modelo"]]
    fc[["p10", "p50", "p90"]] = fc[["p10", "p50", "p90"]].round(3)
    out_dir.mkdir(parents=True, exist_ok=True)
    fc.to_csv(out_dir / "forecasts.csv", index=False)

    payload = {}
    for (op, metric), g in fc.groupby(["op", "metrica"], sort=False):
        g = g.sort_values("fecha")
        payload.setdefault(op, []).append({
            "metric": metric, "modelo": g["modelo"].iloc[0],
            "days": [d.strftime("%Y-%m-%d") for d in g["fecha"]],
            **{q: g[q].tolist() for q in ["p10", "p50", "p90"]},
        })
    (out_dir / "forecast.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return fc


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Prediccion de paradas por linea")
    p.add_argument("accion", choices=["backtest", "predict"])
    p.add_argument("--line", action="append", help="linea (repetible); por defecto todas")
    p.add_argument("--data", type=Path, default=ingest.RAW_DATA)
    p.add_argument("--config", type=Path, default=ingest.RAW_CONFIG)
    p.add_argument("--lines-dir", type=Path, default=LINES_DIR)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--figures", type=Path, default=FIGURES)
    p.add_argument("--horizon", type=int, default=5, help="dias productivos a predecir (predict)")
    p.add_argument("--off", nargs="*", default=[], help="dias futuros sin produccion, AAAA-MM-DD (predict)")
    p.add_argument("--sin-timesfm", action="store_true", help="solo las referencias (rapido, sin descargar nada)")
    p.add_argument("--modelo", help="predict: usar esta variante para todo en vez de la que gano el backtest")
    p.add_argument("--solo-informe", action="store_true",
                   help="backtest: rehacer el informe con las predicciones ya guardadas, sin volver a predecir")
    args = p.parse_args(argv)

    raw = ingest.load(args.data, args.config)
    variants = backtest.default_variants(use_timesfm=not args.sin_timesfm)
    if args.modelo and args.modelo not in [v.name for v in variants]:
        sys.exit(f"--modelo debe ser una de: {[v.name for v in variants]}")
    off = [pd.Timestamp(d) for d in args.off]
    for line in args.line or ingest.lines(raw):
        panel = series.load_line(line, args.data, args.config, args.lines_dir)
        out_dir = args.out / line
        metrics_csv = out_dir / "backtest_metricas.csv"
        if args.accion == "backtest" or not metrics_csv.exists():
            scores = write_backtest(panel, variants, out_dir, args.figures / line, reuse=args.solo_informe)
            print(f"{line}: backtest en {out_dir / 'BACKTEST.md'}")
        else:
            scores = pd.read_csv(metrics_csv)
            scores = scores[scores["modelo"].isin([v.name for v in variants])]
        if args.accion == "predict":
            fc = write_forecast(panel, variants, scores, args.horizon, off, out_dir, args.modelo)
            print(f"{line}: {len(fc)} predicciones en {out_dir / 'forecasts.csv'} y forecast.json "
                  f"({fc['fecha'].min():%d/%m} a {fc['fecha'].max():%d/%m})")


if __name__ == "__main__":
    main()
