"""Carga las dos tablas del reto y las une por Linea + Operacion.

Vale para cualquier linea y para varias lineas en el mismo fichero. Si la tabla no
trae la columna Jour (datos semanales), cada fila se fecha en el lunes de su semana.
"""

from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DATA = ROOT / "data" / "raw" / "datos_hackaton.csv"
RAW_CONFIG = ROOT / "data" / "raw" / "config_hackaton.csv"

TIME_COLS = ["TBF", "TAP", "DES", "SAT"]
COUNT_COLS = ["NAP", "NPR"]
KEY = ["Linea", "Operacion"]


def load(data_path: Path = RAW_DATA, config_path: Path = RAW_CONFIG) -> pd.DataFrame:
    """Una fila por operacion y periodo, con su orden en la linea, la fecha ISO y TR."""
    data = pd.read_csv(data_path)
    config = pd.read_csv(config_path)

    missing = {"Year", "Week", *KEY, *TIME_COLS, *COUNT_COLS} - set(data.columns)
    if missing:
        raise ValueError(f"Faltan columnas en la tabla de datos: {sorted(missing)}")
    missing = {*KEY, "Orden_OP"} - set(config.columns)
    if missing:
        raise ValueError(f"Faltan columnas en la tabla de configuracion: {sorted(missing)}")
    if config.duplicated(KEY).any() or config.duplicated(["Linea", "Orden_OP"]).any():
        raise ValueError("La configuracion repite una operacion o un Orden_OP dentro de una linea")

    if "Jour" not in data.columns:
        data["Jour"] = 1
    if data.duplicated(["Year", "Week", "Jour", *KEY]).any():
        raise ValueError("Hay filas repetidas para la misma operacion y periodo")
    if (data[TIME_COLS + COUNT_COLS] < 0).any().any():
        raise ValueError("Hay tiempos o contadores negativos")

    df = data.merge(config, on=KEY, how="left", validate="many_to_one")
    unmatched = df.loc[df["Orden_OP"].isna(), KEY].drop_duplicates()
    if len(unmatched):
        raise ValueError(f"Operaciones sin configuracion:\n{unmatched.to_string(index=False)}")

    df["Orden_OP"] = df["Orden_OP"].astype(int)
    # Jour 1 es lunes.
    df["fecha"] = pd.to_datetime(
        [date.fromisocalendar(y, w, d) for y, w, d in zip(df["Year"], df["Week"], df["Jour"])]
    )
    df["TR"] = df[TIME_COLS].sum(axis=1)
    return df.sort_values(["Linea", "fecha", "Orden_OP"]).reset_index(drop=True)


def lines(df: pd.DataFrame) -> list[str]:
    return sorted(df["Linea"].unique())
