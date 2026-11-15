"""Ejecuta la lógica de paradas y enseña un resumen por línea. Desde la raíz del repo:

    python -m backend.logic --clean data/processed --out data/processed/logic/logic_state.json
    python -m backend.logic --data data/raw/datos_hackaton.csv --config data/raw/config_hackaton.csv --provisional-clean
"""

import argparse
import json
from pathlib import Path

from . import schema as s
from .config import LogicConfig, load_line_files
from .loaders import flag_non_productive_days, load_clean, read_table, to_logic_input
from .penalty import rankings
from .pipeline import analyze


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m backend.logic", description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--clean", help="clean.csv de Rol 1, o la carpeta data/processed con una por línea")
    source.add_argument("--data", help="tabla de datos en el formato de la lógica, o los CSV en bruto")
    parser.add_argument("--config", help="con --data: tabla de configuración, si los datos no traen Orden_OP")
    parser.add_argument(
        "--provisional-clean",
        action="store_true",
        help="con --data: quita los días no productivos (sin la limpieza de Rol 1)",
    )
    parser.add_argument("--out", type=Path, help="escribe la salida jerárquica en este JSON")
    parser.add_argument("--top", type=int, default=5, help="máquinas por ranking en el resumen")
    args = parser.parse_args(argv)

    config = LogicConfig.from_line_files(load_line_files())
    if args.clean:
        data = load_clean(args.clean, config)
    else:
        data = to_logic_input(read_table(args.data), read_table(args.config) if args.config else None)
        if args.provisional_clean:
            data = flag_non_productive_days(data, config)
    analysis = analyze(data, config)

    totals = analysis.totals.set_index([s.LINE, s.OP])
    for line, ranks in rankings(analysis.totals, config.main_group).items():
        t = totals.loc[line]
        days = analysis.daily.loc[analysis.daily[s.LINE] == line, s.DAY].nunique()
        print(f"\n{line} · {days} días · {len(t)} máquinas ({len(ranks['penalizacion'])} en el ranking)")
        print("  Penaliza más:   " + ", ".join(f"{op} ({t.loc[op, 'penalty_h']:.0f} h)" for op in ranks["penalizacion"][: args.top]))
        print("  Se para más:    " + ", ".join(f"{op} ({t.loc[op, s.TAP]:.0f} h)" for op in ranks["se_para_mas"][: args.top]))
        print("  Frena la línea: " + ", ".join(f"{op} ({t.loc[op, 'bottleneck_days']} d)" for op in ranks["frena_linea"][: args.top]))
        for op in ranks["penalizacion"][: args.top]:
            print(f"  · {t.loc[op, 'explanation']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSalida escrita en {args.out}")


if __name__ == "__main__":
    main()
