"""Índice de penalización y rankings por línea."""

import pandas as pd

from . import schema as s


def _eligible(totals: pd.DataFrame, main_group: str) -> pd.Series:
    """Entran en el ranking las máquinas del flujo principal con algún día válido."""
    return (totals["valid_days"] > 0) & (totals[s.GROUP] == main_group)


def add_penalty(totals: pd.DataFrame, main_group: str) -> pd.DataFrame:
    """Índice de penalización (IP) por máquina, siempre con su desglose:

        IP = TAP propio + SAT de la anterior + DES de la siguiente

    Los dos últimos términos solo cuentan los días en que la máquina frena la
    línea según la regla de las flechas. Las máquinas fuera del flujo principal
    o sin ningún día válido no entran en el ranking (`rank` vacío).
    """
    out = totals.copy()
    out["induced_on_neighbours_h"] = out["induced_on_prev_h"] + out["induced_on_next_h"]
    out["penalty_h"] = out[s.TAP] + out["induced_on_neighbours_h"]
    eligible = out[_eligible(out, main_group)].sort_values(
        [s.LINE, "penalty_h", s.ORDER], ascending=[True, False, True]
    )
    out["rank"] = (eligible.groupby(s.LINE).cumcount() + 1).reindex(out.index).astype("Int64")
    out["ranked_in_line"] = out[s.LINE].map(eligible.groupby(s.LINE).size()).fillna(0).astype(int)
    return out


def rankings(totals: pd.DataFrame, main_group: str) -> dict[str, dict[str, list[str]]]:
    """Tres rankings por línea, para enseñarlos lado a lado:

    - penalizacion: por IP; la lista de prioridades para mantenimiento.
    - se_para_mas: por parada propia (TAP); el ranking ingenuo.
    - frena_linea: solo las que frenan algún día, por días y horas inducidas.
    """
    eligible = totals[_eligible(totals, main_group)]
    out = {}
    for line, t in eligible.groupby(s.LINE, sort=True):
        brakes = t[t["bottleneck_days"] > 0]
        out[line] = {
            "penalizacion": _ordered(t, ["penalty_h"]),
            "se_para_mas": _ordered(t, [s.TAP]),
            "frena_linea": _ordered(brakes, ["bottleneck_days", "induced_on_neighbours_h"]),
        }
    return out


def _ordered(t: pd.DataFrame, by: list[str]) -> list[str]:
    """Operaciones ordenadas de mayor a menor; en empate, por orden en la línea."""
    ordered = t.sort_values([*by, s.ORDER], ascending=[False] * len(by) + [True])
    return ordered[s.OP].tolist()
