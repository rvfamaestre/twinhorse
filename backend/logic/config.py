"""Objetivos, umbrales y topología. Nada de esto está escrito en la lógica: todo sale de aquí.

Cada línea puede tener sus propios objetivos y tramos en `lines/<Linea>.json` (en la raíz
del repo, el mismo fichero que lee la limpieza); si no, usa los del reto para la L5 y una
sola cadena por Orden_OP.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

LINES_DIR = Path(__file__).resolve().parents[2] / "lines"
# Claves de la lógica en lines/<Linea>.json
LOGIC_KEYS = {"notas", "objetivos", "tramos", "hipotesis_tramos"}
# Claves de la limpieza (campos de LineSettings en backend/pipeline/settings.py). La lógica no las
# usa, salvo los objetivos de la línea, que valen para las dos. Un test comprueba que no se desfasan.
PIPELINE_KEYS = {
    "required_h", "dp_target", "tcy_target", "tr_tolerance_h", "tr_low_ratio", "double_count_ratio",
    "broken_count_ratio", "parallel_sum_range", "parallel_max_gap", "station_share", "off_flow",
    "parallel_groups", "subassemblies",
}


@dataclass(frozen=True)
class Targets:
    required_h: float = 22.0         # tiempo requerido al día (24 h - 2 h de pausas)
    dp_min: float = 0.90             # disponibilidad mínima
    tcy_max_cmin: float = 80.0       # tiempo de ciclo máximo
    tai_max: float = 0.10            # parada inducida máxima (TAI / TR) para estar "ok"
    micro_stop_max_s: float = 60.0   # por debajo: microparadas
    long_stop_min_s: float = 600.0   # por encima: averías largas


@dataclass(frozen=True)
class LogicConfig:
    default_targets: Targets = field(default_factory=Targets)
    targets_by_line: dict[str, Targets] = field(default_factory=dict)
    # Línea → {tramo: [operaciones]}. Las que no aparecen van al tramo principal.
    segments_by_line: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    main_group: str = "principal"
    main_segment: str = "principal"
    # Nombres de los flags que pone la limpieza; acordarlos con Rol 1
    flag_out_of_service: str = "fuera_servicio"
    flag_unreliable: str = "dato_no_fiable"
    flag_non_productive: str = "dia_no_productivo"
    # Flags que invalidan el contador de piezas: ese día no se mide ni Tcy ni Fpm
    counter_flags: tuple[str, ...] = ("contador_roto", "contador_doble")

    def targets(self, line: str) -> Targets:
        return self.targets_by_line.get(line, self.default_targets)

    @classmethod
    def from_line_files(cls, files: dict[str, dict]) -> "LogicConfig":
        """Configuración a partir de `load_line_files`: claves "objetivos" y "tramos".

        Los objetivos de la línea (`dp_target` en %, `tcy_target`, `required_h`) son los mismos
        que usa la limpieza; "objetivos" puede afinar el resto de umbrales de `Targets`.
        """
        return cls(
            targets_by_line={line: t for line, f in files.items() if (t := _targets(f))},
            segments_by_line={line: f["tramos"] for line, f in files.items() if f.get("tramos")},
        )


def _targets(content: dict) -> Targets | None:
    shared = {"dp_min": content.get("dp_target"), "tcy_max_cmin": content.get("tcy_target"),
              "required_h": content.get("required_h")}
    values = {k: float(v) for k, v in shared.items() if v is not None}
    if "dp_min" in values:
        values["dp_min"] = values["dp_min"] / 100
    values.update(content.get("objetivos") or {})
    return Targets(**values) if values else None


def load_line_files(lines_dir: Path = LINES_DIR) -> dict[str, dict]:
    """Lee `lines/<Linea>.json`: una línea nueva sin archivo funciona con los valores por defecto."""
    known = LOGIC_KEYS | PIPELINE_KEYS
    files = {}
    for path in sorted(Path(lines_dir).glob("*.json")):
        content = json.loads(path.read_text(encoding="utf-8"))
        unknown = set(content) - known
        if unknown:
            raise ValueError(f"{path.name}: claves desconocidas {sorted(unknown)}")
        files[path.stem] = content
    return files
