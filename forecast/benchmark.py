"""Benchmark de la prediccion: ventanas de contexto x horizontes, con origen rodante.

    python forecast/benchmark.py --line VLL_MONTAJE_L5          # unos minutos en CPU
    python forecast/benchmark.py --solo-informe                 # rehace informe y figura

Para cada contexto C (dias de historia que ve el modelo) y horizonte H (dias que predice):
se coloca el origen en cada dia t posible, el modelo ve los C dias anteriores a t y predice
t .. t+H-1. Todas las configuraciones se evaluan en los MISMOS dias objetivo (origenes desde
FIRST_ORIGIN, que deja historia para el contexto mas largo), asi la diferencia entre ellas
solo se debe a la ventana. Reutiliza forecast() y score() de backtest.py sin cambiarlos.
"""

import argparse
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eda import plots as style  # noqa: E402
from eda.plots import fmt  # noqa: E402
from forecast import backtest, series  # noqa: E402
from forecast.run_forecast import METRIC_LABEL, MODEL_LABEL, md_table  # noqa: E402

CONTEXTS = [4, 6, 8, 10]
HORIZONS = [1, 3, 5]
FIRST_ORIGIN = max(CONTEXTS)  # indice del primer dia que se predice
OUT = ROOT / "forecast" / "output"
FIGURES = ROOT / "figures" / "forecast"


def origins(n_days: int, h: int) -> range:
    return range(FIRST_ORIGIN, n_days - h + 1)


def run(panel: series.Panel, variants) -> pd.DataFrame:
    dates, parts = panel.dates, []
    for c in CONTEXTS:
        for h in HORIZONS:
            for t in origins(len(dates), h):
                ctx, target = dates[t - c:t], dates[t:t + h]
                for v in variants:
                    parts.append(backtest.forecast(panel, v, ctx, target).assign(
                        escenario=f"C{c}_H{h}", contexto=c, horizonte=h, origen=dates[t]))
            print(f"  contexto {c}, horizonte {h}: {len(origins(len(dates), h))} orígenes", flush=True)
    preds = pd.concat(parts, ignore_index=True)
    return preds.merge(backtest._actuals(panel), on=["fecha", "serie", "metrica"], how="left").dropna(subset=["real"])


def scores(preds: pd.DataFrame) -> pd.DataFrame:
    s = backtest.score(preds)
    s[["contexto", "horizonte"]] = s["escenario"].str.extract(r"C(\d+)_H(\d+)").astype(int)
    n = preds.groupby(["escenario", "metrica", "modelo"]).size().rename("predicciones").reset_index()
    return s.merge(n, on=["escenario", "metrica", "modelo"])


def daily_skill(preds: pd.DataFrame, model: str) -> pd.DataFrame:
    """Mejora frente a la mejor referencia, calculada por separado en cada dia objetivo.

    Sirve para ver si la mejora es estable o depende de un par de dias (dispersion entre dias).
    """
    p = preds.assign(err=(preds["p50"] - preds["real"]).abs())
    g = p.groupby(["contexto", "horizonte", "metrica", "fecha", "modelo"])["err"].mean().unstack("modelo")
    base = g[backtest.BASELINES].min(axis=1)
    return (1 - g[model] / base).rename("mejora").reset_index()


# ---------------------------------------------------------------- figuras

def heatmaps(s: pd.DataFrame, model: str, path: Path) -> Path:
    """Mejora de un modelo frente a la mejor referencia, por metrica, en la rejilla contexto x horizonte."""
    metrics = list(METRIC_LABEL)
    fig, axes = plt.subplots(1, len(metrics), figsize=(3.4 * len(metrics), 3.0), gridspec_kw={"wspace": 0.35})
    sub = s[s["modelo"] == model]
    lim = max(0.3, sub["mejora"].abs().max())
    for ax, m in zip(axes, metrics):
        grid = sub[sub["metrica"] == m].pivot(index="contexto", columns="horizonte", values="mejora")
        grid = grid.reindex(index=CONTEXTS, columns=HORIZONS)
        im = ax.imshow(grid.to_numpy(), cmap="RdBu", vmin=-lim, vmax=lim, aspect="auto")
        for (i, j), v in np.ndenumerate(grid.to_numpy()):
            ax.text(j, i, f"{'+' if v > 0 else ''}{fmt(100 * v, 0)} %", ha="center", va="center", fontsize=8,
                    color="white" if abs(v) > 0.6 * lim else style.INK)
        ax.set_xticks(range(len(HORIZONS)), [f"{h} d" for h in HORIZONS])
        ax.set_yticks(range(len(CONTEXTS)), [f"{c} d" for c in CONTEXTS])
        ax.set_xlabel("horizonte")
        if m == metrics[0]:
            ax.set_ylabel("contexto")
        ax.set_title(METRIC_LABEL[m], fontsize=9.5)
        ax.spines[:].set_visible(False)
    fig.colorbar(im, ax=axes, shrink=0.8, label="menos error que la mejor referencia")
    fig.suptitle(f"{MODEL_LABEL[model]} frente a la mejor referencia (azul = gana, rojo = pierde)",
                 x=0.1, ha="left", fontsize=10.5, y=1.04)
    return _save(fig, path)


def by_horizon(s: pd.DataFrame, path: Path) -> Path:
    """Error y cobertura de la banda segun el horizonte, con el contexto mas largo."""
    sub = s[s["contexto"] == max(CONTEXTS)]
    models = list(dict.fromkeys(sub["modelo"]))
    colors = {"ultimo_valor": style.MUTED, "media": style.INK, "timesfm": style.TAP_C,
              "timesfm_calendario": style.DES_C, "timesfm_vecinas": style.SAT_C}
    metrics = list(METRIC_LABEL)
    fig, axes = plt.subplots(2, len(metrics), figsize=(3.4 * len(metrics), 5.4),
                             gridspec_kw={"wspace": 0.35, "hspace": 0.45})
    for j, m in enumerate(metrics):
        for mo in models:
            g = sub[(sub["metrica"] == m) & (sub["modelo"] == mo)].sort_values("horizonte")
            dash = style.DASH if mo in backtest.BASELINES else "-"
            axes[0, j].plot(g["horizonte"], g["mae"], marker="o", ms=3, color=colors.get(mo), linestyle=dash,
                            label=MODEL_LABEL[mo])
            axes[1, j].plot(g["horizonte"], 100 * g["cobertura"], marker="o", ms=3, color=colors.get(mo),
                            linestyle=dash)
        axes[1, j].axhline(80, color=style.AXIS, linewidth=1)
        axes[0, j].set_title(f"{METRIC_LABEL[m]} · error medio", fontsize=9)
        axes[1, j].set_title(f"{METRIC_LABEL[m]} · días dentro de p10–p90 (%)", fontsize=9)
        for ax in axes[:, j]:
            ax.set_xticks(HORIZONS, [f"{h} d" for h in HORIZONS])
            ax.yaxis.grid(True)
            ax.set_axisbelow(True)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(models), bbox_to_anchor=(0.5, -0.04))
    fig.suptitle(f"Según el horizonte, con {max(CONTEXTS)} días de contexto (la línea gris marca el 80 % ideal)",
                 x=0.1, ha="left", fontsize=10.5)
    return _save(fig, path)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- informe

def conclusion(s: pd.DataFrame) -> str:
    """Tres frases calculadas: efecto del contexto, mejor modelo por celda y calibracion de la banda."""
    t = s[(s["modelo"] == "timesfm") & (s["horizonte"] == min(HORIZONS)) & (s["metrica"] == "tap_h")]
    t = t.set_index("contexto")["mejora"]
    station = s[s["metrica"] != series.LINE_METRIC]
    best = station.loc[station.groupby(["contexto", "horizonte", "metrica"])["mae"].idxmin(), "modelo"]
    cov = station.groupby("modelo")["cobertura"].mean()
    return "\n".join([
        f"- **Más contexto ayuda a TimesFM:** en TAP a {min(HORIZONS)} día pasa de "
        f"{fmt(100 * t[min(CONTEXTS)], 0)} % con {min(CONTEXTS)} días de historia a "
        f"{'+' if t[max(CONTEXTS)] > 0 else ''}{fmt(100 * t[max(CONTEXTS)], 0)} % con {max(CONTEXTS)}. "
        "Con los 16 días que tenemos, no llega a separarse de forma clara.",
        f"- **Para el valor central gana la media** en {(best == 'media').sum()} de {len(best)} celdas de estación. "
        "Predecir el número exacto de horas de mañana con dos semanas de historia no mejora a «lo de siempre».",
        f"- **Para la banda gana TimesFM:** el {fmt(100 * cov['timesfm'], 0)} % de los días reales cae dentro de su "
        f"p10–p90 (ideal 80 %), frente al {fmt(100 * cov['media'], 0)} % de la media y el "
        f"{fmt(100 * cov['ultimo_valor'], 0)} % del último valor. Las covariables estrechan demasiado la banda. "
        "Por eso usamos TimesFM sin covariables como **banda de normalidad para detectar anomalías**, no como pronóstico.",
    ])


def report(line: str, preds: pd.DataFrame, s: pd.DataFrame, figs: dict) -> str:
    tfm = [m for m in s["modelo"].unique() if m.startswith("timesfm")]
    station = s[s["metrica"] != series.LINE_METRIC]
    # Resumen: por modelo, en cuantas celdas (contexto, horizonte, metrica) gana a la mejor referencia.
    rows = []
    for mo in [m for m in MODEL_LABEL if m in s["modelo"].unique()]:
        g = s[s["modelo"] == mo]
        rows.append({
            "Modelo": MODEL_LABEL[mo],
            "Celdas en que gana": "" if mo in backtest.BASELINES else f"{(g['mejora'] > 0.01).sum()} de {len(g)}",
            "Mejora media (estaciones)": "" if mo in backtest.BASELINES else
            f"{fmt(100 * station[station['modelo'] == mo]['mejora'].mean(), 1)} %",
            "Cobertura p10–p90 (estaciones)": f"{fmt(100 * station[station['modelo'] == mo]['cobertura'].mean(), 0)} %",
        })
    best = s[s["modelo"].isin(tfm)].sort_values("mejora", ascending=False)
    top = best.head(5)
    top_tbl = pd.DataFrame({
        "Métrica": top["metrica"].map(METRIC_LABEL), "Modelo": top["modelo"].map(MODEL_LABEL),
        "Contexto": top["contexto"].astype(str) + " d", "Horizonte": top["horizonte"].astype(str) + " d",
        "Mejora": top["mejora"].map(lambda v: f"{fmt(100 * v, 0)} %"),
    })
    if "timesfm" not in tfm:
        return "Benchmark sin TimesFM: solo referencias.\n\n" + md_table(pd.DataFrame(rows)) + "\n"
    ds = daily_skill(preds, "timesfm")
    tap_h1 = ds[(ds["metrica"] == "tap_h") & (ds["horizonte"] == 1) & (ds["contexto"] == max(CONTEXTS))]
    n_days = preds["fecha"].nunique()
    t0, t1 = preds["fecha"].min(), preds["fecha"].max()
    return f"""# Benchmark de la predicción · {line}

Para regenerarlo: `python forecast/benchmark.py --line {line}`.

- **Rejilla:** contexto {', '.join(map(str, CONTEXTS))} días × horizonte {', '.join(map(str, HORIZONS))} días, con origen rodante.
- **Mismos días objetivo para todas las configuraciones:** {n_days} días productivos, del {t0:%d/%m} al {t1:%d/%m}. Así la diferencia entre celdas solo se debe a la ventana.
- **Series:** TAP, DES y SAT de {preds[preds['metrica'] == 'tap_h']['serie'].nunique()} estaciones y las piezas al día de la línea. {fmt(len(preds), 0)} predicciones en total.
- **Modelos:** {', '.join(MODEL_LABEL[m] for m in MODEL_LABEL if m in s['modelo'].unique())}.
- **Mejora** = cuánto menos falla que la mejor de las dos referencias (último valor y media) en esa misma celda. Una mejora por debajo del 1 % cuenta como empate.

## Conclusión

{conclusion(s)}

## Resultado

{md_table(pd.DataFrame(rows))}

![Mejora por contexto y horizonte]({figs['heat']})

![Error y cobertura por horizonte]({figs['hor']})

Las cinco celdas donde TimesFM más gana:

{md_table(top_tbl)}

**Estabilidad:** en TAP a un día vista con {max(CONTEXTS)} días de contexto, la mejora de TimesFM día a día va del {fmt(100 * tap_h1['mejora'].min(), 0)} % al {fmt(100 * tap_h1['mejora'].max(), 0)} % ({len(tap_h1)} días). Con tan pocos días objetivo, diferencias de pocos puntos entre celdas no son significativas.

Las tablas completas están en `benchmark_metricas.csv` y las predicciones en `benchmark_predicciones.csv`.
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Benchmark contexto x horizonte")
    p.add_argument("--line", default="VLL_MONTAJE_L5")
    p.add_argument("--sin-timesfm", action="store_true")
    p.add_argument("--solo-informe", action="store_true")
    args = p.parse_args()

    out = OUT / args.line
    saved = out / "benchmark_predicciones.csv"
    panel = series.load_line(args.line)
    if args.solo_informe and saved.exists():
        preds = pd.read_csv(saved, parse_dates=["fecha", "origen"])
    else:
        preds = run(panel, backtest.default_variants(use_timesfm=not args.sin_timesfm))
        out.mkdir(parents=True, exist_ok=True)
        preds.to_csv(saved, index=False)
    s = scores(preds)
    s.round(4).to_csv(out / "benchmark_metricas.csv", index=False)
    tfm = "timesfm" if "timesfm" in s["modelo"].unique() else "media"
    fig_dir = FIGURES / args.line
    figs = {"heat": heatmaps(s, tfm, fig_dir / "benchmark_mejora.png"),
            "hor": by_horizon(s, fig_dir / "benchmark_horizonte.png")}
    figs = {k: Path(os.path.relpath(v, out)).as_posix() for k, v in figs.items()}
    (out / "BENCHMARK.md").write_text(report(args.line, preds, s, figs), encoding="utf-8")
    print(f"Escrito {out / 'BENCHMARK.md'}")


if __name__ == "__main__":
    main()
