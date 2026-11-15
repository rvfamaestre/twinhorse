"""Parametros de cada linea.

Todo tiene un valor por defecto o se deduce de los datos, asi que una linea nueva
funciona sin configurar nada. Lo que solo sabe la planta (estaciones fuera del flujo,
objetivos propios, grupos en paralelo que los datos no delatan) va en
lines/<Linea>.json y pisa el valor por defecto. El mismo fichero lleva los tramos de la
logica de paradas (LOGIC_KEYS), que lee backend/logic/config.py.
"""

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LINES_DIR = ROOT / "lines"
# Claves de lines/<Linea>.json que no son de LineSettings: las lee backend/logic/config.py.
LOGIC_KEYS = {"objetivos", "tramos", "hipotesis_tramos"}


@dataclass
class LineSettings:
    line: str
    # Horas que la linea necesita a cada operacion por periodo. None = se deduce de los datos.
    required_h: float | None = None
    dp_target: float = 90.0  # disponibilidad minima (%)
    tcy_target: float = 80.0  # tiempo de ciclo maximo (cmin)
    # Margen para dar por buena la suma TBF + TAP + DES + SAT.
    tr_tolerance_h: float = 0.05
    # Una fila es corta si registra menos de esta fraccion del tiempo requerido.
    tr_low_ratio: float = 0.9
    # Contador de piezas: doble por encima y roto por debajo de estas veces la mediana de la linea.
    double_count_ratio: float = 1.3
    broken_count_ratio: float = 0.3
    # Paralelo: estaciones que hacen una fraccion de las piezas y juntas suman la linea.
    parallel_sum_range: tuple[float, float] = (0.85, 1.15)
    parallel_max_gap: int = 4  # distancia maxima en Orden_OP entre estaciones del mismo grupo
    # Una estacion sale del ranking si el problema aparece en esta fraccion de sus dias.
    station_share: float = 0.5
    # Estaciones fuera del flujo principal (manipuladores, puestos auxiliares).
    off_flow: list[str] = field(default_factory=list)
    # Grupos en paralelo. None = se detectan solos; [] = no hay ninguno.
    parallel_groups: list[list[str]] | None = None
    # Subconjuntos que se montan aparte y se unen a la linea (solo para agrupar en los informes).
    subassemblies: list[str] = field(default_factory=list)

    @property
    def tr_low_h(self) -> float:
        return self.tr_low_ratio * self.required_h


def num(x: float) -> str:
    """Numero corto con coma decimal: 22 -> '22', 19.8 -> '19,8'."""
    return f"{round(x, 2):g}".replace(".", ",")


def infer_required_h(df: pd.DataFrame) -> float:
    """Tiempo requerido = el valor de TBF + TAP + DES + SAT que mas se repite (a 0,1 h).

    Una estacion que registra todo su periodo suma justo el tiempo requerido, asi que
    ese valor forma un pico; la mediana se queda corta porque muchas dejan minutos sin
    registrar. Los periodos sin produccion, si los hay, lo dan limpio (todo sale como
    TAP). En L5 sale 22 h: 24 h menos 2 h de pausas.
    """
    period_tbf = df.groupby("fecha")["TBF"].transform("median")
    off = df.loc[(period_tbf == 0) & (df["TR"] > 0), "TR"]
    tr = off if len(off) else df.loc[df["TR"] > 0, "TR"]
    if tr.empty:
        raise ValueError("Ninguna fila registra tiempo: no se puede deducir el tiempo requerido")
    return float(tr.round(1).mode().max())


def read_line_file(line: str, lines_dir: Path = LINES_DIR) -> dict:
    """lines/<line>.json tal cual ({} si no existe), tras comprobar que no trae claves desconocidas."""
    path = Path(lines_dir) / f"{line}.json"
    content = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    unknown = set(content) - {f.name for f in fields(LineSettings)} - LOGIC_KEYS - {"notas"}
    if unknown:
        raise ValueError(f"{path.name}: claves desconocidas {sorted(unknown)}")
    return content


def load_settings(line: str, df: pd.DataFrame, lines_dir: Path = LINES_DIR) -> LineSettings:
    """Valores por defecto + lines/<line>.json si existe + lo que se deduce de los datos."""
    path = Path(lines_dir) / f"{line}.json"
    known = {f.name for f in fields(LineSettings)}
    overrides = {k: v for k, v in read_line_file(line, lines_dir).items() if k in known}
    if "parallel_sum_range" in overrides:
        overrides["parallel_sum_range"] = tuple(overrides["parallel_sum_range"])
    settings = LineSettings(line=line, **overrides)

    stations = set(df["Operacion"])
    missing = (set(settings.off_flow) | set(settings.subassemblies)) - stations
    for group in settings.parallel_groups or []:
        missing |= set(group) - stations
    if missing:
        raise ValueError(f"{path.name}: estaciones que no estan en los datos {sorted(missing)}")
    if settings.required_h is None:
        settings.required_h = infer_required_h(df)
    return settings
