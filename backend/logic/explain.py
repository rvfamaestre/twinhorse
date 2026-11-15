"""Frase que explica cada máquina. Plantillas fijas, sin LLM: mismos datos, misma frase."""

import math

import pandas as pd

from . import schema as s
from . import status as st
from .config import LogicConfig, Targets


def _num(x: float, decimals: int = 0) -> str:
    """Número al estilo español: 9.246 y 77,3."""
    return f"{x:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _pct(share: float, decimals: int = 1) -> str:
    return f"{_num(100 * share, decimals)} %"


def _days(n: int) -> str:
    return "1 día" if n == 1 else f"{n} días"


def _duration(seconds: float) -> str:
    if seconds < 120:
        return f"{_num(seconds)} s"
    if seconds < 7200:
        return f"{_num(seconds / 60)} min"
    return f"{_num(seconds / 3600, 1)} h"


def _dp_note(row: pd.Series, t: Targets) -> str:
    if math.isnan(row["dp"]):
        return ""
    return f" (Dp {_pct(row['dp'])}, objetivo {_pct(t.dp_min, 0)})"


def _brakes(row: pd.Series, n: int) -> str:
    """Días que frena la línea y horas que hace perder a cada vecina."""
    effects = []
    if row["induced_on_prev_h"] > 0:
        effects.append(f"a {row['prev_op_main']} bloqueada {_num(row['induced_on_prev_h'])} h")
    if row["induced_on_next_h"] > 0:
        effects.append(f"a {row['next_op_main']} sin piezas {_num(row['induced_on_next_h'])} h")
    detail = ": deja " + " y ".join(effects) if effects else ""
    return f"frena la línea {int(row['bottleneck_days'])} de {_days(n)}{detail}"


def _stop_kind(row: pd.Series, t: Targets, n: int) -> str:
    """Cuántas veces se para y si son microparadas o averías largas."""
    if row[s.NAP] <= 0 or math.isnan(row["s_per_stop"]):
        return ""
    seconds = row["s_per_stop"]
    if seconds < t.micro_stop_max_s:
        kind = "son microparadas, no averías largas"
    elif seconds >= t.long_stop_min_s:
        kind = "son averías largas"
    else:
        kind = "son paradas cortas"
    if math.isnan(row["fpm"]):
        how_often = f"Se para {_num(row[s.NAP])} veces en {_days(n)}"
    else:
        how_often = f"Se para {_num(row['fpm'])} veces cada 1.000 piezas"
    return f"{how_often}, unos {_duration(seconds)} cada vez: {kind}."


def _slow_cycle(row: pd.Series, t: Targets) -> str:
    return (
        f"su ciclo es de {_num(row['tcy_cmin'], 1)} cmin, por encima del objetivo de "
        f"{_num(t.tcy_max_cmin)}: es lenta incluso cuando funciona"
    )


def explain(row: pd.Series, config: LogicConfig) -> str:
    """Frase para una máquina en un periodo acumulado (una fila de `Analysis.totals`).

    Empieza por lo que más pesa: frenar a las vecinas o sus propias paradas.
    """
    t = config.targets(row[s.LINE])
    op = row[s.OP]
    status = row["status"]
    if status == st.OUT_OF_SERVICE:
        return f"{op} está fuera de servicio o en by-pass todo el periodo. No entra en el ranking."
    if status == st.UNRELIABLE:
        own_flags = (config.flag_unreliable, config.flag_out_of_service)
        reasons = [f for f in row["flags_all"] if f not in own_flags]
        why = f" ({', '.join(reasons)})" if reasons else ""
        return f"Los datos de {op} no son fiables{why}. No entra en el ranking hasta revisarlos."

    n = int(row["valid_days"])
    brakes = row["bottleneck_days"] > 0
    own_first = status == st.OWN and row[s.TAP] > row["induced_on_neighbours_h"]
    parts = []
    if brakes and not own_first:
        parts.append(f"{op} {_brakes(row, n)}.")
        if row[s.TAP] > 0:
            parts.append(f"Además pierde {_num(row[s.TAP])} h por paradas propias{_dp_note(row, t)}.")
            parts.append(_stop_kind(row, t, n))
    elif status == st.OWN:
        parts.append(f"{op} pierde {_num(row[s.TAP])} h por paradas propias en {_days(n)}{_dp_note(row, t)}.")
        parts.append(_stop_kind(row, t, n))
        if brakes:
            parts.append(f"También {_brakes(row, n)}.")
    elif status == st.INDUCED_PREV:
        parts.append(
            f"{op} pierde {_num(row[s.DES])} h esperando piezas de las máquinas anteriores: "
            "es víctima, no causa."
        )
    elif status == st.INDUCED_NEXT:
        parts.append(
            f"{op} pierde {_num(row[s.SAT])} h bloqueada por las máquinas siguientes: "
            "es víctima, no causa."
        )
    elif status == st.SLOW:
        parts.append(f"{op} casi no se para (Dp {_pct(row['dp'])}), pero {_slow_cycle(row, t)}.")
    else:
        parts.append(f"{op} cumple: Dp {_pct(row['dp'])} y {_pct(row['tai_share'])} de parada inducida.")

    cycle_said = status == st.SLOW and not brakes
    if not cycle_said and not math.isnan(row["tcy_cmin"]) and row["tcy_cmin"] > t.tcy_max_cmin:
        cycle = _slow_cycle(row, t)
        parts.append(f"{cycle[0].upper()}{cycle[1:]}.")
    if math.isnan(row["tcy_cmin"]) and any(f in row["flags_all"] for f in config.counter_flags):
        parts.append("Su contador de piezas no es fiable, así que no se mide su ciclo.")
    if row[s.GROUP] != config.main_group:
        parts.append("Está fuera del flujo principal, así que no entra en el ranking.")
    if row["excluded_days"] > 0:
        parts.append(f"{_days(int(row['excluded_days']))} de {int(row['n_days'])} excluidos por calidad del dato.")
    if pd.notna(row["rank"]):
        parts.append(f"Puesto {int(row['rank'])} de {int(row['ranked_in_line'])} en penalización.")
    return " ".join(p for p in parts if p)
