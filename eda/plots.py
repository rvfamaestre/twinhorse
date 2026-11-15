"""Figuras del EDA. Cada funcion recibe los datos de una linea y su LineSettings y guarda un PNG.

Paleta: gris para el contexto y color solo cuando significa algo. Azul, naranja y verde
son siempre TAP, DES y SAT; el negro marca lo que supera un objetivo.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Patch, Rectangle

from backend.pipeline.settings import LineSettings, num

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, LIGHT = "#e1e0d9", "#c3c2b7", "#f0efec"
TAP_C, DES_C, SAT_C = "#2a78d6", "#eb6834", "#1baf7a"
DASH = (0, (4, 3))
# Banda de prediccion: intervalos centrales del 80, 60, 40 y 20 %, superpuestos. Cuanto mas
# probable, mas oscuro. Nunca se dibuja una linea central (ni mediana ni media).
FAN = [("p10", "p90", 80), ("p20", "p80", 60), ("p30", "p70", 40), ("p40", "p60", 20)]
FAN_ALPHA = 0.15
BAND_C = INK2  # la banda es incertidumbre, no un tipo de perdida: gris

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "axes.titlesize": 10, "axes.titlelocation": "left", "axes.titlepad": 10,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "grid.color": GRID, "grid.linewidth": 0.6, "hatch.color": AXIS,
    "legend.frameon": False, "legend.fontsize": 8,
})


def fmt(x: float, d: int = 1) -> str:
    """Numero en formato espanol: coma decimal y punto de miles."""
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def period_word(df: pd.DataFrame) -> str:
    return "días" if df["Jour"].nunique() > 1 else "semanas"


def fan(ax, x, band: pd.DataFrame, color: str) -> None:
    """Banda de prediccion en degradado: cada intervalo central encima del anterior."""
    for lo, hi, _ in FAN:
        if lo in band and hi in band:
            ax.fill_between(x, band[lo], band[hi], color=color, alpha=FAN_ALPHA, linewidth=0)


def fan_legend(color: str, name: str) -> tuple[list, list]:
    """Una muestra por intervalo, con el tono que sale al superponerlos."""
    handles = [Patch(color=color, alpha=1 - (1 - FAN_ALPHA) ** (k + 1), linewidth=0) for k in range(len(FAN))]
    labels = [f"{name}: {p} % prob." if k == 0 else f"{p} %" for k, (_, _, p) in enumerate(FAN)]
    return handles, labels


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _station_axis(ax, labels, n):
    ax.set_xticks(np.arange(n), labels, rotation=90, fontsize=6)
    ax.set_xlim(-0.8, n - 0.2)
    ax.tick_params(axis="x", length=0)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)


def _wide(n: int) -> float:
    return max(8.0, 0.15 * n + 2)


def _legend_above(ax, ncol: int) -> None:
    """Leyenda entre el titulo y los datos, para que nunca tape una barra o un punto."""
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=ncol, borderaxespad=0.3)


def _labels(ax, xs, ys, texts, colors, fontsize: float = 8) -> None:
    """Etiqueta cada punto a su derecha (o a su izquierda si no cabe) y separa en vertical
    las que se pisarian, con una linea fina hasta el punto cuando se desplazan."""
    fig = ax.figure
    fig.canvas.draw()
    pts = ax.transData.transform(np.column_stack([xs, ys]))
    px = fontsize * fig.dpi / 72
    gap, pad = 1.25 * px, 6 * fig.dpi / 72
    placed, out = [], {}
    for i in np.argsort(pts[:, 1]):
        w = 0.58 * px * len(texts[i])
        left = pts[i, 0] + pad + w > ax.bbox.x1
        x0 = pts[i, 0] - pad - w if left else pts[i, 0] + pad
        y = pts[i, 1]
        for a0, a1, ay in sorted(placed, key=lambda p: p[2]):
            if a0 < x0 + w and x0 < a1 and abs(y - ay) < gap:
                y = ay + gap
        placed.append((x0, x0 + w, y))
        out[i] = (left, y)
    for i, (left, y) in out.items():
        dy = (y - pts[i, 1]) * 72 / fig.dpi
        ax.annotate(texts[i], (xs[i], ys[i]), xytext=(-6 if left else 6, dy), textcoords="offset points",
                    ha="right" if left else "left", va="center", fontsize=fontsize, color=colors[i],
                    arrowprops=dict(arrowstyle="-", color=AXIS, linewidth=0.6, shrinkA=1, shrinkB=3)
                    if abs(dy) > 4 else None)


def exclusion_reason(op: str, grupo: str, flags: pd.DataFrame, s: LineSettings) -> str:
    """Por que una estacion no cuenta en el ranking ('' si cuenta)."""
    if grupo == "fuera_flujo":
        return "fuera del flujo"
    for flag, label in [("sin_datos", "sin datos"), ("fuera_servicio", "fuera de servicio"),
                        ("sensor_sospechoso", "sensor sospechoso")]:
        if op in flags.index and flags.loc[op, flag] >= s.station_share:
            return label
    return ""


def time_required(df: pd.DataFrame, s: LineSettings, path: Path) -> Path:
    """Mapa estacion x periodo de TR menos el tiempo requerido."""
    order = df.groupby("Operacion")["Orden_OP"].first().sort_values().index
    dates = sorted(df["fecha"].unique())
    grid = df.pivot(index="Operacion", columns="fecha", values="TR").loc[order, dates] - s.required_h
    off = df.groupby("fecha")["no_productivo"].first().loc[dates].to_numpy()
    values = np.ma.masked_array(grid.to_numpy(), mask=np.repeat(off[None, :], len(order), axis=0))

    lim = 0.2 * s.required_h
    cmap = LinearSegmentedColormap.from_list(
        "tr", ["#184f95", "#86b6ef", LIGHT, "#f2a09f", "#b3302f"]).with_extremes(bad=SURFACE)
    fig, ax = plt.subplots(figsize=(max(5.5, 0.3 * len(dates) + 2.5), max(4.0, 0.14 * len(order) + 1.5)))
    im = ax.imshow(values, aspect="auto", cmap=cmap, norm=TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim),
                   interpolation="nearest")
    for j in np.flatnonzero(off):
        ax.add_patch(Rectangle((j - 0.5, -0.5), 1, len(order), facecolor=LIGHT, hatch="////",
                               edgecolor=AXIS, linewidth=0))
        ax.text(j, len(order) / 2, "sin producción", rotation=90, ha="center", va="center",
                color=INK2, fontsize=8)
    weeks = pd.DatetimeIndex(dates).isocalendar().week.to_numpy()
    for j in np.flatnonzero(np.diff(weeks)):
        ax.axvline(j + 0.5, color=SURFACE, linewidth=2.5)
    ax.set_yticks(range(len(order)), order, fontsize=5.5 if len(order) > 50 else 7)
    ax.set_xticks(range(len(dates)), [pd.Timestamp(d).strftime("%d/%m") for d in dates],
                  rotation=90, fontsize=7)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(f"Horas registradas menos las {num(s.required_h)} h requeridas")
    cb = fig.colorbar(im, ax=ax, orientation="horizontal", fraction=0.025, pad=0.05, extend="both")
    cb.set_label(f"TR − {num(s.required_h)} h (horas)", color=INK2)
    cb.outline.set_visible(False)
    return _save(fig, path)


def ranking(df: pd.DataFrame, totals: pd.DataFrame, flags: pd.DataFrame, s: LineSettings,
            path: Path, top: int = 10) -> Path:
    """TAP sin limpiar frente a TAP limpio: la que mas se para no es la que penaliza."""
    tap = df.groupby(["Operacion", "no_productivo"])["TAP"].sum().unstack(fill_value=0.0)
    raw = pd.DataFrame({"on": tap.get(False, 0.0), "off": tap.get(True, 0.0)})
    raw["total"] = raw["on"] + raw["off"]
    raw = raw.nlargest(top, "total").iloc[::-1]
    cleaned = totals[totals["en_ranking"]].nlargest(top, "tap_h").iloc[::-1]
    grupo = df.groupby("Operacion")["grupo"].first()
    unit = period_word(df)

    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 0.3 * top + 1.6), gridspec_kw={"wspace": 0.55})
    why = [exclusion_reason(op, grupo[op], flags, s) for op in raw.index]
    y = np.arange(len(raw))
    a.barh(y, raw["on"], color=[AXIS if w else TAP_C for w in why], height=0.62,
           edgecolor=SURFACE, linewidth=1)
    if raw["off"].sum() > 0:
        a.barh(y, raw["off"], left=raw["on"], color=LIGHT, hatch="////", height=0.62,
               edgecolor=SURFACE, linewidth=1)
    pad = raw["total"].max() * 0.015
    for yi, (tot, w) in enumerate(zip(raw["total"], why)):
        a.text(tot + pad, yi, f"{tot:.0f} h" + (f"  ·  {w}" if w else ""), va="center", fontsize=8, color=INK2)
    a.set_yticks(y, raw.index)
    a.set_xlim(0, raw["total"].max() * 1.55)
    a.set_title(f"Sin limpiar: TAP en los {df['fecha'].nunique()} {unit}")

    yb = np.arange(len(cleaned))
    b.barh(yb, cleaned["tap_h"], color=TAP_C, height=0.62)
    pad = cleaned["tap_h"].max() * 0.015
    for yi, (v, dp) in enumerate(zip(cleaned["tap_h"], cleaned["dp"])):
        b.text(v + pad, yi, f"{v:.0f} h  ·  Dp {fmt(dp)} %", va="center", fontsize=8, color=INK2)
    b.set_yticks(yb, cleaned.index)
    b.set_xlim(0, cleaned["tap_h"].max() * 1.6)
    n_prod = df.loc[~df["no_productivo"], "fecha"].nunique()
    b.set_title(f"Limpio: TAP en {n_prod} {unit}, flujo principal")

    for ax in (a, b):
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
        ax.set_xlabel("horas de parada propia")
    handles = [Patch(facecolor=TAP_C, label="parada propia"),
               Patch(facecolor=AXIS, label="excluida del ranking")]
    if raw["off"].sum() > 0:
        handles.append(Patch(facecolor=LIGHT, hatch="////", edgecolor=AXIS, label=f"{unit} sin producción"))
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), bbox_to_anchor=(0.5, -0.08))
    return _save(fig, path)


def losses(totals: pd.DataFrame, path: Path) -> Path:
    """Horas perdidas por estacion, separadas en TAP, DES y SAT, en el orden de la linea."""
    t = totals[totals["en_ranking"]].sort_values("Orden_OP")
    x = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(_wide(len(t)), 4.6))
    bottom = np.zeros(len(t))
    for col, color, label in [("tap_h", TAP_C, "parada propia (TAP)"),
                              ("des_h", DES_C, "sin piezas de la anterior (DES)"),
                              ("sat_h", SAT_C, "bloqueada por la siguiente (SAT)")]:
        ax.bar(x, t[col], bottom=bottom, color=color, width=0.72, edgecolor=SURFACE, linewidth=0.6, label=label)
        bottom += t[col].to_numpy()
    for i in np.argsort(bottom)[-5:]:
        ax.text(x[i], bottom[i] + bottom.max() * 0.012, f"{bottom[i]:.0f}", ha="center", fontsize=7.5, color=INK2)
    _station_axis(ax, t.index, len(t))
    ax.set_ylim(0, bottom.max() * 1.08)
    ax.set_ylabel("horas perdidas")
    ax.set_title("Horas perdidas por estación, en el orden de la línea", pad=28)
    _legend_above(ax, ncol=3)
    return _save(fig, path)


def dp_fpm(totals: pd.DataFrame, s: LineSettings, path: Path) -> Path:
    """Disponibilidad frente a frecuencia de parada propia."""
    t = totals[totals["en_ranking"]].dropna(subset=["dp", "fpm"]).copy()
    t["fpm_plot"] = t["fpm"].clip(lower=0.05)
    low = t["dp"] < s.dp_target
    freq = t["fpm"].rank(ascending=False) <= 4
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axvline(s.dp_target, color=INK2, linestyle=DASH, linewidth=1, label=f"objetivo {num(s.dp_target)} %")
    ax.scatter(t.loc[~low, "dp"], t.loc[~low, "fpm_plot"], s=20, color=AXIS, edgecolor=SURFACE,
               linewidth=0.8, zorder=2, label="cumple")
    ax.scatter(t.loc[low, "dp"], t.loc[low, "fpm_plot"], s=46, color=TAP_C, edgecolor=SURFACE,
               linewidth=1.2, zorder=3, label="por debajo del objetivo")
    ax.set_yscale("log")
    ax.set_xlabel("disponibilidad Dp (%)")
    ax.set_ylabel("paradas propias cada 1.000 piezas (Fpm, escala log)")
    ax.yaxis.grid(True, which="major")
    ax.set_axisbelow(True)
    ax.set_title("Disponibilidad frente a frecuencia de parada", pad=28)
    _legend_above(ax, ncol=3)
    lab = t[low | freq]
    _labels(ax, lab["dp"].to_numpy(), lab["fpm_plot"].to_numpy(), list(lab.index),
            [INK if low[op] else INK2 for op in lab.index])
    return _save(fig, path)


def cycle_time(tcy: pd.DataFrame, s: LineSettings, path: Path) -> Path:
    """Tcy corregido (y sin corregir donde cambia) frente al objetivo."""
    t = tcy
    x = np.arange(len(t))
    over = t["sobre_objetivo"].to_numpy()
    moved = ((t["tcy_raw"] - t["tcy"]).abs() > 1).to_numpy()
    fig, ax = plt.subplots(figsize=(_wide(len(t)), 4.4))
    ax.axhline(s.tcy_target, color=INK2, linestyle=DASH, linewidth=1, label=f"objetivo {num(s.tcy_target)} cmin")
    if moved.any():
        ax.vlines(x[moved], t["tcy"][moved], t["tcy_raw"][moved], color=AXIS, linewidth=1, zorder=1)
        ax.scatter(x[moved], t["tcy_raw"][moved], s=22, facecolor=SURFACE, edgecolor=MUTED, linewidth=1,
                   zorder=2, label="sin corregir")
    ax.scatter(x[~over], t["tcy"][~over], s=22, color=AXIS, zorder=3, label="corregido")
    if over.any():
        ax.scatter(x[over], t["tcy"][over], s=40, color=INK, zorder=4, label="corregido, sobre objetivo")
    _station_axis(ax, t.index, len(t))
    ax.set_ylabel("tiempo de ciclo (cmin)")
    ax.set_title("Tiempo de ciclo por estación", pad=28)
    _legend_above(ax, ncol=4)
    idx = np.flatnonzero(over)
    if len(idx):
        _labels(ax, x[idx], t["tcy"].to_numpy()[idx],
                [f"{t.index[i]}  {fmt(t['tcy'].iloc[i])}" for i in idx], [INK] * len(idx))
    return _save(fig, path)


def who_brakes(arrows: pd.Series, n_periods: int, unit: str, strong_at: int, path: Path) -> Path:
    """Periodos en que cada estacion cumple la regla de las flechas."""
    x = np.arange(len(arrows))
    strong = (arrows >= strong_at).to_numpy()
    fig, ax = plt.subplots(figsize=(_wide(len(arrows)), 4))
    ax.bar(x[~strong], arrows[~strong], color=AXIS, width=0.72)
    ax.bar(x[strong], arrows[strong], color=INK, width=0.72)
    for i in np.flatnonzero(strong):
        ax.text(x[i], arrows.iloc[i] + 0.02 * n_periods, arrows.index[i], ha="center", va="bottom",
                fontsize=7.5, color=INK, rotation=90)
    _station_axis(ax, arrows.index, len(arrows))
    ax.set_ylim(0, n_periods * 1.35)
    ax.set_yticks(np.unique(np.linspace(0, n_periods, 5).round().astype(int)))
    ax.set_ylabel(f"{unit} que frena la línea (de {n_periods})")
    ax.set_title(f"Regla de las flechas: {unit} en que cada estación frena a sus vecinas")
    return _save(fig, path)
