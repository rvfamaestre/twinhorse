"""EDA de una o varias lineas. Desde la raiz del repo:

    python eda/run_eda.py                          # todas las lineas del CSV
    python eda/run_eda.py --line VLL_MONTAJE_L5    # solo una
    python eda/run_eda.py --data otra.csv --config otra_config.csv

Por cada linea escribe eda/output/<linea>/EDA.md, sus figuras en figures/eda/<linea>/ y las tablas en
data/processed/<linea>/. Lo especifico de una linea va en lines/<linea>.json (opcional).
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.pipeline import clean, ingest, kpis  # noqa: E402
from backend.pipeline.settings import LINES_DIR, LineSettings, load_settings, num  # noqa: E402
from eda import plots  # noqa: E402
from eda.plots import fmt  # noqa: E402

STRONG_SHARE = 0.75  # una estacion "frena la linea" si cumple la regla en el 75 % de los periodos


def md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


def names(items) -> str:
    items = list(items)
    if not items:
        return "ninguna"
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def stop_kind(seconds: float) -> str:
    if np.isnan(seconds):
        return "sin paradas contadas"
    if seconds < 60:
        return f"microparadas de unos {fmt(seconds, 0)} s"
    if seconds < 300:
        return f"paradas cortas de unos {fmt(seconds, 0)} s"
    return f"paradas largas de unos {fmt(seconds / 60, 0)} min"


def analyse(raw_line: pd.DataFrame, s: LineSettings) -> dict:
    df = clean.clean(raw_line, s)
    return {
        "df": df, "s": s,
        "quality": clean.quality_table(df, s),
        "flags": clean.station_flags(df),
        "totals": kpis.station_totals(df),
        "arrows": kpis.arrow_days(df),
        "tcy": kpis.cycle_times(df, s),
    }


def write_outputs(a: dict, out_dir: Path, processed_dir: Path, fig_dir: Path) -> dict:
    df, s = a["df"], a["s"]
    n_prod = df.loc[~df["no_productivo"], "fecha"].nunique()
    unit = plots.period_word(df)
    figs = {
        "tr": plots.time_required(df, s, fig_dir / "01_horas_registradas.png"),
        "rank": plots.ranking(df, a["totals"], a["flags"], s, fig_dir / "02_ranking_antes_despues.png"),
        "loss": plots.losses(a["totals"], fig_dir / "03_perdidas_por_estacion.png"),
        "dp": plots.dp_fpm(a["totals"], s, fig_dir / "04_disponibilidad_frecuencia.png"),
        "tcy": plots.cycle_time(a["tcy"], s, fig_dir / "05_tiempo_ciclo.png"),
        "arrows": plots.who_brakes(a["arrows"], n_prod, unit, int(np.ceil(STRONG_SHARE * n_prod)),
                                   fig_dir / "06_quien_frena.png"),
    }
    processed_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(processed_dir / "clean.csv", index=False)
    a["quality"].to_csv(processed_dir / "data_quality.csv", index=False)
    a["totals"].round(3).to_csv(processed_dir / "station_kpis.csv")
    a["tcy"].round(3).to_csv(processed_dir / "cycle_times.csv")
    out_dir.mkdir(parents=True, exist_ok=True)
    return {k: Path(os.path.relpath(p, out_dir)).as_posix() for k, p in figs.items()}


def report(a: dict, figs: dict, processed_dir: Path, config_used: bool) -> str:
    df, s, totals, flags, arrows, tcy = a["df"], a["s"], a["totals"], a["flags"], a["arrows"], a["tcy"]
    unit = plots.period_word(df)
    prod = df[~df["no_productivo"]]
    n_all, n_prod = df["fecha"].nunique(), prod["fecha"].nunique()
    off_dates = [f"{d:%d/%m}" for d in sorted(df.loc[df["no_productivo"], "fecha"].unique())]
    grupo = df.groupby("Operacion")["grupo"].first()
    groups = sorted(df["paralelo"].dropna().unique())
    ranked = totals[totals["en_ranking"]]

    def rel(p: Path) -> str:
        p = Path(p).resolve()
        return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.as_posix()

    # 1. Calidad
    q = a["quality"].rename(columns={"regla": "Regla", "que_pasa": "Qué pasa", "filas": "Filas",
                                     "donde": f"Dónde ({unit})", "decision": "Decisión"})
    q = q[["Regla", "Qué pasa", "Filas", f"Dónde ({unit})", "Decisión"]]
    excluded = [(op, plots.exclusion_reason(op, "linea", flags, s))
                for op in sorted(df.loc[df["estacion_excluida"] & (df["grupo"] == "linea"), "Operacion"].unique())]

    # 2. Ranking
    raw_tap = df.groupby("Operacion")["TAP"].sum().nlargest(5)
    raw_txt = names(f"{op} ({r})" if (r := plots.exclusion_reason(op, grupo[op], flags, s)) else op
                    for op in raw_tap.index)
    n_raw_bad = sum(bool(plots.exclusion_reason(op, grupo[op], flags, s)) for op in raw_tap.index)
    top = ranked.nlargest(5, "tap_h")
    top_tbl = pd.DataFrame({
        "Estación": top.index, "TAP (h)": top["tap_h"].map(fmt), "Dp (%)": top["dp"].map(fmt),
        "Fpm": top["fpm"].map(lambda v: fmt(v, 0)), "Segundos por parada": top["s_por_parada"].map(lambda v: fmt(v, 0)),
    })
    kinds = " ".join(f"{op} hace {stop_kind(r['s_por_parada'])}." for op, r in top.head(2).iterrows())

    # 3. Perdidas
    tai = ranked.nlargest(3, "tai_h")
    tai_txt = names(f"{op} ({r['des_h']:.0f} h sin piezas)" if r["des_h"] >= r["sat_h"]
                    else f"{op} ({r['sat_h']:.0f} h bloqueada)" for op, r in tai.iterrows())

    # 4 y 5. Objetivos
    below = ranked[ranked["dp"] < s.dp_target].sort_values("dp")
    over = tcy[tcy["sobre_objetivo"]]
    raw_only = tcy[(tcy["tcy_raw"] > s.tcy_target) & ~tcy["sobre_objetivo"]]
    in_group = set(df["Operacion"][df["paralelo"].notna()])
    no_tcy = [op for op in ranked.index if op not in tcy.index and op not in in_group]

    # 6. Flechas
    strong_at = int(np.ceil(STRONG_SHARE * n_prod))
    strong = arrows[arrows >= strong_at].sort_values(ascending=False)
    overlap = [op for op in strong.index if op in top.index]
    short = [op for op in strong.index if op in flags.index and flags.loc[op, "tr_menor"] >= s.station_share]

    lines = [
        f"# EDA · {s.line}",
        "",
        f"Para regenerarlo: `python eda/run_eda.py --line {s.line}` desde la raíz del repo. "
        f"Reglas en `backend/pipeline/clean.py`, KPIs en `backend/pipeline/kpis.py` y parámetros de la línea en "
        + (f"`lines/{s.line}.json`." if config_used else "los valores por defecto (no hay `lines/" + s.line + ".json`)."),
        "",
        "## Los datos",
        "",
        f"- {fmt(len(df), 0)} filas: {df['Operacion'].nunique()} operaciones por {n_all} {unit}, "
        f"del {df['fecha'].min():%d/%m/%Y} al {df['fecha'].max():%d/%m/%Y}.",
        f"- Tiempo requerido por periodo: {num(s.required_h)} h. Objetivos: Dp ≥ {num(s.dp_target)} % y Tcy ≤ {num(s.tcy_target)} cmin.",
        f"- La línea hace unas {fmt(prod.groupby('fecha')['npr_linea'].first().median(), 0)} piezas por periodo "
        f"(mediana de NPR por estación).",
        f"- Estaciones fuera del flujo principal: {names(sorted(s.off_flow))}.",
        f"- Grupos en paralelo ({'de la configuración' if s.parallel_groups is not None else 'detectados en los datos'}): {names(groups)}.",
        "",
        "## 1. Calidad del dato",
        "",
        "Ninguna regla borra filas. Cada una pone un flag y el análisis decide qué hacer con él.",
        "",
        md_table(q),
        "",
        f"![Horas registradas]({figs['tr']})",
        "",
        "Azul: faltan horas. Rojo: sobran. Gris rayado: periodo sin producción.",
        "",
        f"- Quedan {n_prod} {unit} con producción"
        + (f" (sin producción: {', '.join(off_dates)})." if off_dates else "."),
        f"- Fuera del ranking: {names(f'{op} ({why})' for op, why in excluded)}.",
        "",
        "## 2. La que más se para no es la que penaliza",
        "",
        f"![Ranking antes y después]({figs['rank']})",
        "",
        f"Sin limpiar, el top 5 por parada propia es {raw_txt}. "
        + ("Ninguna cuenta en el ranking limpio. " if n_raw_bad == len(raw_tap)
           else f"{n_raw_bad} de ellas no cuentan en el ranking limpio. " if n_raw_bad else "")
        + (f"Además, cada estación suma el TAP de los {n_all - n_prod} {unit} sin producción." if n_all > n_prod else ""),
        "",
        "Tras limpiar, el top 5 del flujo principal es este:",
        "",
        md_table(top_tbl),
        "",
        kinds,
        "",
        "## 3. Dónde se pierde el tiempo",
        "",
        f"![Pérdidas por estación]({figs['loss']})",
        "",
        f"En el flujo principal se pierden {fmt(ranked['tap_h'].sum(), 0)} h por parada propia y "
        f"{fmt(ranked['tai_h'].sum(), 0)} h por parada inducida. Las que más horas inducidas acumulan son {tai_txt}.",
        "",
        "## 4. Disponibilidad",
        "",
        f"![Disponibilidad y frecuencia]({figs['dp']})",
        "",
        f"Por debajo del {num(s.dp_target)} %: {names(f'{op} ({fmt(r.dp)} %)' for op, r in below.iterrows())}.",
        "",
        "## 5. Tiempo de ciclo",
        "",
        f"![Tiempo de ciclo]({figs['tcy']})",
        "",
        f"Con las horas corregidas, superan los {num(s.tcy_target)} cmin: "
        f"{names(f'{op} ({fmt(v)})' for op, v in over['tcy'].items())}.",
    ]
    if len(raw_only):
        lines.append(f"Sin corregir también saldría {names(f'{op} ({fmt(v)})' for op, v in raw_only['tcy_raw'].items())}, "
                     f"pero es efecto de registrar más de {num(s.required_h)} h.")
    if groups:
        lines.append(f"{names(groups)} se cuenta como una sola estación.")
    if no_tcy:
        lines.append(f"Sin Tcy porque su contador de piezas no es fiable: {names(no_tcy)}.")
    lines += [
        "",
        "## 6. Quién frena la línea (primera mirada)",
        "",
        f"![Quién frena la línea]({figs['arrows']})",
        "",
        "Regla de las flechas (Kuo, Lim y Meerkov): una estación frena la línea en un periodo si la anterior "
        "está más bloqueada que ella sin piezas (SAT anterior > DES propia) y la siguiente está más sin piezas "
        "que ella bloqueada (DES siguiente > SAT propia). Se calcula periodo a periodo saltando las estaciones no fiables.",
        "",
        f"Cumplen la regla en {strong_at} {unit} o más: {names(f'{op} ({n})' for op, n in strong.items())}.",
        (f"Coinciden con el top 5 de parada propia: {names(overlap)}." if overlap
         else "Ninguna está en el top 5 de parada propia: frenar la línea y pararse mucho son cosas distintas."),
    ]
    if short:
        lines.append(f"Ojo con {names(short)}: registra menos de {num(s.tr_low_h)} h en la mayoría de periodos. "
                     "Hay que confirmar sus datos antes de señalarla.")
    lines += [
        "",
        "## Supuestos",
        "",
        "- El orden de la línea es Orden_OP de la configuración.",
        f"- Contador doble: NPR por encima de {fmt(s.double_count_ratio)} veces la mediana de la línea. "
        f"Contador roto: por debajo de {fmt(s.broken_count_ratio)} veces trabajando.",
        f"- Periodo corto: menos de {num(s.tr_low_h)} h registradas. Una estación sale del ranking si falla "
        f"en el {num(100 * s.station_share)} % de sus periodos.",
        "- Paralelo: estaciones a menos de "
        f"{s.parallel_max_gap} puestos que juntas hacen entre {fmt(s.parallel_sum_range[0], 2)} y "
        f"{fmt(s.parallel_sum_range[1], 2)} veces las piezas de la línea.",
        "",
        "## Ficheros",
        "",
        f"- `{rel(processed_dir / 'clean.csv')}`: todas las filas con sus flags y las horas limpias "
        "(`tbf_h`, `tap_h`, `des_h`, `sat_h`, `npr_ef`).",
        f"- `{rel(processed_dir / 'data_quality.csv')}`: la tabla de calidad de la sección 1.",
        f"- `{rel(processed_dir / 'station_kpis.csv')}`: KPIs acumulados por estación.",
        f"- `{rel(processed_dir / 'cycle_times.csv')}`: Tcy por estación, con los grupos en paralelo juntos.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="EDA de paradas por linea")
    p.add_argument("--data", type=Path, default=ingest.RAW_DATA)
    p.add_argument("--config", type=Path, default=ingest.RAW_CONFIG)
    p.add_argument("--line", action="append", help="linea a analizar (repetible); por defecto todas")
    p.add_argument("--lines-dir", type=Path, default=LINES_DIR)
    p.add_argument("--out", type=Path, default=ROOT / "eda" / "output")
    p.add_argument("--processed", type=Path, default=ROOT / "data" / "processed")
    p.add_argument("--figures", type=Path, default=ROOT / "figures" / "eda")
    args = p.parse_args(argv)

    raw = ingest.load(args.data, args.config)
    available = ingest.lines(raw)
    selected = args.line or available
    unknown = set(selected) - set(available)
    if unknown:
        sys.exit(f"Lineas que no estan en los datos: {sorted(unknown)}. Disponibles: {available}")

    for line in selected:
        raw_line = raw[raw["Linea"] == line]
        s = load_settings(line, raw_line, args.lines_dir)
        a = analyse(raw_line, s)
        out_dir, processed_dir = args.out / line, args.processed / line
        figs = write_outputs(a, out_dir, processed_dir, args.figures / line)
        text = report(a, figs, processed_dir, (args.lines_dir / f"{line}.json").exists())
        (out_dir / "EDA.md").write_text(text, encoding="utf-8")
        print(f"{line}: {out_dir / 'EDA.md'} ({len(figs)} figuras), tablas en {processed_dir}")


if __name__ == "__main__":
    main()
