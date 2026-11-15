"""Comprueba que el pipeline funciona con una linea que no es L5.

La linea TEST_L9 es inventada: 8 estaciones, 16 h requeridas (no 22) y un caso de cada
problema que el EDA tiene que encontrar solo, sin ningun fichero lines/*.json.
"""

import pandas as pd
import pytest

from backend.pipeline import clean, ingest, kpis
from backend.pipeline.settings import load_settings
from eda import run_eda

LINE = "TEST_L9"
REQUIRED = 16.0
DAYS = [(10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (11, 1)]  # (semana, dia); S11 lunes sin produccion


def _row(week, day, op, tbf=13.0, tap=1.0, des=1.0, sat=1.0, nap=20, npr=1000, line=LINE):
    return dict(Linea=line, Year=2026, Week=week, Jour=day, Operacion=op,
                TBF=tbf, TAP=tap, DES=des, SAT=sat, NAP=nap, NPR=npr)


def synthetic_line(line: str = LINE) -> tuple[pd.DataFrame, pd.DataFrame]:
    ops = [f"A{i}" for i in range(1, 9)]
    rows = []
    for week, day in DAYS:
        for op in ops:
            if (week, day) == (11, 1):
                rows.append(_row(week, day, op, tbf=0, tap=REQUIRED, des=0, sat=0, nap=0, npr=0, line=line))
                continue
            kw = {
                "A1": dict(tbf=11.0, sat=3.0),            # bloqueada por A4
                "A2": dict(nap=3000),                      # sensor que rebota
                "A3": dict(tbf=0, tap=REQUIRED, des=0, sat=0, nap=5, npr=0),  # fuera de servicio
                "A4": dict(tbf=14.0, des=0.5, sat=0.5),    # cuello de botella
                "A5": dict(tbf=11.0, des=3.0, npr=500),    # pareja en paralelo,
                "A6": dict(tbf=11.0, des=3.0, npr=500),    # sin piezas por culpa de A4
                "A7": dict(tbf=14.0, des=2.0),             # registra 18 h de 16
                "A8": dict(npr=10),                        # contador roto
            }[op]
            rows.append(_row(week, day, op, line=line, **kw))
    data = pd.DataFrame(rows)
    config = pd.DataFrame({"Linea": line, "Operacion": ops, "Orden_OP": range(1, len(ops) + 1)})
    return data, config


def _analyse(tmp_path, data, config):
    data.to_csv(tmp_path / "datos.csv", index=False)
    config.to_csv(tmp_path / "config.csv", index=False)
    raw = ingest.load(tmp_path / "datos.csv", tmp_path / "config.csv")
    s = load_settings(LINE, raw, lines_dir=tmp_path)  # sin json: todo por defecto o deducido
    return s, clean.clean(raw, s)


@pytest.fixture
def analysed(tmp_path):
    return _analyse(tmp_path, *synthetic_line())


def flagged(df, flag):
    return set(df.loc[df[flag], "Operacion"])


def test_required_time_is_inferred(analysed):
    s, _ = analysed
    assert s.required_h == REQUIRED


def test_each_problem_is_found(analysed):
    s, df = analysed
    assert set(df.loc[df["no_productivo"], "fecha"].dt.strftime("%Y-%m-%d")) == {"2026-03-09"}
    assert flagged(df, "fuera_servicio") == {"A3"}
    assert flagged(df, "sensor_sospechoso") == {"A2"}
    assert flagged(df, "tr_mayor") == {"A7"}
    assert flagged(df, "contador_roto") == {"A8"}
    assert set(df.loc[df["estacion_excluida"], "Operacion"]) == {"A2", "A3"}


def test_stopped_section_is_not_a_day_off(tmp_path):
    data, config = synthetic_line()
    # El martes de S10 se para medio flujo (A1-A5) y el resto sigue contando piezas.
    stopped = (data["Week"] == 10) & (data["Jour"] == 2) & data["Operacion"].isin(["A1", "A2", "A3", "A4", "A5"])
    data.loc[stopped, ["TBF", "TAP", "DES", "SAT", "NAP", "NPR"]] = [0, REQUIRED, 0, 0, 0, 0]
    _, df = _analyse(tmp_path, data, config)
    assert set(df.loc[df["no_productivo"], "fecha"].dt.strftime("%Y-%m-%d")) == {"2026-03-09"}


def test_parallel_pair_is_detected(analysed):
    _, df = analysed
    assert set(df["paralelo"].dropna()) == {"A5+A6"}


def test_clean_hours_fit_required_time(analysed):
    s, df = analysed
    a7 = df[(df["Operacion"] == "A7") & ~df["no_productivo"]]
    assert (a7[["tbf_h", "tap_h", "des_h", "sat_h"]].sum(axis=1).round(6) == s.required_h).all()
    a8 = df[(df["Operacion"] == "A8") & ~df["no_productivo"]]
    assert (a8["npr_ef"] == a8["npr_linea"]).all()


def test_bottleneck_found_by_arrow_rule(analysed):
    _, df = analysed
    arrows = kpis.arrow_days(df)
    assert arrows.idxmax() == "A4"
    assert arrows["A4"] == 5


def test_report_for_several_lines(tmp_path):
    l9, c9 = synthetic_line(LINE)
    l8, c8 = synthetic_line("TEST_L8")
    pd.concat([l9, l8]).to_csv(tmp_path / "datos.csv", index=False)
    pd.concat([c9, c8]).to_csv(tmp_path / "config.csv", index=False)
    run_eda.main(["--data", str(tmp_path / "datos.csv"), "--config", str(tmp_path / "config.csv"),
                  "--lines-dir", str(tmp_path), "--out", str(tmp_path / "out"),
                  "--processed", str(tmp_path / "processed"), "--figures", str(tmp_path / "fig")])
    for line in (LINE, "TEST_L8"):
        report = (tmp_path / "out" / line / "EDA.md").read_text(encoding="utf-8")
        assert f"# EDA · {line}" in report
        assert "A4" in report
        assert len(list((tmp_path / "fig" / line).glob("*.png"))) == 6
        assert (tmp_path / "processed" / line / "clean.csv").exists()


def test_weekly_data_without_jour(tmp_path):
    data, config = synthetic_line()
    full_week = data[data["Week"] == 10].drop(columns="Jour")
    weekly = full_week.groupby(["Linea", "Year", "Week", "Operacion"], as_index=False).sum()
    weekly.to_csv(tmp_path / "datos.csv", index=False)
    config.to_csv(tmp_path / "config.csv", index=False)
    raw = ingest.load(tmp_path / "datos.csv", tmp_path / "config.csv")
    assert raw["fecha"].nunique() == 1
    s = load_settings(LINE, raw, lines_dir=tmp_path)
    assert s.required_h == 5 * REQUIRED  # 5 dias de 16 h
    assert len(clean.clean(raw, s)) == len(weekly)
