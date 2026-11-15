"""Carga de datos al formato de entrada de la lógica (ver schema.py)."""

from datetime import date
from pathlib import Path

import pandas as pd

from . import schema as s
from .config import LogicConfig


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def to_logic_input(data: pd.DataFrame, config_table: pd.DataFrame | None = None) -> pd.DataFrame:
    """Une datos y configuración por Línea + Operación y añade la fecha ISO.

    Sirve para los CSV en bruto y para la tabla limpia de Rol 1: si ya trae
    Orden_OP o day, se respetan.
    """
    out = data.copy()
    if s.ORDER not in out:
        if config_table is None:
            raise ValueError("Falta Orden_OP: pasa también la tabla de configuración")
        out = out.merge(config_table, on=[s.LINE, s.OP], how="left", validate="many_to_one")
        orphans = sorted(out.loc[out[s.ORDER].isna(), s.OP].unique())
        if orphans:
            raise ValueError(f"Operaciones sin posición en la configuración: {orphans}")
        out[s.ORDER] = out[s.ORDER].astype(int)
    if s.DAY not in out:
        # Jour 1 es lunes: semana ISO
        out[s.DAY] = [
            date.fromisocalendar(int(y), int(w), int(j)).isoformat()
            for y, w, j in zip(out["Year"], out["Week"], out["Jour"])
        ]
    return out


def load_raw(data_path: str | Path, config_path: str | Path) -> pd.DataFrame:
    return to_logic_input(read_table(data_path), read_table(config_path))


# Columnas de verdadero/falso de la limpieza de Rol 1 (backend/pipeline/clean.py)
_CLEAN_UNRELIABLE = ["sin_datos", "sensor_sospechoso", "estacion_excluida"]
_CLEAN_INFO = ["tr_mayor", "tr_menor", "contador_roto", "contador_doble"]


def from_clean(clean: pd.DataFrame, config: LogicConfig | None = None, rescaled: bool = True) -> pd.DataFrame:
    """Traduce la tabla limpia de Rol 1 (data/processed/<Linea>/clean.csv).

    - Horas reescaladas (tbf_h, tap_h, des_h, sat_h) y contador efectivo (npr_ef)
      en lugar de los originales. Con `rescaled=False`, las horas originales
      (para la prueba de robustez).
    - grupo "linea" es el flujo principal; fuera_flujo no entra en la cadena ni
      en el ranking.
    - no_productivo descarta la fila; fuera_servicio se mantiene; sin_datos,
      sensor_sospechoso y estacion_excluida la marcan como dato no fiable. El
      resto de sus flags se copian a la salida como información.
    """
    config = config or LogicConfig()
    to_flags = {
        "no_productivo": [config.flag_non_productive],
        "fuera_servicio": [config.flag_out_of_service],
        **{f: [f, config.flag_unreliable] for f in _CLEAN_UNRELIABLE},
        **{f: [f] for f in _CLEAN_INFO},
    }
    cols = [c for c in to_flags if c in clean]
    flags = [
        tuple(sorted({name for col, on in zip(cols, row) if on for name in to_flags[col]}))
        for row in clean[cols].itertuples(index=False)
    ]
    hours = {h: clean[f"{h.lower()}_h"] if rescaled else clean[h] for h in s.HOURS}
    return pd.DataFrame(
        {
            s.LINE: clean["Linea"],
            s.OP: clean["Operacion"],
            s.ORDER: clean["Orden_OP"],
            s.DAY: clean["fecha"],
            **hours,
            s.NAP: clean["NAP"],
            s.NPR: clean["npr_ef"],
            s.GROUP: clean["grupo"].where(clean["grupo"] != "linea", config.main_group),
            s.PARALLEL: clean["paralelo"],
            s.FLAGS: pd.Series(flags, index=clean.index, dtype=object),
        }
    )


def read_clean(path: str | Path) -> pd.DataFrame:
    """La tabla de Rol 1 tal cual: un clean.csv, o todos los <Linea>/clean.csv de una carpeta."""
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*/clean.csv")) or [path / "clean.csv"]
    else:
        files = [path]
    return pd.concat([read_table(f) for f in files], ignore_index=True)


def load_clean(path: str | Path, config: LogicConfig | None = None) -> pd.DataFrame:
    """Lee la limpieza de Rol 1 y la traduce a la entrada de la lógica."""
    return from_clean(read_clean(path), config)


def flag_non_productive_days(df: pd.DataFrame, config: LogicConfig | None = None) -> pd.DataFrame:
    """PROVISIONAL, hasta tener la limpieza de Rol 1: marca como no productivo el
    día en que la mediana de TBF de la línea es 0 (regla del plan de equipo)."""
    config = config or LogicConfig()
    out = df.copy()
    median_tbf = out.groupby([s.LINE, s.DAY])[s.TBF].transform("median")
    flags = out[s.FLAGS] if s.FLAGS in out else [None] * len(out)
    out[s.FLAGS] = pd.Series(
        [s.as_flags(f) + ((config.flag_non_productive,) if m == 0 else ()) for f, m in zip(flags, median_tbf)],
        index=out.index,
        dtype=object,
    )
    return out
