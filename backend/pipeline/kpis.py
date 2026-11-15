"""KPIs del reto sobre los datos limpios de una linea.

Dp  = TBF / (TBF + TAP)            objetivo en LineSettings.dp_target (%)
Tcy = 6000 * TBF / NPR  (cmin)     objetivo en LineSettings.tcy_target (1 h = 6000 cmin)
Fpm = 1000 * NAP / NPR             paradas propias cada 1000 piezas
TAI = DES + SAT                    parada inducida
"""

import numpy as np
import pandas as pd

HOURS = ["tbf_h", "tap_h", "des_h", "sat_h"]


def add_ratios(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    own = (df["tbf_h"] + df["tap_h"]).replace(0, np.nan)
    npr = df["npr_ef"].replace(0, np.nan)
    df["dp"] = 100 * df["tbf_h"] / own
    df["tcy"] = 6000 * df["tbf_h"] / npr
    df["fpm"] = 1000 * df["NAP"] / npr
    df["tai_h"] = df["des_h"] + df["sat_h"]
    # Duracion media de una parada propia: separa microparadas de averias largas.
    df["s_por_parada"] = 3600 * df["tap_h"] / df["NAP"].replace(0, np.nan)
    return df


def station_day(df: pd.DataFrame) -> pd.DataFrame:
    """KPIs por estacion y periodo, solo filas validas."""
    return add_ratios(df[df["valida"]])


def _totals(rows: pd.DataFrame, how_hours: str) -> pd.DataFrame:
    agg = rows.groupby("Operacion").agg(
        Orden_OP=("Orden_OP", "min"), grupo=("grupo", "first"), en_ranking=("en_ranking", "all"),
        periodos=("fecha", "nunique"), **{h: (h, how_hours) for h in HOURS},
        NAP=("NAP", "sum"), npr_ef=("npr_ef", "sum"),
    )
    return add_ratios(agg).sort_values("Orden_OP")


def station_totals(df: pd.DataFrame) -> pd.DataFrame:
    """KPIs acumulados por estacion sobre los periodos validos."""
    return _totals(df[df["valida"]], "sum")


def merge_parallel(df: pd.DataFrame) -> pd.DataFrame:
    """Junta cada grupo en paralelo en un solo nodo por periodo.

    Las horas se promedian (cada estacion vive su propio periodo) y las piezas se suman.
    """
    single = df[df["paralelo"].isna()]
    group = df[df["paralelo"].notna()]
    if group.empty:
        return df
    merged = group.groupby(["paralelo", "fecha"]).agg(
        Orden_OP=("Orden_OP", "min"), grupo=("grupo", "first"), valida=("valida", "all"),
        en_ranking=("en_ranking", "all"), **{h: (h, "mean") for h in HOURS},
        NAP=("NAP", "sum"), npr_ef=("npr_ef", "sum"),
    ).reset_index().rename(columns={"paralelo": "Operacion"})
    merged["paralelo"] = np.nan
    return pd.concat([single, merged], ignore_index=True)


def chain(df: pd.DataFrame) -> pd.DataFrame:
    """Estaciones fiables del flujo principal, con los grupos en paralelo como un solo nodo."""
    return merge_parallel(df[(df["grupo"] == "linea") & df["valida"] & df["en_ranking"]])


def arrow_days(df: pd.DataFrame) -> pd.Series:
    """Regla de las flechas (Kuo, Lim y Meerkov) periodo a periodo sobre el flujo principal.

    La estacion i frena la linea un periodo si la anterior esta mas bloqueada que i
    desabastecida (SAT[i-1] > DES[i]) y la siguiente esta mas desabastecida que i
    bloqueada (DES[i+1] > SAT[i]). Las estaciones no fiables se saltan, asi que la
    vecina es siempre la siguiente estacion fiable segun Orden_OP.
    """
    nodes = chain(df)
    hits: dict[str, int] = {}
    for _, period in nodes.sort_values("Orden_OP").groupby("fecha"):
        ops, des, sat = period["Operacion"].to_numpy(), period["des_h"].to_numpy(), period["sat_h"].to_numpy()
        for i in range(1, len(ops) - 1):
            if sat[i - 1] > des[i] and des[i + 1] > sat[i]:
                hits[ops[i]] = hits.get(ops[i], 0) + 1
    order = nodes.groupby("Operacion")["Orden_OP"].first().sort_values()
    return pd.Series(hits, dtype=int).reindex(order.index, fill_value=0)


def cycle_times(df: pd.DataFrame, s) -> pd.DataFrame:
    """Tcy por nodo del flujo (grupos en paralelo juntos), corregido y sin corregir.

    Se dejan fuera las estaciones con el contador de piezas roto o doble la mayoria de periodos,
    porque su Tcy no se puede medir.
    """
    prod = df[~df["no_productivo"]]
    bad = prod.groupby("Operacion")[["contador_roto", "contador_doble"]].mean().max(axis=1)
    ok = bad[bad < s.station_share].index
    base = df[df["valida"] & df["en_ranking"] & df["Operacion"].isin(ok)]
    t = merge_parallel(base).groupby("Operacion").agg(
        Orden_OP=("Orden_OP", "first"), tbf_h=("tbf_h", "sum"), npr=("npr_ef", "sum")
    ).sort_values("Orden_OP")
    t["tcy"] = 6000 * t["tbf_h"] / t["npr"]

    # Sin corregir: horas originales; el grupo en paralelo promedia TBF y suma piezas.
    raw = base.assign(nodo=base["paralelo"].fillna(base["Operacion"]))
    per_period = raw.groupby(["nodo", "fecha"]).agg(TBF=("TBF", "mean"), NPR=("NPR", "sum"))
    raw_tot = per_period.groupby("nodo").sum()
    t["tcy_raw"] = (6000 * raw_tot["TBF"] / raw_tot["NPR"].replace(0, np.nan)).reindex(t.index)
    t["sobre_objetivo"] = t["tcy"] > s.tcy_target
    return t
