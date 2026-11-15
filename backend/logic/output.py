"""Salida jerárquica para el dashboard: plantas → líneas → máquinas → sensores.

Solo tipos de JSON (dict, list, str, int, float, bool, None). Horas y cmin con
un decimal; Dp y cuotas en porcentaje.
"""

import pandas as pd

from . import schema as s
from .penalty import rankings
from .status import STATUS_INFO, STATUSES

SCHEMA_VERSION = 2  # 2: nombres oficiales de estado y su etiqueta para la leyenda


def _r(x, decimals: int = 1):
    if x is None or pd.isna(x):
        return None
    return round(float(x), decimals)


def _pct(share):
    return None if share is None or pd.isna(share) else _r(100 * share)


def _str(x):
    return None if x is None or pd.isna(x) else str(x)


def _kpi(row: pd.Series) -> dict:
    return {
        "dp": _pct(row["dp"]),
        "tcy": _r(row["tcy_cmin"]),
        "tcy_machine": _r(row["tcy_machine_cmin"]),
        "fpm": _r(row["fpm"]),
        "s_per_stop": _r(row["s_per_stop"]),
        "tr_h": _r(row["TR"]),
        "tbf_h": _r(row[s.TBF]),
        "tap_h": _r(row[s.TAP]),
        "des_h": _r(row[s.DES]),
        "sat_h": _r(row[s.SAT]),
        "tai_h": _r(row["TAI"]),
        "nap": int(row[s.NAP]),
        "npr": int(row[s.NPR]),
    }


def _day(row: pd.Series) -> dict:
    return {
        "day": row[s.DAY],
        "status": row["status"],
        "is_bottleneck": bool(row["is_bottleneck"]),
        "severity_pct": _pct(row["severity"]),
        "flags": list(row[s.FLAGS]),
        **_kpi(row),
    }


def _station(row: pd.Series, daily: pd.DataFrame) -> dict:
    rank = row["rank"]
    parallel = _str(row[s.PARALLEL])
    return {
        "op": row[s.OP],
        "order": int(row[s.ORDER]),
        "group": row[s.GROUP],
        "segment": row[s.SEGMENT],
        "parallel_with": [op for op in parallel.split("+") if op != row[s.OP]] if parallel else None,
        "status": row["status"],
        "flags": list(row["flags_all"]),
        "kpi": _kpi(row),
        "penalty": {
            "rank": None if pd.isna(rank) else int(rank),
            "index_h": _r(row["penalty_h"]),
            "own_h": _r(row[s.TAP]),
            "induced_on_neighbours_h": _r(row["induced_on_neighbours_h"]),
            "induced_on_prev_h": _r(row["induced_on_prev_h"]),
            "induced_on_next_h": _r(row["induced_on_next_h"]),
            "bottleneck_days": int(row["bottleneck_days"]),
            "valid_days": int(row["valid_days"]),
            "excluded_days": int(row["excluded_days"]),
            "brakes_line_in_total": bool(row["brakes_line_in_total"]),
            "severity_total_pct": _pct(row["severity_total"]),
        },
        "explanation": row["explanation"],
        "daily": [_day(d) for _, d in daily.sort_values(s.DAY).iterrows()],
        "sensors": [],  # sin datos de sensores todavía; aquí colgarían
    }


def _arrows(arrows: pd.DataFrame) -> list[dict]:
    return [
        {
            "segment": a[s.SEGMENT],
            "from": a["from"],
            "to": a["to"],
            "direction": a["direction"],
            "points_to": _str(a["points_to"]),
            "sat_pct_from": _pct(a["sat_share_from"]),
            "des_pct_to": _pct(a["des_share_to"]),
        }
        for _, a in arrows.iterrows()
    ]


def to_dashboard(analysis) -> dict:
    daily_by_op = {k: g for k, g in analysis.daily.groupby([s.LINE, s.OP])}
    arrows_daily = {k: g for k, g in analysis.arrows_daily.groupby(s.LINE)}
    arrows_total = {k: g for k, g in analysis.arrows_total.groupby(s.LINE)}
    ranks = rankings(analysis.totals, analysis.config.main_group)
    no_arrows = analysis.arrows_daily.iloc[0:0]

    plants = []
    for plant, tp in analysis.totals.groupby(s.PLANT, sort=True):
        lines = []
        for line, tl in tp.groupby(s.LINE, sort=True):
            t = analysis.config.targets(line)
            line_arrows = arrows_daily.get(line, no_arrows)
            days = sorted(analysis.daily.loc[analysis.daily[s.LINE] == line, s.DAY].unique())
            lines.append(
                {
                    "id": line,
                    "targets": {
                        "required_h": t.required_h,
                        "dp_pct": _pct(t.dp_min),
                        "tcy_cmin": t.tcy_max_cmin,
                        "tai_pct": _pct(t.tai_max),
                    },
                    "days": days,
                    "stations": [
                        _station(row, daily_by_op[(line, row[s.OP])])
                        for _, row in tl.sort_values([s.ORDER, s.OP]).iterrows()
                    ],
                    "arrows": {
                        "total": _arrows(arrows_total.get(line, no_arrows)),
                        "daily": {
                            day: _arrows(line_arrows[line_arrows[s.DAY] == day]) for day in days
                        },
                    },
                    "ranking": ranks.get(line, {"penalizacion": [], "se_para_mas": [], "frena_linea": []}),
                }
            )
        plants.append({"id": plant, "lines": lines})
    statuses = [{"id": st, "label": STATUS_INFO[st][0], "family": STATUS_INFO[st][1]} for st in STATUSES]
    return {"schema_version": SCHEMA_VERSION, "statuses": statuses, "plants": plants}
