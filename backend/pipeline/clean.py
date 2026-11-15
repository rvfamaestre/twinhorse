"""Reglas de limpieza para una linea. Cada regla marca filas con un flag; ninguna borra datos.

Las horas limpias van en tbf_h, tap_h, des_h y sat_h. Las columnas originales
(TBF, TAP, DES, SAT, NPR) no se tocan, para poder comparar antes y despues.
Todos los umbrales vienen de LineSettings, nada depende de una linea concreta.
"""

import pandas as pd

from .settings import LineSettings, num

# Flags que sacan una fila del analisis de paradas.
EXCLUDING_FLAGS = ["no_productivo", "sin_datos", "fuera_servicio", "sensor_sospechoso"]
# Flags que invalidan el contador de piezas: se usa el de la linea.
COUNTER_FLAGS = ["contador_roto", "contador_doble"]


def rules(s: LineSettings) -> dict[str, tuple[str, str]]:
    """Regla -> (que pasa, que se decide). Es la leyenda de la tabla de calidad."""
    h = f"{num(s.required_h)} h"
    return {
        "no_productivo": ("Periodo sin producción: la mediana de TBF de la línea es 0 y no cuenta piezas",
                          "Excluir el periodo"),
        "sin_datos": ("La estación no registra nada (TR = 0)", "Excluir la fila"),
        "fuera_servicio": ("TBF = 0 y TAP ocupa casi todo el periodo", "Excluir: fuera de servicio o by-pass"),
        "tr_mayor": (f"TBF + TAP + DES + SAT supera las {h} requeridas", f"Reescalar las cuatro horas a {h}"),
        "tr_menor": (f"TBF + TAP + DES + SAT no llega a {num(s.tr_low_h)} h",
                     "Mantener y marcar: falta tiempo sin explicar"),
        "sensor_sospechoso": ("Más paradas propias que piezas (NAP > NPR) con un contador creíble",
                              "Excluir del ranking: falsa alarma candidata"),
        "contador_doble": (f"NPR mayor que {num(s.double_count_ratio)} veces la mediana de la línea",
                           "Usar el NPR de la línea"),
        "contador_roto": (f"Trabaja pero cuenta menos de {num(s.broken_count_ratio)} veces las piezas de la línea",
                          "Usar el NPR de la línea"),
    }


def _period_median(df: pd.DataFrame, col: str) -> pd.Series:
    """Mediana por periodo de una columna sobre las estaciones del flujo principal."""
    main = df[df["grupo"] == "linea"]
    return df["fecha"].map(main.groupby("fecha")[col].median())


def detect_parallel(df: pd.DataFrame, s: LineSettings) -> list[list[str]]:
    """Grupos de estaciones cercanas que hacen una fraccion de las piezas y juntas suman la linea."""
    rows = df[(df["grupo"] == "linea") & (df["npr_linea"] > 0) & (df["TBF"] > 1.0)]
    ratio = (rows["NPR"] / rows["npr_linea"]).groupby(rows["Operacion"]).median()
    cands = ratio[(ratio >= s.broken_count_ratio) & (ratio <= 0.75)]
    order = df.groupby("Operacion")["Orden_OP"].first().loc[cands.index].sort_values()
    ops, (lo, hi) = list(order.index), s.parallel_sum_range

    groups, i = [], 0
    while i < len(ops):
        group, total, j = [ops[i]], cands[ops[i]], i + 1
        while total < lo and j < len(ops) and order[ops[j]] - order[group[-1]] <= s.parallel_max_gap:
            group.append(ops[j])
            total += cands[ops[j]]
            j += 1
        if len(group) > 1 and lo <= total <= hi:
            groups.append(group)
            i = j
        else:
            i += 1
    return groups


def clean(raw: pd.DataFrame, s: LineSettings) -> pd.DataFrame:
    """Aplica las reglas a las filas de una sola linea."""
    if raw["Linea"].nunique() != 1:
        raise ValueError("clean() trabaja linea a linea: filtra antes por Linea")
    df = raw.copy()
    df["grupo"] = df["Operacion"].map(lambda op: "fuera_flujo" if op in s.off_flow else "linea")
    # Piezas de la linea: mediana de las estaciones que cuentan algo. Las que no cuentan
    # (paradas, contador a cero) bajarian la mediana en una linea corta.
    counting = df[(df["grupo"] == "linea") & (df["NPR"] > 0)]
    df["npr_linea"] = df["fecha"].map(counting.groupby("fecha")["NPR"].median()).fillna(0.0)

    groups = s.parallel_groups if s.parallel_groups is not None else detect_parallel(df, s)
    df["paralelo"] = df["Operacion"].map({op: "+".join(g) for g in groups for op in g})

    working = df["TBF"] > 1.0
    # Sin produccion: la mitad del flujo no trabaja y ninguna estacion cuenta piezas. Con
    # solo la mediana, un tramo parado tiraria tambien las horas del resto, que si produjo.
    df["no_productivo"] = (_period_median(df, "TBF") == 0) & (df["npr_linea"] == 0)
    productive = ~df["no_productivo"]
    low_count = df["NPR"] < s.broken_count_ratio * df["npr_linea"]
    df["sin_datos"] = productive & (df["TR"] == 0)
    df["fuera_servicio"] = productive & (df["TBF"] == 0) & (df["TAP"] >= 0.95 * s.required_h)
    df["tr_mayor"] = productive & (df["TR"] > s.required_h + s.tr_tolerance_h)
    df["tr_menor"] = productive & (df["TR"] > 0) & (df["TR"] < s.tr_low_h)
    # Solo con un contador creible: si no, NAP > NPR es culpa del contador.
    df["sensor_sospechoso"] = productive & ~low_count & (df["NAP"] > df["NPR"])
    df["contador_doble"] = productive & (df["NPR"] > s.double_count_ratio * df["npr_linea"])
    df["contador_roto"] = productive & working & df["paralelo"].isna() & low_count

    scale = (s.required_h / df["TR"]).where(df["tr_mayor"], 1.0)
    for col in ["TBF", "TAP", "DES", "SAT"]:
        df[f"{col.lower()}_h"] = df[col] * scale

    df["npr_ef"] = df["NPR"].where(~df[COUNTER_FLAGS].any(axis=1), df["npr_linea"])
    df["valida"] = ~df[EXCLUDING_FLAGS].any(axis=1)

    # Una estacion entra en el ranking si sus periodos con produccion son mayoritariamente validos.
    prod = df[productive]
    bad_share = (~prod["valida"]).groupby(prod["Operacion"]).mean()
    df["estacion_excluida"] = df["Operacion"].map(bad_share >= s.station_share).fillna(True)
    df["en_ranking"] = (df["grupo"] == "linea") & ~df["estacion_excluida"]
    return df


def station_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Fraccion de periodos con produccion en que cada estacion levanta cada flag."""
    prod = df[~df["no_productivo"]]
    flags = [f for f in EXCLUDING_FLAGS + COUNTER_FLAGS + ["tr_mayor", "tr_menor"] if f != "no_productivo"]
    return prod.groupby("Operacion")[flags].mean()


def quality_table(df: pd.DataFrame, s: LineSettings) -> pd.DataFrame:
    """Cuantas filas y que operaciones toca cada regla."""
    out = []
    for flag, (what, decision) in rules(s).items():
        hit = df[df[flag]]
        if flag == "no_productivo":
            where = ", ".join(sorted(hit["fecha"].dt.strftime("%Y-%m-%d").unique()))
        else:
            ops = hit["Operacion"].value_counts()
            where = ", ".join(f"{op} ({n})" for op, n in ops.head(6).items())
            if len(ops) > 6:
                where += f" y {len(ops) - 6} mas"
        out.append({"regla": flag, "que_pasa": what, "filas": len(hit),
                    "operaciones": hit["Operacion"].nunique(), "donde": where or "-", "decision": decision})
    return pd.DataFrame(out)
