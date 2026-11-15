"""Orquesta la lógica de paradas: de la tabla limpia al análisis por máquina."""

from dataclasses import dataclass

import pandas as pd

from . import schema as s
from . import status as st
from .arrows import REQUIRED_TIME, arrow_rule
from .config import LogicConfig
from .explain import explain
from .kpis import COUNTED, add_kpis, piece_kpis
from .penalty import add_penalty

PERIOD = "period"
TOTAL = "total"
FLAG_NO_TIME = "sin_tiempo_registrado"  # TR = 0: la máquina no registró ningún tiempo
_KEYS = [s.PLANT, s.LINE, s.OP]


@dataclass
class Analysis:
    daily: pd.DataFrame         # una fila por máquina y día
    totals: pd.DataFrame        # una fila por máquina, periodo completo
    arrows_daily: pd.DataFrame  # una fila por par de vecinas y día
    arrows_total: pd.DataFrame  # una fila por par de vecinas, sobre el acumulado
    config: LogicConfig

    def to_dict(self) -> dict:
        from .output import to_dashboard

        return to_dashboard(self)


def prepare(df: pd.DataFrame, config: LogicConfig) -> pd.DataFrame:
    """Valida la entrada y la normaliza: flags como tupla, Planta y Grupo por
    defecto, fecha ISO y fuera los días que la limpieza marcó como no productivos."""
    missing = [c for c in s.REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas de entrada: {missing}")
    empty = [c for c in s.HOURS + s.COUNTS if df[c].isna().any()]
    if empty:
        raise ValueError(f"Hay valores vacíos en: {empty}")

    out = df.copy()
    prefix = out[s.LINE].str.split("_").str[0]
    out[s.PLANT] = out[s.PLANT].fillna(prefix) if s.PLANT in out else prefix
    out[s.GROUP] = out[s.GROUP].fillna(config.main_group) if s.GROUP in out else config.main_group
    if s.PARALLEL not in out:
        out[s.PARALLEL] = None
    if s.SEGMENT not in out:
        out[s.SEGMENT] = _segments(out, config)
    raw_flags = out[s.FLAGS] if s.FLAGS in out else [None] * len(out)
    out[s.FLAGS] = pd.Series([s.as_flags(f) for f in raw_flags], index=out.index, dtype=object)
    out[s.DAY] = pd.to_datetime(out[s.DAY]).dt.strftime("%Y-%m-%d")
    out = out[~out[s.FLAGS].map(lambda f: config.flag_non_productive in f)]
    if out.duplicated([s.LINE, s.OP, s.DAY]).any():
        raise ValueError("Hay filas repetidas para la misma máquina y día")
    return out.reset_index(drop=True)


def _segments(df: pd.DataFrame, config: LogicConfig) -> list[str]:
    """Tramo de cada fila según `config.segments_by_line`; por defecto, el principal."""
    segment_of = {}
    for line, segments in config.segments_by_line.items():
        ops = set(df.loc[df[s.LINE] == line, s.OP])
        for segment, members in segments.items():
            missing = set(members) - ops
            if ops and missing:
                raise ValueError(f"Tramo {segment} de {line}: operaciones que no están en los datos {sorted(missing)}")
            segment_of.update({(line, op): segment for op in members})
    return [segment_of.get(k, config.main_segment) for k in zip(df[s.LINE], df[s.OP])]


def analyze(df: pd.DataFrame, config: LogicConfig | None = None) -> Analysis:
    """Calcula KPIs, estado, regla de las flechas, índice de penalización y frase
    de cada máquina, por día y acumulado. Procesa todas las plantas y líneas que
    vengan en `df`; cada línea es independiente."""
    config = config or LogicConfig()
    daily = add_kpis(prepare(df, config))
    counter_ok = ~daily[s.FLAGS].map(lambda f: any(c in f for c in config.counter_flags))
    for col, counted in COUNTED.items():
        daily[counted] = daily[col].where(counter_ok)
    daily = piece_kpis(daily, s.DAY)
    no_time = daily["TR"] <= 0
    daily[s.FLAGS] = pd.Series(
        [f + (FLAG_NO_TIME, config.flag_unreliable) if bad else f for f, bad in zip(daily[s.FLAGS], no_time)],
        index=daily.index,
        dtype=object,
    )
    daily["exclusion"] = daily[s.FLAGS].map(lambda f: st.exclusion_from_flags(f, config))
    daily["status"] = st.classify(daily, config)
    daily[REQUIRED_TIME] = daily[s.LINE].map(lambda line: config.targets(line).required_h)

    nodes, arrows_daily = arrow_rule(daily, s.DAY, config)
    daily = _attach_nodes(daily, nodes, [s.LINE, s.DAY, s.OP])

    totals = _accumulate(daily, config)
    nodes_total, arrows_total = arrow_rule(totals, PERIOD, config)
    totals = totals.merge(
        nodes_total[[s.LINE, s.OP, "is_bottleneck", "severity"]].rename(
            columns={"is_bottleneck": "brakes_line_in_total", "severity": "severity_total"}
        ),
        on=[s.LINE, s.OP],
        how="left",
    )
    totals["brakes_line_in_total"] = totals["brakes_line_in_total"].eq(True)
    totals = add_penalty(totals, config.main_group)
    totals["explanation"] = [explain(row, config) for _, row in totals.iterrows()]
    return Analysis(daily, totals, arrows_daily, arrows_total.drop(columns=PERIOD), config)


def _attach_nodes(df: pd.DataFrame, nodes: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    cols = ["prev_op", "next_op", "is_bottleneck", "severity", "induced_on_prev_h", "induced_on_next_h"]
    out = df.merge(nodes[[*keys, *cols]], on=keys, how="left")
    out["is_bottleneck"] = out["is_bottleneck"].eq(True)
    out[["induced_on_prev_h", "induced_on_next_h"]] = out[["induced_on_prev_h", "induced_on_next_h"]].fillna(0.0)
    return out


def _mode(values: pd.Series):
    """Valor más frecuente (el menor en empate), o None si no hay ninguno."""
    modes = values.dropna().mode()
    return modes.iloc[0] if len(modes) else None


def _accumulate(daily: pd.DataFrame, config: LogicConfig) -> pd.DataFrame:
    """Una fila por máquina con el periodo completo. Suma solo los días válidos;
    los excluidos se cuentan aparte."""
    valid = daily[daily["exclusion"].isna()]
    summed = [*s.HOURS, *s.COUNTS, *COUNTED.values(), REQUIRED_TIME, "induced_on_prev_h", "induced_on_next_h"]
    totals = (
        daily.groupby(_KEYS)
        .agg(
            **{c: (c, "first") for c in (s.ORDER, s.GROUP, s.PARALLEL, s.SEGMENT)},
            n_days=(s.DAY, "size"),
        )
        .join(valid.groupby(_KEYS)[summed].sum())
        .join(valid.groupby(_KEYS).agg(valid_days=(s.DAY, "size"), bottleneck_days=("is_bottleneck", "sum")))
        .join(
            valid[valid["is_bottleneck"]]
            .groupby(_KEYS)
            .agg(prev_op_main=("prev_op", _mode), next_op_main=("next_op", _mode))
        )
        .reset_index()
    )
    totals[[*summed, "valid_days", "bottleneck_days"]] = totals[[*summed, "valid_days", "bottleneck_days"]].fillna(0)
    totals[["valid_days", "bottleneck_days"]] = totals[["valid_days", "bottleneck_days"]].astype(int)
    totals["excluded_days"] = totals["n_days"] - totals["valid_days"]

    by_machine = daily.groupby(_KEYS)
    flags_all = {k: tuple(sorted(set().union(*f))) for k, f in by_machine[s.FLAGS]}
    exclusion = by_machine["exclusion"].agg(_mode).to_dict()
    keys = list(zip(*(totals[k] for k in _KEYS)))
    totals["flags_all"] = pd.Series([flags_all[k] for k in keys], index=totals.index, dtype=object)
    # Fuera del ranking solo si no tiene ningún día válido
    totals["exclusion"] = [exclusion[k] if n == 0 else None for k, n in zip(keys, totals["valid_days"])]
    totals[PERIOD] = TOTAL

    totals = piece_kpis(add_kpis(totals), PERIOD)
    totals["status"] = st.classify(totals, config)
    return totals
