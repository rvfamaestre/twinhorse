"""Series diarias por estacion para la prediccion.

Salen del mismo pipeline que el EDA (backend.pipeline), asi que usan las mismas reglas de
limpieza y valen para cualquier linea. Una serie = una estacion y una metrica, indexada por
dia productivo (los dias sin produccion no son paradas y no entran).
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from backend.pipeline import clean, ingest
from backend.pipeline.settings import LINES_DIR, LineSettings, load_settings

STATION_METRICS = ["tap_h", "des_h", "sat_h"]
LINE_ID = "LINEA"  # serie de la linea completa
LINE_METRIC = "npr"  # piezas al dia de la linea
CALENDAR_COLS = ["dia_semana", "tras_parada", "vispera_parada"]
# Parada media de mas de 5 min con al menos media hora de TAP: posible intervencion planificada.
LONG_STOP_S = 300
LONG_STOP_MIN_TAP_H = 0.5


@dataclass
class Panel:
    """Todo lo que necesita un modelo para una linea."""

    settings: LineSettings
    dates: pd.DatetimeIndex  # dias productivos, en orden
    off_dates: set  # dias sin produccion del periodo observado
    values: dict[str, pd.DataFrame]  # metrica -> tabla dias x series (NaN = dato no valido)
    neighbours: dict[str, tuple[str | None, str | None]]  # estacion -> (anterior, siguiente)
    clean_rows: pd.DataFrame = field(repr=False)

    @property
    def line(self) -> str:
        return self.settings.line

    def series(self, metric: str) -> list[str]:
        return list(self.values[metric].columns)


def load_line(line: str, data_path: Path = ingest.RAW_DATA, config_path: Path = ingest.RAW_CONFIG,
              lines_dir: Path = LINES_DIR) -> Panel:
    raw = ingest.load(data_path, config_path)
    raw_line = raw[raw["Linea"] == line]
    if raw_line.empty:
        raise ValueError(f"La linea {line} no esta en los datos. Disponibles: {ingest.lines(raw)}")
    s = load_settings(line, raw_line, lines_dir)
    return build_panel(clean.clean(raw_line, s), s)


def build_panel(df: pd.DataFrame, s: LineSettings) -> Panel:
    prod = df[~df["no_productivo"]]
    dates = pd.DatetimeIndex(sorted(prod["fecha"].unique()))
    off = set(pd.DatetimeIndex(df.loc[df["no_productivo"], "fecha"].unique()))

    rows = df[df["valida"] & df["en_ranking"]]
    order = rows.groupby("Operacion")["Orden_OP"].first().sort_values()
    values = {m: rows.pivot(index="fecha", columns="Operacion", values=m).reindex(index=dates, columns=order.index)
              for m in STATION_METRICS}
    values[LINE_METRIC] = prod.groupby("fecha")["npr_linea"].first().reindex(dates).to_frame(LINE_ID)

    ops = list(order.index)
    neighbours = {op: (ops[i - 1] if i > 0 else None, ops[i + 1] if i < len(ops) - 1 else None)
                  for i, op in enumerate(ops)}
    return Panel(settings=s, dates=dates, off_dates=off, values=values, neighbours=neighbours, clean_rows=df)


# ---------------------------------------------------------------- calendario

def _prev_weekday(d: pd.Timestamp) -> pd.Timestamp:
    return d - pd.Timedelta(days=3 if d.dayofweek == 0 else 1)


def _next_weekday(d: pd.Timestamp) -> pd.Timestamp:
    return d + pd.Timedelta(days=3 if d.dayofweek == 4 else 1)


def calendar(dates, off_dates) -> pd.DataFrame:
    """Covariables que se conocen de antemano para cada dia productivo.

    dia_semana: 0 lunes ... 4 viernes.
    tras_parada: el dia laborable anterior la linea no produjo (festivo o parada planificada).
    vispera_parada: el dia laborable siguiente la linea no producira.
    """
    dates = pd.DatetimeIndex(dates)
    off = set(pd.DatetimeIndex(list(off_dates)))
    return pd.DataFrame({
        "dia_semana": dates.dayofweek.astype(float),
        "tras_parada": [float(_prev_weekday(d) in off) for d in dates],
        "vispera_parada": [float(_next_weekday(d) in off) for d in dates],
    }, index=dates)


def future_dates(last: pd.Timestamp, horizon: int, off_dates) -> pd.DatetimeIndex:
    """Los siguientes `horizon` dias laborables tras `last`, saltando los dias sin produccion."""
    off = set(pd.DatetimeIndex(list(off_dates)))
    out, d = [], pd.Timestamp(last)
    while len(out) < horizon:
        d = _next_weekday(d)
        if d not in off:
            out.append(d)
    return pd.DatetimeIndex(out)


# ---------------------------------------------------------------- paradas largas

def long_stops(panel: Panel) -> pd.DataFrame:
    """Estacion-dias cuya parada propia media supera LONG_STOP_S: posible intervencion planificada.

    Con datos diarios no se puede saber si fue una averia o una parada a proposito, solo que
    fueron pocas paradas y largas. Se marcan para no tratarlas como microparadas.
    """
    rows = panel.clean_rows
    rows = rows[rows["valida"] & rows["en_ranking"]].copy()
    rows["s_por_parada"] = 3600 * rows["tap_h"] / rows["NAP"].replace(0, np.nan)
    hit = rows[(rows["s_por_parada"] > LONG_STOP_S) & (rows["tap_h"] >= LONG_STOP_MIN_TAP_H)]
    return hit[["Operacion", "fecha", "tap_h", "NAP", "s_por_parada"]].sort_values(["Operacion", "fecha"])
