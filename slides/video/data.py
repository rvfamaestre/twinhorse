"""Junta en scenes/data.json los números reales que pintan los vídeos. Desde la raíz del repo:

    python slides/video/data.py

Lee lo que ya generan el pipeline, la lógica y el backtest; no calcula nada nuevo.
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LINE = "VLL_MONTAJE_L5"
OUT = Path(__file__).resolve().parent / "scenes" / "data.json"

# Ejemplo de la propagación (vídeo 3) y serie del aviso (vídeo 5)
FOCUS = "ST-0260"
ALERT_SERIES = "ST-2050"


def rankings(stations):
    ranked = [s for s in stations if (s.get("penalty") or {}).get("rank")]
    row = lambda s: {
        "op": s["op"],
        "own": s["penalty"]["own_h"],
        "prev": s["penalty"]["induced_on_prev_h"],
        "next": s["penalty"]["induced_on_next_h"],
        "index": s["penalty"]["index_h"],
    }
    own = sorted(ranked, key=lambda s: -s["kpi"]["tap_h"])[:6]
    pen = sorted(ranked, key=lambda s: s["penalty"]["rank"])[:6]
    return [row(s) for s in own], [row(s) for s in pen]


def neighbourhood(stations):
    i = next(k for k, s in enumerate(stations) if s["op"] == FOCUS)
    near = stations[i - 2 : i + 3]
    return [{"op": s["op"], "tap": s["kpi"]["tap_h"], "des": s["kpi"]["des_h"], "sat": s["kpi"]["sat_h"]} for s in near]


def quality_grid():
    """Rejilla operación × día y los niveles de la limpieza: qué filas salen y por qué."""
    c = pd.read_csv(ROOT / "data" / "processed" / LINE / "clean.csv")
    ops = c.drop_duplicates("Operacion").sort_values("Orden_OP")["Operacion"].tolist()
    days = sorted(c["fecha"].unique())

    # Niveles, en orden: cada uno quita filas de lo que deja el anterior
    dia = c["no_productivo"]
    man = ~dia & (c["grupo"] == "fuera_flujo")
    nofiable = ~dia & (c["grupo"] == "linea") & c["estacion_excluida"]
    kept = c["en_ranking"] & ~dia
    assert (dia | man | nofiable | kept).all() and len(c) - dia.sum() - man.sum() - nofiable.sum() == kept.sum()
    assert c.loc[kept, "valida"].all()
    # Lo que se queda, corregido: horas reescaladas y contador de la línea
    reloj = kept & c["tr_mayor"]
    contador = kept & c[["contador_roto", "contador_doble"]].any(axis=1)

    cat = pd.Series("ok", index=c.index)
    cat[reloj] = "reloj"
    cat[contador] = "contador"
    cat[reloj & contador] = "ambos"
    cat[nofiable] = "nofiable"
    cat[man] = "man"
    cat[dia] = "dia"
    idx = dict(zip(zip(c["fecha"], c["Operacion"]), cat))
    grid = [[idx[(d, op)] for op in ops] for d in days]

    # En un día sin producción la estación registra el día entero como parada y 0 piezas
    stop_h = c.loc[dia, "TAP"].round(1).unique()
    assert len(stop_h) == 1 and (c.loc[dia, "NPR"] == 0).all()
    return {
        "ops": ops,
        "days": days,
        "grid": grid,
        "stop_h": float(stop_h[0]),
        "levels": [
            {"key": "dia", "count": int(c.loc[dia, "fecha"].nunique()), "rows": int(dia.sum())},
            {"key": "man", "count": int(c.loc[man, "Operacion"].nunique()), "rows": int(man.sum())},
            {"key": "nofiable", "count": int(c.loc[nofiable, "Operacion"].nunique()), "rows": int(nofiable.sum()),
             "ops": sorted(c.loc[nofiable, "Operacion"].unique())},
        ],
        "kept": int(kept.sum()),
        "fixed": {"reloj": int(reloj.sum()), "contador": int(contador.sum())},
    }


def forecast_example():
    c = pd.read_csv(ROOT / "data" / "processed" / LINE / "clean.csv")
    h = c[(c["Operacion"] == ALERT_SERIES) & c["valida"]].sort_values("fecha")
    b = pd.read_csv(ROOT / "forecast" / "output" / LINE / "backtest_predicciones.csv")
    t = b[(b["modelo"] == "timesfm") & (b["escenario"] == "semana") & (b["metrica"] == "tap_h") & (b["serie"] == ALERT_SERIES)]
    t = t.sort_values("fecha")
    test_days = set(t["fecha"])
    qs = [f"p{q}" for q in range(10, 100, 10)]
    return {
        "op": ALERT_SERIES,
        "history": [{"day": r.fecha, "v": round(r.tap_h, 3)} for r in h.itertuples() if r.fecha not in test_days],
        "test": [{"day": r.fecha, "real": round(r.real, 3), "q": [round(max(getattr(r, q), 0.0), 3) for q in qs]} for r in t.itertuples()],
    }


def main():
    state = json.loads((ROOT / "data" / "processed" / "logic" / "logic_state.json").read_text(encoding="utf-8"))
    stations = state["plants"][0]["lines"][0]["stations"]
    own, pen = rankings(stations)
    data = {
        "own": own,
        "penalty": pen,
        "neighbourhood": neighbourhood(stations),
        "focus": FOCUS,
        "quality": quality_grid(),
        "forecast": forecast_example(),
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
