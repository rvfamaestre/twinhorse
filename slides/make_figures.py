"""Figuras de la presentacion, con los datos reales del repo. Desde la raiz:

    python slides/make_figures.py

Escribe figures/slides/*.png (300 ppp) y *.pdf (vectorial). Estetica minimalista: fondo blanco,
texto casi negro, sin marcos ni rejilla, y color solo para los estados (mismos que el dashboard).
Las figuras no llevan titulo: el titulo va en la diapositiva (ver slides/README.md).
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LINE = "VLL_MONTAJE_L5"
PROC = ROOT / "data" / "processed" / LINE
OUT = ROOT / "figures" / "slides"

INK, INK2, MUTED, RULE, LIGHT = "#111111", "#3c4043", "#8a8f98", "#d9dbdf", "#eef0f2"
OWN, STARVED, BLOCKED, OK, OFF = "#e5484d", "#f0a530", "#3e8bf0", "#30a46c", "#b8bcc2"

plt.rcParams.update({
    "font.family": ["Inter", "Helvetica Neue", "Segoe UI", "Arial", "DejaVu Sans"],
    "font.size": 13, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False, "axes.spines.bottom": False,
    "axes.grid": False, "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False,
})


def es(x: float, d: int = 0) -> str:
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print("  ", name)


def logic() -> dict:
    data = json.loads((ROOT / "data/processed/logic/logic_state.json").read_text(encoding="utf-8"))
    return next(ln for p in data["plants"] for ln in p["lines"] if ln["id"] == LINE)


# 1 · La paradoja: la que mas se para no es la que mas penaliza ---------------------------------
def paradox(ln: dict) -> None:
    by = {s["op"]: s for s in ln["stations"]}
    own = ln["ranking"]["se_para_mas"][:6]
    pen = ln["ranking"]["penalizacion"][:6]
    fig, ax = plt.subplots(figsize=(12, 6.2))
    xl, xr = 0.0, 1.0
    for col, ops, key, x, ha in [("Se para más", own, "own_h", xl, "right"), ("Penaliza más a la línea", pen, "index_h", xr, "left")]:
        ax.text(x, 0.75, col.upper(), ha=ha, va="bottom", fontsize=12, color=MUTED, fontweight="bold")
        for i, op in enumerate(ops):
            y = -i
            hl = op in ("ST-2390", "ST-0260")
            h = by[op]["penalty"][key]
            label = f"{op}   {es(h)} h" if ha == "left" else f"{es(h)} h   {op}"
            ax.text(x + (-0.04 if ha == "right" else 0.04), y, label, ha=ha, va="center", fontsize=17,
                    color=INK if hl else INK2, fontweight="bold" if hl else "normal")
            ax.plot(x, y, "o", ms=9, color=INK if hl else RULE, zorder=3)
    for i, op in enumerate(own):
        if op in pen:
            j = pen.index(op)
            hl = op == "ST-2390"
            ax.plot([xl, xr], [-i, -j], color=OWN if hl else RULE, lw=3 if hl else 1.6, zorder=2, solid_capstyle="round")
    ax.text(0.5, -6.35, "Índice de penalización = horas de parada propia + horas que hace perder a sus vecinas.\n"
            "ST-2390 pierde 68 h por sí misma; ST-0260 solo 11 h, pero hace perder 175 h a las de al lado.",
            ha="center", va="top", fontsize=12.5, color=MUTED, linespacing=1.6)
    ax.set_xlim(-0.9, 1.9)
    ax.set_ylim(-7.1, 1.3)
    ax.axis("off")
    save(fig, "01_paradoja")


# 2 · Antes de limpiar, el ranking se lo llevan falsas alarmas ----------------------------------
def before_after(ln: dict) -> None:
    c = pd.read_csv(PROC / "clean.csv")
    raw = c.groupby("Operacion")["TAP"].sum().nlargest(5)
    why = {"PM2130": "fuera de servicio", "ST2235": "sensor que rebota", "ManBM2_1": "manipulador sin contador",
           "Ma_BM2_2": "manipulador", "MANOP749": "manipulador"}
    by = {s["op"]: s for s in ln["stations"]}
    clean = [(op, by[op]["penalty"]["own_h"]) for op in ln["ranking"]["se_para_mas"][:5]]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"wspace": 0.55})
    top = max(raw.max(), max(h for _, h in clean))
    for ax, rows, color, head in [
        (axes[0], list(raw.items()), RULE, "DATO EN BRUTO"),
        (axes[1], clean, OWN, "TRAS LIMPIAR"),
    ]:
        y = np.arange(len(rows))[::-1]
        ax.barh(y, [h for _, h in rows], color=color, height=0.56)
        ax.set_yticks(y, [op for op, _ in rows], fontsize=14)
        for yi, (op, h) in zip(y, rows):
            txt = f"{es(h)} h" + (f"  ·  {why[op]}" if head == "DATO EN BRUTO" and op in why else "")
            ax.text(h + top * 0.02, yi, txt, va="center", fontsize=12, color=MUTED if head == "DATO EN BRUTO" else INK2)
        ax.set_xlim(0, top * 1.65)
        ax.set_xticks([])
        ax.set_title(head, loc="left", fontsize=12, color=MUTED, fontweight="bold", pad=14)
    save(fig, "02_antes_despues_limpieza")


# 3 · Lo inducido pesa cinco veces mas que lo propio --------------------------------------------
def losses() -> None:
    k = pd.read_csv(PROC / "station_kpis.csv")
    k = k[k["en_ranking"]]
    parts = [("Parada propia", k["tap_h"].sum(), OWN), ("Sin piezas", k["des_h"].sum(), STARVED), ("Bloqueada", k["sat_h"].sum(), BLOCKED)]
    total = sum(v for _, v, _ in parts)
    fig, ax = plt.subplots(figsize=(12, 2.9))
    x = 0
    for name, v, color in parts:
        ax.barh(0, v, left=x, color=color, height=0.42)
        ax.text(x, 0.36, name.upper(), fontsize=11.5, color=MUTED, fontweight="bold", va="bottom")
        ax.text(x, -0.36, f"{es(v)} h", fontsize=22, color=INK, va="top", fontweight="bold")
        x += v
    induced = parts[1][1] + parts[2][1]
    ax.annotate("", xy=(total, -0.95), xytext=(parts[0][1], -0.95), arrowprops={"arrowstyle": "-", "color": INK2, "lw": 1.2})
    ax.text((parts[0][1] + total) / 2, -1.02, f"Inducida: {es(induced / parts[0][1], 1)} veces la propia",
            ha="center", va="top", fontsize=13, color=INK2)
    ax.set_xlim(0, total)
    ax.set_ylim(-1.45, 0.75)
    ax.axis("off")
    save(fig, "03_inducida_vs_propia")


# 4 · Calidad del dato: cada regla, cuantas filas toca ------------------------------------------
def quality() -> None:
    q = pd.read_csv(PROC / "data_quality.csv")
    names = {
        "no_productivo": "Día sin producción", "sin_datos": "No registra nada", "fuera_servicio": "Fuera de servicio",
        "tr_mayor": "Registra más de 22 h", "tr_menor": "Le faltan horas", "sensor_sospechoso": "Más paradas que piezas",
        "contador_doble": "Cuenta piezas dos veces", "contador_roto": "Contador de piezas roto",
    }
    q = q.assign(name=q["regla"].map(names)).sort_values("filas")
    fig, ax = plt.subplots(figsize=(11, 4.8))
    y = np.arange(len(q))
    colors = [INK if r == "no_productivo" else MUTED for r in q["regla"]]
    ax.barh(y, q["filas"], color=colors, height=0.5)
    ax.set_yticks(y, q["name"], fontsize=13.5)
    for yi, (f, ops) in zip(y, zip(q["filas"], q["operaciones"])):
        ax.text(f + 6, yi, f"{es(f)} filas · {ops} estaciones", va="center", fontsize=11.5, color=INK2)
    ax.set_xlim(0, q["filas"].max() * 1.5)
    ax.set_xticks([])
    save(fig, "04_calidad_del_dato")


# 5 · Que le paso a cada estacion cada dia ------------------------------------------------------
def day_map() -> None:
    s = pd.read_csv(PROC / "stops.csv")
    s = s[s["bloque"] != "manipulador"]
    group = {"microparada": 0, "parada_larga": 0, "desabastecimiento": 1, "saturacion": 2, "ok": 3, "sensor": 4, "error_registro": 4}
    colors = [OWN, STARVED, BLOCKED, LIGHT, OFF]
    ops = s.groupby("op")["orden"].first().sort_values().index
    grid = s.pivot(index="fecha", columns="op", values="tipo").reindex(columns=ops).apply(lambda col: col.map(group))
    fig, ax = plt.subplots(figsize=(14, 3.6))
    from matplotlib.colors import ListedColormap
    ax.imshow(grid.to_numpy(dtype=float), aspect="auto", interpolation="none", cmap=ListedColormap(colors), vmin=-0.5, vmax=4.5)
    for j in range(len(ops)):
        ax.axvline(j + 0.5, color="white", lw=0.8)
    for i in range(len(grid)):
        ax.axhline(i + 0.5, color="white", lw=0.8)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel(f"{len(ops)} estaciones, en el orden de la línea  →", fontsize=12, color=MUTED, labelpad=10)
    ax.set_ylabel(f"{len(grid)} días", fontsize=12, color=MUTED, labelpad=10)
    for k, (name, color) in enumerate([("Parada propia", OWN), ("Sin piezas", STARVED), ("Bloqueada", BLOCKED), ("Sin pérdida relevante", LIGHT), ("Dato no fiable", OFF)]):
        ax.add_patch(plt.Rectangle((k * 15.5, -2.6), 1.6, 1.1, color=color, clip_on=False))
        ax.text(k * 15.5 + 2.4, -2.05, name, fontsize=11.5, color=INK2, va="center")
    save(fig, "05_mapa_estacion_dia")


# 6 · Prediccion: banda de normalidad, no pronostico --------------------------------------------
def benchmark() -> None:
    b = pd.read_csv(ROOT / "forecast" / "output" / LINE / "benchmark_metricas.csv")
    st = b[b["metrica"] != "npr"]
    cov = st.groupby("modelo")["cobertura"].mean()
    order = [("ultimo_valor", "Último valor"), ("media", "Media"), ("timesfm", "TimesFM"),
             ("timesfm_calendario", "TimesFM + calendario"), ("timesfm_vecinas", "TimesFM + vecinas")]
    fig, (a, c) = plt.subplots(1, 2, figsize=(13.5, 4.8), gridspec_kw={"wspace": 0.4, "width_ratios": [1.25, 1]})
    y = np.arange(len(order))[::-1]
    vals = [100 * cov[m] for m, _ in order]
    a.barh(y, vals, color=[INK if m == "timesfm" else RULE for m, _ in order], height=0.55)
    a.set_yticks(y, [n for _, n in order], fontsize=13.5)
    for yi, v in zip(y, vals):
        inside = v > 72
        a.text(v - 1.5 if inside else v + 1.2, yi, f"{es(v)} %", va="center", ha="right" if inside else "left",
               fontsize=13, color="white" if inside else INK2, fontweight="bold" if inside else "normal")
    a.axvline(80, color=OK, lw=1.6, ls=(0, (4, 3)))
    a.text(80, len(order) - 0.35, "ideal 80 %", color=OK, fontsize=11.5, ha="center")
    a.set_xlim(0, 100)
    a.set_xticks([])
    a.set_title("DÍAS REALES DENTRO DE LA BANDA P10–P90", loc="left", fontsize=11.5, color=MUTED, fontweight="bold", pad=16)

    t = b[(b["modelo"] == "timesfm") & (b["metrica"] == "tap_h") & (b["horizonte"] == 1)].sort_values("contexto")
    c.axhline(0, color=RULE, lw=1.2)
    c.plot(t["contexto"], 100 * t["mejora"], color=INK, lw=2.4, marker="o", ms=8)
    for x, v in zip(t["contexto"], 100 * t["mejora"]):
        c.text(x, v + (2.2 if v >= 0 else -2.2), f"{'+' if v > 0 else ''}{es(v)} %", ha="center", va="bottom" if v >= 0 else "top", fontsize=12.5)
    c.set_xticks(t["contexto"], [f"{x} días" for x in t["contexto"]], fontsize=12)
    c.set_yticks([])
    c.set_ylim(min(-22, 100 * t["mejora"].min() - 6), 14)
    c.text(t["contexto"].iloc[0] - 0.4, 1.5, "gana a la media", fontsize=11, color=MUTED)
    c.text(t["contexto"].iloc[0] - 0.4, -2.2, "pierde", fontsize=11, color=MUTED, va="top")
    c.set_title("TIMESFM FRENTE A LA MEDIA, SEGÚN LA HISTORIA", loc="left", fontsize=11.5, color=MUTED, fontweight="bold", pad=16)
    save(fig, "06_prediccion_banda")


# 7 · El indice de penalizacion, desglosado ------------------------------------------------------
def penalty(ln: dict) -> None:
    by = {s["op"]: s for s in ln["stations"]}
    ops = ln["ranking"]["penalizacion"][:6]
    fig, ax = plt.subplots(figsize=(12, 4.6))
    y = np.arange(len(ops))[::-1]
    for yi, op in zip(y, ops):
        p = by[op]["penalty"]
        x = 0
        for v, color in [(p["own_h"], OWN), (p["induced_on_prev_h"], BLOCKED), (p["induced_on_next_h"], STARVED)]:
            ax.barh(yi, v, left=x, color=color, height=0.56)
            x += v
        ax.text(x + 3, yi, f"{es(p['index_h'])} h", va="center", fontsize=14, color=INK, fontweight="bold")
    ax.set_yticks(y, ops, fontsize=14)
    ax.set_xticks([])
    top = max(by[o]["penalty"]["index_h"] for o in ops)
    ax.set_xlim(0, top * 1.18)
    for k, (name, color) in enumerate([("Su parada propia", OWN), ("La anterior, bloqueada por ella", BLOCKED), ("La siguiente, sin piezas por ella", STARVED)]):
        ax.add_patch(plt.Rectangle((k * top * 0.38, len(ops) - 0.1), top * 0.022, 0.32, color=color, clip_on=False))
        ax.text(k * top * 0.38 + top * 0.035, len(ops) + 0.06, name, fontsize=11.5, color=INK2, va="center")
    save(fig, "07_indice_penalizacion")


def main() -> None:
    ln = logic()
    print("Figuras en", OUT)
    paradox(ln)
    before_after(ln)
    losses()
    quality()
    day_map()
    benchmark()
    penalty(ln)


if __name__ == "__main__":
    main()
