import json
import math
from pathlib import Path

import pandas as pd
import pytest

from logic import LogicConfig, Targets, analyze, flag_non_productive_days, from_clean, load_clean, load_raw
from logic.kpis import add_kpis

DAY = "2026-09-29"
REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw"
CLEAN_DIR = REPO / "data" / "processed"
CLEAN_FLAGS = [
    "no_productivo", "sin_datos", "fuera_servicio", "tr_mayor", "tr_menor",
    "sensor_sospechoso", "contador_doble", "contador_roto", "estacion_excluida",
]


def machine(op, order, tbf, tap, des, sat, nap=10, npr=1300, line="VLL_TEST", day=DAY, **extra):
    return {
        "Linea": line, "Operacion": op, "Orden_OP": order, "day": day,
        "TBF": tbf, "TAP": tap, "DES": des, "SAT": sat, "NAP": nap, "NPR": npr, **extra,
    }


def toy_line(**kw):
    """M3 frena la línea: las anteriores se bloquean (SAT) y las siguientes esperan
    piezas (DES). M5 es la que más se para por sí misma, pero no frena a nadie."""
    return [
        machine("M1", 1, 18.0, 0.5, 0.0, 3.5, **kw),
        machine("M2", 2, 17.0, 0.5, 0.5, 4.0, **kw),
        machine("M3", 3, 17.0, 4.0, 0.5, 0.5, **kw),
        machine("M4", 4, 17.0, 0.5, 4.0, 0.5, **kw),
        machine("M5", 5, 13.0, 5.5, 3.5, 0.0, **kw),
    ]


def clean_row(op, order, grupo="linea", paralelo=None, **flags):
    """Fila con las columnas de data/processed/<Linea>/clean.csv (Rol 1)."""
    return {
        "Linea": "VLL_TEST", "Operacion": op, "Orden_OP": order, "fecha": DAY,
        # Originales sin limpiar: la lógica no debe usarlos
        "TBF": 99.0, "TAP": 99.0, "DES": 99.0, "SAT": 99.0, "NPR": 1,
        "tbf_h": 17.0, "tap_h": 1.0, "des_h": 2.0, "sat_h": 2.0, "NAP": 10, "npr_ef": 1300.0,
        "grupo": grupo, "paralelo": paralelo,
        **{f: flags.get(f, False) for f in CLEAN_FLAGS},
    }


def totals_of(analysis):
    return analysis.totals.set_index("Operacion")


def test_kpis_follow_the_challenge_formulas():
    k = add_kpis(pd.DataFrame([machine("M1", 1, 18.0, 2.0, 1.0, 1.0, nap=27, npr=1350)])).iloc[0]
    assert k["TR"] == 22.0
    assert k["TAI"] == 2.0
    assert k["dp"] == pytest.approx(0.9)
    assert k["tcy_cmin"] == pytest.approx(80.0)
    assert k["fpm"] == pytest.approx(20.0)
    assert k["s_per_stop"] == pytest.approx(2 * 3600 / 27)


def test_kpis_without_denominator_are_nan_not_infinite():
    k = add_kpis(pd.DataFrame([machine("M1", 1, 0.0, 0.0, 22.0, 0.0, nap=0, npr=0)])).iloc[0]
    assert math.isnan(k["dp"]) and math.isnan(k["tcy_cmin"]) and math.isnan(k["fpm"])


def test_arrows_converge_on_the_machine_that_brakes_the_line():
    a = analyze(pd.DataFrame(toy_line()))
    assert a.arrows_daily["direction"].tolist() == ["→", "→", "←", "←"]
    assert a.arrows_daily["points_to"].tolist() == ["M2", "M3", "M3", "M4"]
    brakes = a.daily[a.daily["is_bottleneck"]]
    assert brakes["Operacion"].tolist() == ["M3"]
    assert brakes["severity"].iloc[0] == pytest.approx((4.0 - 0.5) / 22 + (4.0 - 0.5) / 22)


def test_machine_that_stops_most_is_not_the_one_that_penalizes():
    a = analyze(pd.DataFrame(toy_line()))
    t = totals_of(a)
    ranking = a.to_dict()["plants"][0]["lines"][0]["ranking"]
    assert ranking["se_para_mas"][0] == "M5"
    assert ranking["penalizacion"][0] == "M3"
    assert ranking["frena_linea"] == ["M3"]
    # IP = TAP propio + SAT de la anterior + DES de la siguiente
    assert t.loc["M3", "penalty_h"] == pytest.approx(4.0 + 4.0 + 4.0)
    assert t.loc["M3", "induced_on_prev_h"] == pytest.approx(4.0)
    assert t.loc["M3", "induced_on_next_h"] == pytest.approx(4.0)
    assert t.loc["M5", "penalty_h"] == pytest.approx(5.5)


def test_penalty_adds_up_over_the_days_it_brakes_the_line():
    rows = toy_line() + toy_line(day="2026-09-30")
    t = totals_of(analyze(pd.DataFrame(rows)))
    assert t.loc["M3", "bottleneck_days"] == 2
    assert t.loc["M3", "penalty_h"] == pytest.approx(24.0)


def test_first_machine_can_brake_the_line():
    rows = [
        machine("M1", 1, 15.0, 6.0, 0.0, 1.0),
        machine("M2", 2, 17.0, 0.5, 4.0, 0.5),
        machine("M3", 3, 17.0, 0.5, 4.0, 0.5),
    ]
    a = analyze(pd.DataFrame(rows))
    assert a.daily.loc[a.daily["is_bottleneck"], "Operacion"].tolist() == ["M1"]


def test_unreliable_machine_is_skipped_and_its_neighbours_become_contiguous():
    rows = toy_line()
    rows[1]["flags"] = ["dato_no_fiable"]
    a = analyze(pd.DataFrame(rows))
    t = totals_of(a)
    m3 = a.daily.set_index("Operacion").loc["M3"]
    assert m3["prev_op"] == "M1"
    assert t.loc["M3", "induced_on_prev_h"] == pytest.approx(3.5)
    assert t.loc["M2", "status"] == "dato_no_fiable"
    assert pd.isna(t.loc["M2", "rank"])
    assert "M2" not in a.to_dict()["plants"][0]["lines"][0]["ranking"]["penalizacion"]


def test_status_follows_its_priority_order():
    rows = [
        machine("OK", 1, 21.0, 0.5, 0.3, 0.2, npr=1600),     # Dp 97,7 %, Tcy 78,8
        machine("SLOW", 2, 21.0, 0.5, 0.3, 0.2, npr=1500),   # igual, pero Tcy 84
        machine("OWN", 3, 16.0, 5.0, 0.5, 0.5),
        machine("STARVED", 4, 15.0, 0.5, 6.0, 0.5),
        machine("BLOCKED", 5, 15.0, 0.5, 0.5, 6.0),
        machine("OUT", 6, 0.0, 22.0, 0.0, 0.0, flags="fuera_servicio"),
        machine("EMPTY", 7, 0.0, 0.0, 0.0, 0.0, nap=0, npr=0),
    ]
    status = analyze(pd.DataFrame(rows)).daily.set_index("Operacion")["status"]
    assert status.to_dict() == {
        "OK": "ok",
        "SLOW": "lenta",
        "OWN": "parada_propia",
        "STARVED": "desabastecimiento",
        "BLOCKED": "saturacion",
        "OUT": "fuera_servicio",
        "EMPTY": "dato_no_fiable",
    }


def test_targets_can_change_per_line():
    rows = [machine("SLOW", 1, 21.0, 0.5, 0.3, 0.2, npr=1500)]
    config = LogicConfig(targets_by_line={"VLL_TEST": Targets(tcy_max_cmin=90.0)})
    assert analyze(pd.DataFrame(rows), config).daily["status"].iloc[0] == "ok"


def test_non_productive_days_are_dropped_and_text_flags_are_parsed():
    rows = toy_line() + toy_line(day="2026-09-30", flags="dia_no_productivo")
    rows[0]["flags"] = "revisar;  reescalado_22h"
    a = analyze(pd.DataFrame(rows))
    assert a.daily["day"].unique().tolist() == [DAY]
    assert a.daily.set_index("Operacion").loc["M1", "flags"] == ("reescalado_22h", "revisar")


def test_lines_are_independent_and_output_is_hierarchical():
    rows = toy_line(line="VLL_A") + toy_line(line="PLT_B", Planta="PLT")
    a = analyze(pd.DataFrame(rows))
    assert len(a.arrows_daily) == 8  # 4 pares por línea, ninguno entre líneas
    out = a.to_dict()
    assert [p["id"] for p in out["plants"]] == ["PLT", "VLL"]
    station = out["plants"][1]["lines"][0]["stations"][2]
    assert station["op"] == "M3" and station["sensors"] == []
    assert station["penalty"]["rank"] == 1
    json.dumps(out)  # solo tipos de JSON


def test_same_input_in_any_order_gives_the_same_output():
    df = pd.DataFrame(toy_line() + toy_line(day="2026-09-30"))
    shuffled = df.sample(frac=1, random_state=0)
    assert json.dumps(analyze(df).to_dict()) == json.dumps(analyze(shuffled).to_dict())


def test_explanation_names_who_it_brakes_and_who_is_a_victim():
    t = totals_of(analyze(pd.DataFrame(toy_line())))
    assert t.loc["M3", "explanation"].startswith(
        "M3 frena la línea 1 de 1 día: deja a M2 bloqueada 4 h y a M4 sin piezas 4 h."
    )
    assert "es víctima, no causa" in t.loc["M2", "explanation"]


def test_teammate_clean_table_is_translated():
    rows = [
        clean_row("A", 1, tr_mayor=True),
        clean_row("B", 2, sensor_sospechoso=True),
        clean_row("C", 3, fuera_servicio=True),
        clean_row("D", 4, no_productivo=True),
    ]
    df = from_clean(pd.DataFrame(rows))
    r = df.set_index("Operacion")
    assert (r.loc["A", "TBF"], r.loc["A", "NPR"], r.loc["A", "Grupo"]) == (17.0, 1300.0, "principal")
    assert r.loc["A", "flags"] == ("tr_mayor",)
    assert r.loc["B", "flags"] == ("dato_no_fiable", "sensor_sospechoso")
    assert r.loc["C", "flags"] == ("fuera_servicio",)
    status = analyze(df).daily.set_index("Operacion")["status"]
    assert "D" not in status.index
    assert (status["B"], status["C"]) == ("dato_no_fiable", "fuera_servicio")


def test_off_flow_machines_are_out_of_the_chain_and_the_ranking():
    rows = toy_line() + [machine("MAN", 6, 2.0, 20.0, 0.0, 0.0, Grupo="fuera_flujo")]
    a = analyze(pd.DataFrame(rows))
    assert "MAN" not in set(a.arrows_daily["from"]) | set(a.arrows_daily["to"])
    assert "MAN" not in a.to_dict()["plants"][0]["lines"][0]["ranking"]["se_para_mas"]
    man = totals_of(a).loc["MAN"]
    assert pd.isna(man["rank"])
    assert "fuera del flujo principal" in man["explanation"]


def test_parallel_machines_are_judged_by_the_station_cycle():
    # Cada una tarda 157,9 cmin por pieza, pero juntas sacan una cada 78,9
    rows = [
        machine("P1", 1, 20.0, 1.0, 0.5, 0.5, npr=760, Paralelo="P1+P2"),
        machine("P2", 2, 20.0, 1.0, 0.5, 0.5, npr=760, Paralelo="P1+P2"),
    ]
    a = analyze(pd.DataFrame(rows))
    t = totals_of(a)
    assert t.loc["P1", "tcy_machine_cmin"] == pytest.approx(6000 * 20 / 760)
    assert t.loc["P1", "tcy_cmin"] == pytest.approx(6000 / (2 * 760 / 20))
    assert set(a.daily["status"]) == {"ok"}
    assert a.to_dict()["plants"][0]["lines"][0]["stations"][0]["parallel_with"] == ["P2"]


def test_missing_columns_are_reported():
    with pytest.raises(ValueError, match="Faltan columnas"):
        analyze(pd.DataFrame(toy_line()).drop(columns=["SAT"]))


@pytest.mark.skipif(not (RAW / "datos_hackaton.csv").exists(), reason="sin los CSV del reto")
def test_real_line_l5():
    data = flag_non_productive_days(load_raw(RAW / "datos_hackaton.csv", RAW / "config_hackaton.csv"))
    a = analyze(data)
    t = totals_of(a)
    assert a.daily["day"].nunique() == 16
    assert len(t) == 91
    assert t.loc["ST-0260", "bottleneck_days"] == 16
    assert t.loc["ST-0830", "bottleneck_days"] == 16
    assert t.loc["ST-0830", "status"] == "lenta"


@pytest.mark.skipif(not (CLEAN_DIR / "VLL_MONTAJE_L5" / "clean.csv").exists(), reason="sin la limpieza de Rol 1")
def test_real_line_l5_with_teammate_cleaning():
    a = analyze(load_clean(CLEAN_DIR))
    ranking = a.to_dict()["plants"][0]["lines"][0]["ranking"]
    t = totals_of(a)
    assert ranking["penalizacion"][0] == "ST-0260"
    assert len(ranking["penalizacion"]) == 81  # 91 - 7 fuera del flujo - 3 excluidas
    assert t.loc["PM2130", "status"] == "fuera_servicio"
    assert t.loc["ST-0830", "status"] == "lenta"
    assert t.loc["ST2376", "status"] != "lenta"  # en paralelo con ST-2375


def test_last_machine_can_brake_the_line():
    rows = [
        machine("M1", 1, 17.0, 0.5, 0.5, 4.0),
        machine("M2", 2, 17.0, 0.5, 0.5, 4.0),
        machine("M3", 3, 15.0, 6.0, 1.0, 0.0),
    ]
    a = analyze(pd.DataFrame(rows))
    assert a.daily.loc[a.daily["is_bottleneck"], "Operacion"].tolist() == ["M3"]


def test_parallel_group_is_one_node_in_the_arrow_rule():
    rows = [
        machine("M1", 1, 18.0, 0.5, 0.0, 3.5),
        machine("P1", 2, 20.0, 1.0, 0.5, 0.5, Paralelo="P1+P2"),
        machine("P2", 3, 20.0, 1.0, 0.5, 0.5, Paralelo="P1+P2"),
        machine("M4", 4, 17.0, 0.5, 4.0, 0.5),
    ]
    a = analyze(pd.DataFrame(rows))
    assert list(zip(a.arrows_daily["from"], a.arrows_daily["to"])) == [("M1", "P1+P2"), ("P1+P2", "M4")]
    t = totals_of(a)
    assert t.loc[["P1", "P2"], "bottleneck_days"].tolist() == [1, 1]
    # Las horas que el grupo hace perder a sus vecinas se reparten entre sus máquinas
    assert t.loc["P1", "induced_on_prev_h"] == pytest.approx(3.5 / 2)
    assert t.loc["P1", "induced_on_next_h"] == pytest.approx(4.0 / 2)


def test_arrows_compare_on_required_time_not_on_recorded_time():
    # B registra 17,6 h de 22. Sobre lo registrado, su DES (1,8 h) pesaría más que
    # el SAT de A (2 h); sobre las 22 h requeridas, no.
    rows = [machine("A", 1, 19.0, 1.0, 0.0, 2.0), machine("B", 2, 14.0, 0.8, 1.8, 1.0)]
    assert analyze(pd.DataFrame(rows)).arrows_daily["direction"].tolist() == ["→"]


@pytest.mark.skipif(not (CLEAN_DIR / "VLL_MONTAJE_L5" / "clean.csv").exists(), reason="sin la limpieza de Rol 1")
def test_arrow_rule_matches_the_cleaning_except_at_the_line_ends():
    """La limpieza (backend/pipeline/kpis.py) no deja frenar la línea a la primera ni a la
    última máquina; el método original sí. Fuera de eso, deben dar los mismos días."""
    from backend.pipeline import kpis as pipeline_kpis

    his = pipeline_kpis.arrow_days(pd.read_csv(CLEAN_DIR / "VLL_MONTAJE_L5" / "clean.csv", parse_dates=["fecha"]))
    a = analyze(load_clean(CLEAN_DIR))
    t = totals_of(a)
    node = t["Paralelo"].fillna(pd.Series(t.index, index=t.index))
    mine = t.groupby(node)["bottleneck_days"].first().reindex(his.index)
    by_day = a.arrows_daily.groupby("day")
    ends = set(by_day["from"].first()) | set(by_day["to"].last())
    inner = [n for n in his.index if n not in ends]
    assert len(inner) == len(his) - len(ends)
    assert mine[inner].tolist() == his[inner].tolist()


def test_segments_are_independent_chains():
    config = LogicConfig(segments_by_line={"VLL_TEST": {"B": ["M4", "M5"]}})
    a = analyze(pd.DataFrame(toy_line()), config)
    pairs = list(zip(a.arrows_daily["Tramo"], a.arrows_daily["from"], a.arrows_daily["to"]))
    assert pairs == [("B", "M4", "M5"), ("principal", "M1", "M2"), ("principal", "M2", "M3")]
    # Sin vecina siguiente, M3 frena su tramo solo por la izquierda
    assert totals_of(a).loc["M3", "induced_on_next_h"] == 0.0


def test_segment_with_unknown_machine_is_reported():
    config = LogicConfig(segments_by_line={"VLL_TEST": {"B": ["M4", "NO_EXISTE"]}})
    with pytest.raises(ValueError, match="NO_EXISTE"):
        analyze(pd.DataFrame(toy_line()), config)


def test_line_files_set_targets_and_segments(tmp_path):
    (tmp_path / "L_X.json").write_text(
        json.dumps({"objetivos": {"tcy_max_cmin": 90.0}, "tramos": {"B": ["M4"]}}), encoding="utf-8"
    )
    from logic.config import load_line_files

    config = LogicConfig.from_line_files(load_line_files(tmp_path))
    assert config.targets("L_X").tcy_max_cmin == 90.0
    assert config.segments_by_line == {"L_X": {"B": ["M4"]}}
    (tmp_path / "L_Y.json").write_text(json.dumps({"tramo": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="claves desconocidas"):
        load_line_files(tmp_path)


def test_line_targets_are_shared_with_the_cleaning(tmp_path):
    """lines/<Linea>.json es el mismo fichero para la limpieza y para la lógica."""
    from dataclasses import fields

    from backend.pipeline.settings import LOGIC_KEYS, LineSettings
    from logic.config import LOGIC_KEYS as MINE, PIPELINE_KEYS, load_line_files

    assert PIPELINE_KEYS == {f.name for f in fields(LineSettings)} - {"line"}
    assert LOGIC_KEYS == MINE - {"notas"}
    content = {"dp_target": 85, "tcy_target": 90, "off_flow": ["M9"], "objetivos": {"tai_max": 0.2}}
    (tmp_path / "L_X.json").write_text(json.dumps(content), encoding="utf-8")
    t = LogicConfig.from_line_files(load_line_files(tmp_path)).targets("L_X")
    assert (t.dp_min, t.tcy_max_cmin, t.tai_max, t.required_h) == (0.85, 90, 0.2, 22.0)


def test_missing_time_is_filled_into_one_loss():
    from logic.robustness import fill_missing_time

    df = pd.DataFrame([machine("A", 1, 14.0, 0.8, 1.8, 1.0), machine("B", 2, 18.0, 1.0, 1.5, 1.5)])
    filled = fill_missing_time(df, "DES", LogicConfig()).set_index("Operacion")
    assert filled.loc["A", "DES"] == pytest.approx(1.8 + 22 - 17.6)
    assert filled.loc["B", "DES"] == pytest.approx(1.5)  # ya registra 22 h


@pytest.mark.skipif(not (CLEAN_DIR / "VLL_MONTAJE_L5" / "clean.csv").exists(), reason="sin la limpieza de Rol 1")
def test_leader_survives_every_robustness_scenario():
    from logic.config import load_line_files
    from logic.loaders import read_clean
    from logic.robustness import compare

    files = load_line_files()
    result = compare(read_clean(CLEAN_DIR), files, LogicConfig.from_line_files(files))
    assert len(result) == 7
    assert set(result["leader"]) == {"ST-0260"}
    assert result["leader_rank"].tolist() == [1] * 7


def test_unreliable_piece_counter_does_not_make_a_machine_slow():
    rows = [
        # Con el contador sustituto saldría Tcy 84: no se puede afirmar que sea lenta
        machine("A", 1, 21.0, 0.5, 0.3, 0.2, npr=1500, flags="contador_roto"),
        machine("A", 1, 21.0, 0.5, 0.3, 0.2, npr=1600, day="2026-09-30"),
        machine("B", 2, 21.0, 0.5, 0.3, 0.2, npr=1500, flags="contador_doble"),
    ]
    a = analyze(pd.DataFrame(rows))
    day = a.daily.set_index(["Operacion", "day"])
    assert math.isnan(day.loc[("A", DAY), "tcy_cmin"]) and math.isnan(day.loc[("A", DAY), "fpm"])
    assert day.loc[("A", DAY), "status"] == "ok"
    t = totals_of(a)
    assert t.loc["A", "tcy_cmin"] == pytest.approx(6000 * 21 / 1600)  # solo el día con contador fiable
    assert "no se mide su ciclo" in t.loc["B", "explanation"]


def test_statuses_use_the_official_names_and_labels():
    statuses = {st["id"]: st for st in analyze(pd.DataFrame(toy_line())).to_dict()["statuses"]}
    assert statuses["saturacion"]["label"] == "Saturación (SAT)"
    assert statuses["desabastecimiento"]["family"] == statuses["saturacion"]["family"] == "parada_inducida"
    assert statuses["parada_propia"]["label"] == "Parada propia (TAP)"


@pytest.mark.skipif(not (CLEAN_DIR / "VLL_MONTAJE_L5" / "clean.csv").exists(), reason="sin la limpieza de Rol 1")
def test_status_never_contradicts_the_stop_types():
    """stops/classify.py clasifica con más detalle y otro umbral de "ok". Donde los
    dos ven una pérdida tienen que coincidir en cuál, y lo que la lógica excluye él lo
    marca como error o sensor."""
    from stops import classify as stop_types
    from logic.status import EXCLUDED, STOP_TYPE_TO_STATUS

    theirs = stop_types.classify(stop_types.load_clean("VLL_MONTAJE_L5"), "VLL_MONTAJE_L5")
    mine = analyze(load_clean(CLEAN_DIR)).daily.rename(columns={"Operacion": "op", "day": "fecha"})
    both = theirs.merge(mine[["op", "fecha", "status"]], on=["op", "fecha"])
    assert len(both) == len(theirs) == len(mine)

    to_status = {stop_types.TIPOS[k]: v for k, v in STOP_TYPE_TO_STATUS.items()}
    losses = both[both["tipo"].isin(to_status) & both["status"].isin(to_status.values())]
    assert len(losses) > 600
    assert (losses["tipo"].map(to_status) == losses["status"]).all()
    excluded = both[both["status"].isin(EXCLUDED)]
    assert excluded["tipo"].isin([stop_types.TIPOS["error_registro"], stop_types.TIPOS["sensor"]]).all()
