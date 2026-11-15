"""Genera frontend/public/mock/line_state.mock.json a partir de los datos reales limpios.

Es el mock con el que arranca el Rol 3 hasta que la API real (Rol 1) sirva
line_state.json. Reutiliza el pipeline del EDA (ingest -> clean -> kpis), asi que
los numeros son los de verdad. Lo que todavia no existe se marca como provisional:

- status, penalty, explanation y ranking: de la logica de paradas (backend/logic, data/processed/logic/
  logic_state.json) si esta generada; si no, una regla provisional de este script.
- forecast: banda p10-p90 de TimesFM a un dia vista (forecast/output/<linea>/backtest_predicciones.csv)
  si existe; si no, cuantiles historicos de prueba.
- alerts: reglas provisionales de este script. Las sustituye la deteccion de anomalias (Rol 4).
- topology y kind: hipotesis deducida de los datos (scripts/topology.py) y de line_hints.json.
  El config solo trae el orden; lo confirma la planta o lo sirve Rol 1.

Uso, desde la raiz del repo:
    .venv/bin/python frontend/scripts/build_mock.py [--line VLL_MONTAJE_L5]
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import topology  # noqa: E402

from backend.pipeline import clean, ingest, kpis  # noqa: E402
from backend.pipeline.settings import load_settings  # noqa: E402


def es1(x: float) -> str:
    """Un decimal con coma, como se escribe en castellano: 11.6 -> '11,6'."""
    return f"{x:.1f}".replace(".", ",")


OUT = ROOT / "frontend" / "public" / "mock" / "line_state.mock.json"
LOGIC = ROOT / "data" / "processed" / "logic" / "logic_state.json"  # logica de paradas (backend/logic)
FORECAST = ROOT / "forecast" / "output"  # prediccion: backtest_predicciones.csv
# Estados oficiales de la logica -> estados del contrato del dashboard.
LOGIC_STATUS = {"parada_propia": "propia", "desabastecimiento": "inducida_anterior", "saturacion": "inducida_siguiente",
                "lenta": "ok", "ok": "ok", "dato_no_fiable": "dato_no_fiable", "fuera_servicio": "fuera_servicio"}
HINTS = Path(__file__).with_name("line_hints.json")

# Umbral provisional para "ok": ninguna perdida supera esta fraccion del tiempo requerido.
LOSS_SHARE_OK = 0.10
FORECAST_HORIZON = 5  # ultimos dias productivos que se "predicen" en el mock
# Avisos provisionales: horas a partir de las que un dia merece aviso.
ALERT_BLOCK_H = (3.0, 6.0)  # horas que hace perder a sus vecinas: aviso, critica
ALERT_OWN_H = (1.5, 3.0)  # horas de parada propia: aviso, critica
ALERT_BAND_H = 0.3  # horas por encima de p90 para avisar de un dia fuera de banda


def r(x, nd=1):
    """Redondeo seguro para JSON: NaN/inf -> None."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), nd)


def day_status(row, s, threshold_h: float) -> str:
    """Regla provisional (Rol 2 la sustituye): orden fuera_servicio > dato_no_fiable > propia por Dp > perdida mayor."""
    if row["fuera_servicio"]:
        return "fuera_servicio"
    if row["sin_datos"] or row["sensor_sospechoso"]:
        return "dato_no_fiable"
    own = row["tbf_h"] + row["tap_h"]
    dp = 100 * row["tbf_h"] / own if own > 0 else np.nan
    if np.isfinite(dp) and dp < s.dp_target:
        return "propia"
    losses = {"propia": row["tap_h"], "inducida_anterior": row["des_h"], "inducida_siguiente": row["sat_h"]}
    worst = max(losses, key=losses.get)
    return "ok" if losses[worst] <= threshold_h else worst


def day_flags(row) -> list[str]:
    names = ["fuera_servicio", "sin_datos", "sensor_sospechoso", "contador_roto", "contador_doble", "tr_mayor", "tr_menor"]
    return [n for n in names if bool(row[n])]


def arrows_by_day(df: pd.DataFrame) -> dict[tuple[str, str], dict]:
    """Regla de las flechas dia a dia (misma logica que kpis.arrow_days) con las horas que hace perder."""
    nodes = kpis.chain(df)
    out: dict[tuple[str, str], dict] = {}
    for fecha, period in nodes.sort_values("Orden_OP").groupby("fecha"):
        ops = period["Operacion"].to_numpy()
        des, sat = period["des_h"].to_numpy(), period["sat_h"].to_numpy()
        for i in range(1, len(ops) - 1):
            if sat[i - 1] > des[i] and des[i + 1] > sat[i]:
                out[(ops[i], fecha.strftime("%Y-%m-%d"))] = {
                    "prev": ops[i - 1], "next": ops[i + 1],
                    "prev_sat_h": float(sat[i - 1]), "next_des_h": float(des[i + 1]),
                }
    return out


def kind_of(op: str, grupo: str, hints: dict) -> str | None:
    """Tipo de puesto para el dibujo. Hipotesis configurable: patrones de line_hints.json."""
    if grupo == "fuera_flujo":
        return "manipulator"
    for rule in hints.get("kinds", []):
        if re.search(rule["pattern"], op):
            return rule["kind"]
    return None


def explanation(st: dict, n_days: int, target: float) -> str:
    """Frase por plantilla, sin LLM (provisional; la definitiva es de Rol 2)."""
    op, k, p = st["op"], st["kpi"], st["penalty"]
    if st["status"] == "fuera_servicio":
        return f"{op} no produce ningún día: TBF = 0 y toda la jornada como parada propia. Fuera de servicio o by-pass, fuera del ranking."
    if st["status"] == "dato_no_fiable":
        why = {
            "sensor_sospechoso": "registra más paradas propias que piezas (NAP > NPR)",
            "sin_datos": "no registra ningún tiempo",
            "contador_roto": "su contador de piezas no cuenta",
        }
        reason = next((why[f] for f in st["flags"] if f in why), "sus datos no cuadran")
        return f"Dato no fiable: {op} {reason}. Se marca como falsa alarma candidata y queda fuera del ranking."
    parts = [f"{op} pierde {k['tap_h']:.0f} h propias en {n_days} días (Dp {k['dp']:.0f} %, objetivo {target:.0f} %)."]
    if k.get("fpm") and k.get("s_per_stop"):
        kind = "son microparadas, no averías largas" if k["s_per_stop"] < 60 else "son paradas largas"
        parts.append(f"Se para {k['fpm']:.0f} veces cada 1.000 piezas, unos {k['s_per_stop']:.0f} s cada vez: {kind}.")
    if p["blocking_days"]:
        parts.append(f"Frena la línea {p['blocking_days']} de {n_days} días y hace perder {p['induced_on_neighbours_h']:.0f} h a sus vecinas.")
    elif k["des_h"] > k["sat_h"] and k["des_h"] > k["tap_h"]:
        parts.append(f"Su mayor pérdida es esperar piezas ({k['des_h']:.0f} h): la frena la estación anterior.")
    elif k["sat_h"] > k["tap_h"]:
        parts.append(f"Su mayor pérdida es estar bloqueada ({k['sat_h']:.0f} h): la frena la estación siguiente.")
    return " ".join(parts)


def build_alerts(stations: list[dict]) -> list[dict]:
    """Avisos por estacion y dia (provisional): frena la linea, parada propia, fuera de banda y dato dudoso."""
    out = []
    for x in stations:
        op = x["op"]
        if x["status"] in ("fuera_servicio", "dato_no_fiable"):
            title = "Fuera de servicio" if x["status"] == "fuera_servicio" else "Dato no fiable"
            out.append({"id": f"dato|{op}", "day": None, "op": op, "severity": "info", "type": "dato",
                        "title": f"{op}: {title.lower()}", "detail": x["explanation"], "hours": None})
            continue
        if not x["in_ranking"]:
            continue
        fc = x["forecast"] or {}
        p90 = dict(zip(fc.get("days", []), fc.get("p90", []))) if fc.get("metric") == "tap_h" else {}
        for d in x["daily"]:
            day, tap = d["day"], d["tap"] or 0.0
            if d["blocks_line"] and d["induced_h"] >= ALERT_BLOCK_H[0]:
                out.append({
                    "id": f"frena|{op}|{day}", "day": day, "op": op, "type": "frena_linea",
                    "severity": "critica" if d["induced_h"] >= ALERT_BLOCK_H[1] else "aviso",
                    "title": f"{op} frena la línea",
                    "detail": f"Sus vecinas pierden {es1(d['induced_h'])} h esperándola: la de atrás se bloquea y la de delante se queda sin piezas.",
                    "hours": d["induced_h"],
                })
            if tap >= ALERT_OWN_H[0] and (tap >= ALERT_OWN_H[1] or d["status"] == "propia"):
                secs = 3600 * tap / d["nap"] if d["nap"] else None
                how = "" if secs is None else f" en {d['nap']} paradas de unos {secs:.0f} s" if secs < 60 else f" en {d['nap']} paradas de unos {secs / 60:.0f} min"
                out.append({
                    "id": f"propia|{op}|{day}", "day": day, "op": op, "type": "parada_propia",
                    "severity": "critica" if tap >= ALERT_OWN_H[1] else "aviso",
                    "title": f"{op} se para mucho",
                    "detail": f"{es1(tap)} h parada por sí misma{how}.",
                    "hours": tap,
                })
            elif day in p90 and p90[day] is not None and tap - p90[day] >= ALERT_BAND_H:
                out.append({
                    "id": f"banda|{op}|{day}", "day": day, "op": op, "type": "prediccion", "severity": "aviso",
                    "title": f"{op} se para más de lo normal",
                    "detail": f"{es1(tap)} h de parada propia; lo esperado para ese día era como mucho {es1(p90[day])} h.",
                    "hours": tap,
                })
    return out


def apply_logic(stations: list[dict], line: str) -> list[str] | None:
    """Estado, frase, penalizacion y ranking de la logica de paradas (Rol 2), si esta generada."""
    if not LOGIC.exists():
        return None
    data = json.loads(LOGIC.read_text(encoding="utf-8"))
    found = [ln for p in data["plants"] for ln in p["lines"] if ln["id"] == line]
    if not found:
        return None
    ln = found[0]
    by_op = {x["op"]: x for x in ln["stations"]}
    for x in stations:
        lx = by_op.get(x["op"])
        if not lx:
            continue
        x["status"] = LOGIC_STATUS.get(lx["status"], x["status"])
        x["explanation"] = lx.get("explanation") or x["explanation"]
        days = {d["day"]: d for d in lx.get("daily", [])}
        for d in x["daily"]:
            if d["day"] in days:
                d["status"] = LOGIC_STATUS.get(days[d["day"]]["status"], d["status"])
    ranking = [op for op in ln.get("ranking", {}).get("penalizacion", []) if any(x["op"] == op for x in stations)]
    for i, op in enumerate(ranking, 1):
        next(x for x in stations if x["op"] == op)["penalty"]["rank"] = i
    return ranking


def apply_forecast(stations: list[dict], line: str) -> bool:
    """Banda p10-p90 de TimesFM a un dia vista (backtest del Rol 4) para la parada propia."""
    path = FORECAST / line / "backtest_predicciones.csv"
    if not path.exists():
        return False
    pr = pd.read_csv(path)
    pr = pr[(pr["escenario"] == "dia") & (pr["modelo"] == "timesfm") & (pr["metrica"] == "tap_h")]
    if pr.empty:
        return False
    for x in stations:
        g = pr[pr["serie"] == x["op"]].sort_values("fecha")
        if g.empty:
            continue
        x["forecast"] = {
            "metric": "tap_h", "model": "TimesFM 3.0 (a un día vista)",
            "context_days": [d["day"] for d in x["daily"] if d["day"] < g["fecha"].iloc[0]],
            "days": g["fecha"].tolist(),
            **{q: [r(v, 2) for v in g[q]] for q in ["p10", "p50", "p90"]},
        }
    return True


def build(line: str) -> dict:
    raw = ingest.load()
    raw = raw[raw["Linea"] == line]
    s = load_settings(line, raw)
    df = clean.clean(raw, s)
    hints = json.loads(HINTS.read_text(encoding="utf-8")).get(line, {}) if HINTS.exists() else {}

    prod = df[~df["no_productivo"]].copy()
    topo = topology.infer(prod, hints.get("topology"))
    branch_of = topo.pop("branch_of")
    days = sorted(prod["fecha"].dt.strftime("%Y-%m-%d").unique())
    excluded = sorted(df.loc[df["no_productivo"], "fecha"].dt.strftime("%Y-%m-%d").unique())
    n_days = len(days)
    thr_day = LOSS_SHARE_OK * s.required_h

    totals = kpis.station_totals(df)
    tcy = kpis.cycle_times(df, s)["tcy"]
    arrows = arrows_by_day(df)
    flag_share = clean.station_flags(df)
    parallel = df.groupby("Operacion")["paralelo"].first()

    stations = []
    for op, rows in prod.sort_values("fecha").groupby("Operacion", sort=False):
        first = rows.iloc[0]
        node = parallel.get(op) if isinstance(parallel.get(op), str) else op
        partners = [x for x in node.split("+") if x != op] if node != op else []

        daily = []
        for _, row in rows.iterrows():
            day = row["fecha"].strftime("%Y-%m-%d")
            arrow = arrows.get((node, day))
            own = row["tbf_h"] + row["tap_h"]
            daily.append({
                "day": day, "tbf": r(row["tbf_h"], 2), "tap": r(row["tap_h"], 2), "des": r(row["des_h"], 2),
                "sat": r(row["sat_h"], 2), "npr": int(row["NPR"]), "npr_ef": int(round(row["npr_ef"])), "nap": int(row["NAP"]),
                "dp": r(100 * row["tbf_h"] / own if own else np.nan),
                "status": day_status(row, s, thr_day), "flags": day_flags(row),
                "blocks_line": arrow is not None,
                "induced_h": r(arrow["prev_sat_h"] + arrow["next_des_h"], 2) if arrow else 0.0,
            })

        shares = flag_share.loc[op] if op in flag_share.index else pd.Series(dtype=float)
        st_flags = [f for f, v in shares.items() if v >= s.station_share]
        t = totals.loc[op] if op in totals.index else None
        kpi = {
            "dp": r(t["dp"]) if t is not None else None,
            "tcy": r(tcy.get(node, np.nan)) if node in tcy.index else None,
            "fpm": r(t["fpm"], 0) if t is not None else None,
            "tbf_h": r(t["tbf_h"]) if t is not None else 0.0,
            "tap_h": r(t["tap_h"]) if t is not None else r(rows["tap_h"].sum()),
            "des_h": r(t["des_h"]) if t is not None else r(rows["des_h"].sum()),
            "sat_h": r(t["sat_h"]) if t is not None else r(rows["sat_h"].sum()),
            "s_per_stop": r(t["s_por_parada"], 0) if t is not None else None,
        }

        if "fuera_servicio" in st_flags:
            status = "fuera_servicio"
        elif "sensor_sospechoso" in st_flags or "sin_datos" in st_flags or bool(first["estacion_excluida"]) and first["grupo"] == "linea":
            status = "dato_no_fiable"
        else:
            fake = pd.Series({**{f: False for f in ["fuera_servicio", "sin_datos", "sensor_sospechoso"]},
                              "tbf_h": kpi["tbf_h"] or 0, "tap_h": kpi["tap_h"] or 0,
                              "des_h": kpi["des_h"] or 0, "sat_h": kpi["sat_h"] or 0})
            status = day_status(fake, s, thr_day * n_days)

        blocking = [d for d in daily if d["blocks_line"]]
        stations.append({
            "op": op, "order": int(first["Orden_OP"]),
            "group": "manipulator" if first["grupo"] == "fuera_flujo" else "subassembly" if op in branch_of else "main",
            "parallel_with": partners[0] if partners else None,
            "branch": branch_of.get(op),
            "kind": kind_of(op, first["grupo"], hints),
            "kpi": kpi, "status": status, "flags": st_flags,
            "in_ranking": bool(first["en_ranking"]),
            "penalty": {
                "rank": None, "own_h": kpi["tap_h"] or 0.0,
                "induced_on_neighbours_h": r(sum(d["induced_h"] for d in blocking)),
                "blocking_days": len(blocking),
                "blocked_neighbours": sorted({a for d in blocking for a in [arrows[(node, d["day"])]["prev"], arrows[(node, d["day"])]["next"]]}),
            },
            "explanation": "",
            "daily": daily,
            "forecast": None,
        })

    # Ranking provisional: horas propias + horas que hace perder a sus vecinas los dias que frena la linea.
    ranked = [x for x in stations if x["in_ranking"] and x["status"] not in ("fuera_servicio", "dato_no_fiable")]
    seen_nodes, ranking = set(), []
    for x in sorted(ranked, key=lambda x: -(x["penalty"]["own_h"] + x["penalty"]["induced_on_neighbours_h"])):
        node = "+".join(sorted([x["op"], x["parallel_with"]])) if x["parallel_with"] else x["op"]
        if node in seen_nodes:
            continue
        seen_nodes.add(node)
        ranking.append(x["op"])
    for i, op in enumerate(ranking, 1):
        next(x for x in stations if x["op"] == op)["penalty"]["rank"] = i
    ranking_own = [x["op"] for x in sorted(ranked, key=lambda x: -x["kpi"]["tap_h"])]

    # Banda de prediccion de prueba: cuantiles del contexto (todos menos los ultimos 5 dias).
    ctx_days, fc_days = days[:-FORECAST_HORIZON], days[-FORECAST_HORIZON:]
    for x in stations:
        if x["status"] in ("fuera_servicio", "dato_no_fiable"):
            continue
        hist = [d["tap"] for d in x["daily"] if d["day"] in ctx_days and d["tap"] is not None]
        if len(hist) < 5:
            continue
        q10, q50, q90 = np.quantile(hist, [0.1, 0.5, 0.9])
        x["forecast"] = {
            "metric": "tap_h", "model": "mock-cuantiles-historicos",
            "context_days": ctx_days, "days": fc_days,
            "p10": [r(q10, 2)] * len(fc_days), "p50": [r(q50, 2)] * len(fc_days), "p90": [r(q90, 2)] * len(fc_days),
        }

    for x in stations:
        x["explanation"] = explanation(x, n_days, s.dp_target)

    # Lo que ya entregan los demas roles sustituye a lo provisional de este script.
    provisional = ["status", "penalty", "explanation", "forecast", "topology", "kind", "alerts"]
    logic_ranking = apply_logic(stations, line)
    if logic_ranking:
        ranking = logic_ranking
        provisional = [f for f in provisional if f not in ("status", "penalty", "explanation")]
    if apply_forecast(stations, line):
        provisional.remove("forecast")

    quality = clean.quality_table(df, s)
    return {
        "meta": {
            "line": line, "required_h": s.required_h,
            "targets": {"tcy_cmin": s.tcy_target, "dp_pct": s.dp_target},
            "days": days, "excluded_days": excluded,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "mock",
            "provisional": provisional,
        },
        "stations": sorted(stations, key=lambda x: x["order"]),
        "ranking": ranking,
        "ranking_own": ranking_own,
        "quality": quality.to_dict(orient="records"),
        "topology": topo,
        "alerts": build_alerts(stations),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--line", default="VLL_MONTAJE_L5")
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    state = build(args.line)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    st = state["stations"]
    print(f"{args.out.relative_to(ROOT)}: {len(st)} estaciones, {len(state['meta']['days'])} días")
    print("ranking (penalización):", state["ranking"][:5])
    print("ranking (parada propia):", state["ranking_own"][:5])
    print("estados:", pd.Series([x["status"] for x in st]).value_counts().to_dict())
    alerts = pd.DataFrame(state["alerts"])
    print("avisos:", alerts.groupby(["type", "severity"]).size().to_dict(), "· por día:", round(alerts["day"].notna().sum() / len(state["meta"]["days"]), 1))
    print("hipótesis de topología:")
    for n in state["topology"]["notes"]:
        print(f"  [{n['confidence']}] {n['title']}: {n['detail']}")


if __name__ == "__main__":
    main()
