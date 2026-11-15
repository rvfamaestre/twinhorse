"""Figuras de la clasificacion de paradas (classify.py). Desde la raiz del repo:

    python stops/plots.py --line VLL_MONTAJE_L5

Lee data/processed/<linea>/stops.csv (y, si existe, el backtest de forecast/output/<linea>/)
y escribe stops/output/<linea>/STOPS.md con sus figuras en figures/stops/<linea>/.
"""

import argparse
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eda import plots as style  # noqa: E402  (misma paleta que el EDA)
from eda.plots import fmt  # noqa: E402
from stops.classify import MICRO_S, PERDIDA_MIN_H, PROCESSED, TIPOS  # noqa: E402

OUT = ROOT / "stops" / "output"
FIGURES = ROOT / "figures" / "stops"
FORECAST_OUT = ROOT / "forecast" / "output"  # backtest de la prediccion
# Color por tipo: azul = propia (TAP), naranja = DES, verde = SAT, grises = no se clasifica.
COLOR = {
    TIPOS["microparada"]: "#7fb0ec", TIPOS["parada_larga"]: style.TAP_C,
    TIPOS["desabastecimiento"]: style.DES_C, TIPOS["saturacion"]: style.SAT_C,
    TIPOS["ok"]: style.LIGHT, TIPOS["sensor"]: "#b9b8b0", TIPOS["error_registro"]: style.INK2,
}
LABEL = {
    TIPOS["microparada"]: "microparada (propia, < 60 s)", TIPOS["parada_larga"]: "parada larga (propia)",
    TIPOS["desabastecimiento"]: "desabastecimiento (le faltan piezas)",
    TIPOS["saturacion"]: "saturación (no puede soltar)", TIPOS["ok"]: "ok",
    TIPOS["sensor"]: "sensor dudoso", TIPOS["error_registro"]: "error de registro",
}
ORDER = list(COLOR)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def type_map(stops: pd.DataFrame, path: Path) -> Path:
    """Estacion x dia coloreado por tipo: el semaforo completo de la linea."""
    ops = stops.groupby("op")["orden"].first().sort_values().index
    days = sorted(stops["fecha"].unique())
    grid = stops.pivot(index="fecha", columns="op", values="tipo").reindex(index=days, columns=ops)
    codes = grid.apply(lambda c: c.map({t: i for i, t in enumerate(ORDER)}))
    fig, ax = plt.subplots(figsize=(style._wide(len(ops)), 4.2))
    ax.imshow(codes.to_numpy(dtype=float), aspect="auto", interpolation="none",
              cmap=ListedColormap([COLOR[t] for t in ORDER]), vmin=-0.5, vmax=len(ORDER) - 0.5)
    ax.set_xticks(np.arange(len(ops)), ops, rotation=90, fontsize=6)
    dia = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    ax.set_yticks(np.arange(len(days)),
                  [f"{dia[pd.Timestamp(d).day_of_week]} {pd.Timestamp(d):%d/%m}" for d in days], fontsize=7)
    bloque = stops.groupby("op")["bloque"].first().reindex(ops).to_numpy()
    for j in np.flatnonzero(bloque[1:] != bloque[:-1]):
        ax.axvline(j + 0.5, color=style.INK, linewidth=1.2)
    for j in range(len(ops)):
        ax.axvline(j + 0.5, color=style.SURFACE, linewidth=0.4)
    ax.tick_params(length=0)
    ax.spines[:].set_visible(False)
    ax.set_title("Qué le pasó a cada estación cada día (estaciones en orden de la línea; "
                 "las líneas negras separan línea, subconjuntos y manipuladores)")
    ax.legend(handles=[Patch(color=COLOR[t], label=LABEL[t]) for t in ORDER], loc="upper center",
              bbox_to_anchor=(0.5, -0.32), ncol=4)
    return _save(fig, path)


def type_totals(stops: pd.DataFrame, path: Path) -> Path:
    """Cuantos estacion-dia hay de cada tipo y cuantas horas pierde cada uno."""
    valid = stops[~stops["tipo"].isin([TIPOS["error_registro"], TIPOS["sensor"]])]
    counts = stops["tipo"].value_counts().reindex(ORDER, fill_value=0)
    hours = pd.Series({
        "propia (TAP)": valid["tap_h"].sum(), "desabastecida (DES)": valid["des_h"].sum(),
        "saturada (SAT)": valid["sat_h"].sum()})
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 3.4), gridspec_kw={"wspace": 0.9, "width_ratios": [1.3, 1]})
    y = np.arange(len(ORDER))[::-1]
    a.barh(y, counts.to_numpy(), color=[COLOR[t] for t in ORDER], edgecolor=style.AXIS, linewidth=0.5)
    a.set_yticks(y, [LABEL[t] for t in ORDER])
    for yi, v in zip(y, counts):
        a.text(v + 8, yi, fmt(v, 0), va="center", fontsize=8, color=style.INK2)
    a.set_title(f"Tipo de cada estación-día ({fmt(len(stops), 0)} en total)")
    a.xaxis.grid(True)
    a.set_axisbelow(True)
    yb = np.arange(3)[::-1]
    b.barh(yb, hours.to_numpy(), color=[style.TAP_C, style.DES_C, style.SAT_C])
    b.set_yticks(yb, hours.index)
    for yi, v in zip(yb, hours):
        b.text(v + 20, yi, f"{fmt(v, 0)} h", va="center", fontsize=8, color=style.INK2)
    b.set_title("Horas perdidas en total (filas fiables)")
    b.xaxis.grid(True)
    b.set_axisbelow(True)
    b.set_xlim(0, hours.max() * 1.25)
    return _save(fig, path)


def own_stop_threshold(stops: pd.DataFrame, path: Path) -> Path:
    """Dias en que manda la parada propia: duracion media de cada parada frente a horas de TAP."""
    own = stops[stops["tipo"].isin([TIPOS["microparada"], TIPOS["parada_larga"]]) & stops["s_por_parada"].notna()]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for t in [TIPOS["microparada"], TIPOS["parada_larga"]]:
        g = own[own["tipo"] == t]
        ax.scatter(g["s_por_parada"], g["tap_h"], s=22, color=COLOR[t], edgecolor=style.SURFACE,
                   linewidth=0.5, label=f"{LABEL[t]}: {len(g)} estación-días")
    ax.axvline(MICRO_S, color=style.INK, linestyle=style.DASH, linewidth=1)
    ax.text(MICRO_S * 1.06, ax.get_ylim()[1] * 0.95, f"umbral {fmt(MICRO_S, 0)} s", fontsize=8, va="top")
    ax.set_xscale("log")
    # Una etiqueta por tipo: la estacion con mas dias de ese tipo, junto a su dia de mas TAP.
    for t in [TIPOS["microparada"], TIPOS["parada_larga"]]:
        g = own[own["tipo"] == t]
        if g.empty:
            continue
        op = g["op"].value_counts().index[0]
        top = g[g["op"] == op].nlargest(1, "tap_h").iloc[0]
        ax.annotate(f"{op} ({(g['op'] == op).sum()} días)", (top["s_por_parada"], top["tap_h"]),
                    xytext=(-8, 10), textcoords="offset points", ha="right", fontsize=8, color=style.INK,
                    arrowprops={"arrowstyle": "-", "color": style.MUTED, "linewidth": 0.6})
    ax.set_xlabel("segundos por parada (escala log)")
    ax.set_ylabel("horas de parada propia ese día")
    ax.grid(True)
    ax.set_axisbelow(True)
    ax.set_title("Microparada o parada larga: solo los días en que manda la parada propia", pad=28)
    style._legend_above(ax, 2)
    return _save(fig, path)


def band_preview(stops: pd.DataFrame, preds: pd.DataFrame, path: Path, n: int = 4) -> tuple[Path, pd.DataFrame]:
    """TAP real frente a la banda a un dia vista de TimesFM (forecast/run_forecast.py backtest)."""
    band = preds[(preds["escenario"] == "dia") & (preds["modelo"] == "timesfm") & (preds["metrica"] == "tap_h")]
    band = band.assign(fecha=band["fecha"].dt.strftime("%Y-%m-%d"))
    band["fuera"] = (band["real"] < band["p10"]) | (band["real"] > band["p90"])
    table = band.merge(stops[["op", "fecha", "tipo"]], left_on=["serie", "fecha"], right_on=["op", "fecha"])
    # Estaciones con alguna alerta, las que mas parada propia acumulan (donde TAP importa).
    alerted = table.groupby("op")["fuera"].sum()
    tap_total = stops.groupby("op")["tap_h"].sum()
    picks = tap_total.reindex(alerted[alerted > 0].index).sort_values(ascending=False, kind="stable").head(n).index

    fig, axes = plt.subplots(1, n, figsize=(4 * n, 3.4), gridspec_kw={"wspace": 0.3})
    for ax, op in zip(axes, picks):
        hist = stops[stops["op"] == op].sort_values("fecha")
        b = table[table["op"] == op].sort_values("fecha")
        pos = {d: i for i, d in enumerate(hist["fecha"])}
        xb = [pos[d] for d in b["fecha"]]
        style.fan(ax, xb, b, style.BAND_C)
        ax.plot(range(len(hist)), hist["tap_h"], color=style.AXIS, linewidth=1, zorder=1)
        ax.scatter(range(len(hist)), hist["tap_h"], s=26, zorder=3, edgecolor=style.SURFACE, linewidth=0.5,
                   color=[COLOR[t] for t in hist["tipo"]])
        out = b[b["fuera"]]
        ax.scatter([pos[d] for d in out["fecha"]], out["real"], s=150, facecolors="none", edgecolors=style.INK,
                   linewidth=1.5, zorder=4, label="fuera de banda → alerta")
        ax.axvline(min(xb) - 0.5, color=style.AXIS, linewidth=1)
        ax.set_xticks(range(0, len(hist), 3), [pd.Timestamp(d).strftime("%d/%m") for d in hist["fecha"][::3]])
        ax.set_ylim(bottom=0)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.set_title(f"{op} · TAP (h) · {int(b['fuera'].sum())} de {len(b)} días fuera")
    # Dos filas: la banda y la alerta arriba, los tipos de parada debajo.
    handles, labels = style.fan_legend(style.BAND_C, "TimesFM")
    out_h, out_l = axes[0].get_legend_handles_labels()
    fig.legend(handles + out_h, labels + out_l, loc="lower center", ncol=len(handles) + len(out_h),
               bbox_to_anchor=(0.5, -0.1))
    shown = [t for t in ORDER if t in set(stops[stops["op"].isin(picks)]["tipo"])]
    fig.legend([Patch(color=COLOR[t]) for t in shown], [LABEL[t] for t in shown], loc="lower center",
               ncol=len(shown), bbox_to_anchor=(0.5, -0.2))
    return _save(fig, path), table


def report(line: str, stops: pd.DataFrame, figs: dict, table: pd.DataFrame | None) -> str:
    counts = stops["tipo"].value_counts()
    res = stops.groupby("op")["tipo"].agg(lambda t: t.value_counts().idxmax())
    induced = counts.get(TIPOS["desabastecimiento"], 0) + counts.get(TIPOS["saturacion"], 0)
    own = counts.get(TIPOS["microparada"], 0) + counts.get(TIPOS["parada_larga"], 0)
    lines = [
        f"# Clasificación de paradas · {line}",
        "",
        f"Para regenerarlo: `python stops/classify.py --line {line}` y `python stops/plots.py --line {line}`.",
        "",
        f"Cada estación-día productivo ({fmt(len(stops), 0)}) recibe un tipo por reglas fijas, sin modelo. "
        f"En {fmt(induced, 0)} manda una parada inducida por las vecinas y en {fmt(own, 0)} la parada propia. "
        f"{fmt(counts.get(TIPOS['error_registro'], 0) + counts.get(TIPOS['sensor'], 0), 0)} no se clasifican "
        "porque el dato no es fiable.",
        "",
        "Reglas, en orden (la primera que se cumple decide): error de registro (sin datos o fuera de servicio) → "
        "sensor dudoso (NAP > NPR) → error de registro (contador roto o doble) → si se pierde al menos "
        f"{fmt(PERDIDA_MIN_H, 0)} h, la mayor de SAT, DES o TAP (TAP con menos de {fmt(MICRO_S, 0)} s por parada "
        "es microparada) → ok.",
        "",
        f"![Mapa de tipos]({figs['mapa']})",
        "",
        f"![Totales]({figs['totales']})",
        "",
        f"Lo inducido pesa más que lo propio: la mayoría de estaciones pasa casi todos sus días sin piezas o "
        f"bloqueada. Estaciones donde manda la parada propia: "
        f"{', '.join(sorted(res[res.isin([TIPOS['microparada'], TIPOS['parada_larga']])].index)) or 'ninguna'}.",
        "",
        f"![Umbral microparada]({figs['umbral']})",
    ]
    if table is not None:
        out = table[table["fuera"]]
        by_type = out["tipo"].value_counts()
        lines += [
            "",
            "## Paradas fuera de la banda de normalidad",
            "",
            f"Con la banda de TimesFM a un día vista, {len(out)} de {len(table)} estación-días de la semana de prueba "
            f"({fmt(100 * len(out) / len(table), 0)} %) tienen un TAP fuera de p10–p90. Por tipo: "
            + ", ".join(f"{LABEL[t]} {n}" for t, n in by_type.items()) + ". "
            "Es la base de los avisos por banda del gemelo 3D (`frontend/scripts/build_mock.py`).",
            "",
            f"![Banda]({figs['banda']})",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description="Figuras de la clasificacion de paradas")
    p.add_argument("--line", default="VLL_MONTAJE_L5")
    args = p.parse_args()

    stops = pd.read_csv(PROCESSED / args.line / "stops.csv")
    out, fig_dir = OUT / args.line, FIGURES / args.line
    out.mkdir(parents=True, exist_ok=True)
    figs = {
        "mapa": type_map(stops, fig_dir / "stops_mapa.png"),
        "totales": type_totals(stops, fig_dir / "stops_totales.png"),
        "umbral": own_stop_threshold(stops, fig_dir / "stops_umbral.png"),
    }
    table = None
    preds_path = FORECAST_OUT / args.line / "backtest_predicciones.csv"
    if preds_path.exists():
        figs["banda"], table = band_preview(stops, pd.read_csv(preds_path, parse_dates=["fecha"]),
                                            fig_dir / "stops_vs_banda.png")
    figs = {k: Path(os.path.relpath(v, out)).as_posix() for k, v in figs.items()}
    (out / "STOPS.md").write_text(report(args.line, stops, figs, table), encoding="utf-8")
    print(f"Escrito {out / 'STOPS.md'} con {len(figs)} figuras")


if __name__ == "__main__":
    main()
