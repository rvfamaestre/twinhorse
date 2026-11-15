"""KPIs del reto. Valen igual para una fila diaria que para un acumulado.

En los acumulados se suman primero horas y contadores y después se calculan los
ratios; nunca se promedian ratios.
"""

import pandas as pd

from . import schema as s

CMIN_PER_HOUR = 6000  # 1 h = 60 min = 6.000 centésimas de minuto


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """División que da NaN en vez de infinito cuando el denominador es 0."""
    return num.astype(float) / den.astype(float).where(den > 0)


def add_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """Añade TR, TAI, Dp, Tcy, Fpm, la cuota de cada pérdida y los segundos por parada.

    TR  = TBF + TAP + DES + SAT        (tiempo requerido, diapositiva 4)
    TAI = DES + SAT                    (parada inducida)
    Dp  = TBF / (TBF + TAP)            (objetivo >= 90 %)
    Tcy = 6000 * TBF / NPR  [cmin]     (objetivo <= 80 cmin)
    Fpm = 1000 * NAP / NPR             (paradas propias cada 1.000 piezas)
    """
    out = df.copy()
    out["TR"] = out[s.HOURS].sum(axis=1)
    out["TAI"] = out[s.DES] + out[s.SAT]
    out["dp"] = _ratio(out[s.TBF], out[s.TBF] + out[s.TAP])
    out["tcy_cmin"] = _ratio(CMIN_PER_HOUR * out[s.TBF], out[s.NPR])
    out["fpm"] = _ratio(1000 * out[s.NAP], out[s.NPR])
    out["s_per_stop"] = _ratio(3600 * out[s.TAP], out[s.NAP])
    for col in (s.TAP, s.DES, s.SAT, "TAI"):
        out[f"{col.lower()}_share"] = _ratio(out[col], out["TR"])
    return out


COUNTED = {s.TBF: "TBF_counted", s.NAP: "NAP_counted", s.NPR: "NPR_counted"}


def piece_kpis(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Tcy y Fpm solo con días de contador de piezas fiable.

    Usa las columnas de `COUNTED`: las mismas horas y contadores, pero vacías (o
    sin sumar) los días en que la limpieza marcó el contador. Con un contador
    sustituto, el Tcy no dice nada de la máquina.

    En un grupo en paralelo, el Tcy que cuenta es el de la estación: las
    máquinas juntas sacan una pieza cada 6000 / (NPR_1/TBF_1 + NPR_2/TBF_2 + ...)
    cmin. El de cada máquina por separado queda en `tcy_machine_cmin`.
    """
    out = df.copy()
    tbf, nap, npr = (out[COUNTED[c]] for c in (s.TBF, s.NAP, s.NPR))
    out["tcy_machine_cmin"] = _ratio(CMIN_PER_HOUR * tbf, npr)
    out["fpm"] = _ratio(1000 * nap, npr)
    in_group = out[s.PARALLEL].notna()
    pieces_per_h = _ratio(npr, tbf).where(in_group)
    group_rate = pieces_per_h.groupby([out[s.LINE], out[period], out[s.PARALLEL]]).transform(
        lambda rates: rates.sum() if rates.notna().all() else float("nan")
    )
    # Las filas sin grupo no salen del groupby: se realinean con el índice completo
    station = (CMIN_PER_HOUR / group_rate.where(group_rate > 0)).reindex(out.index)
    out["tcy_cmin"] = out["tcy_machine_cmin"].where(~in_group, station)
    return out
