"""Comprobaciones de stops/classify.py: una por regla con filas inventadas y unas pocas sobre L5."""

import pandas as pd
import pytest

from stops import classify as stops
from stops.classify import TIPOS

FLAGS = ["no_productivo", "sin_datos", "fuera_servicio", "sensor_sospechoso",
         "contador_roto", "contador_doble", "tr_mayor", "tr_menor"]


def row(op="ST_A", tap=0.0, des=0.0, sat=0.0, nap=0, npr=1500, **flags):
    r = {"Operacion": op, "fecha": pd.Timestamp("2026-09-29"), "Orden_OP": 1, "grupo": "linea",
         "tap_h": tap, "des_h": des, "sat_h": sat, "NAP": nap, "NPR": npr}
    r.update({f: flags.get(f, False) for f in FLAGS})
    return r


def tipo_of(**kw) -> str:
    df = pd.DataFrame([row(**kw)])
    return stops.classify(df, "LINEA_TEST")["tipo"].iloc[0]


def test_sin_registro_es_error():
    assert tipo_of(fuera_servicio=True, tap=22) == TIPOS["error_registro"]
    assert tipo_of(sin_datos=True) == TIPOS["error_registro"]


def test_sensor_gana_a_contador_doble():
    assert tipo_of(sensor_sospechoso=True, contador_doble=True, tap=3, nap=20000) == TIPOS["sensor"]


def test_fuera_servicio_gana_a_sensor():
    assert tipo_of(fuera_servicio=True, sensor_sospechoso=True) == TIPOS["error_registro"]


def test_contador_roto_es_error():
    assert tipo_of(contador_roto=True, des=5) == TIPOS["error_registro"]


def test_perdida_dominante():
    assert tipo_of(sat=3, des=1) == TIPOS["saturacion"]
    assert tipo_of(des=3, sat=1) == TIPOS["desabastecimiento"]


def test_tap_corto_es_microparada_y_largo_parada_larga():
    assert tipo_of(tap=2, nap=400) == TIPOS["microparada"]  # 18 s por parada
    assert tipo_of(tap=2, nap=10) == TIPOS["parada_larga"]  # 720 s por parada
    assert tipo_of(tap=2, nap=0) == TIPOS["parada_larga"]  # sin paradas contadas


def test_microparada_exige_que_tap_domine():
    assert tipo_of(tap=1, nap=400, des=4) == TIPOS["desabastecimiento"]


def test_pocas_perdidas_es_ok():
    assert tipo_of(tap=0.3, des=0.3, nap=50) == TIPOS["ok"]


def test_tr_mayor_se_clasifica_y_se_marca():
    out = stops.classify(pd.DataFrame([row(sat=3, tr_mayor=True)]), "LINEA_TEST").iloc[0]
    assert out["tipo"] == TIPOS["saturacion"] and out["marcas"] == "tr_mayor"


def test_rechaza_dias_no_productivos():
    with pytest.raises(ValueError):
        stops.classify(pd.DataFrame([row(no_productivo=True)]), "LINEA_TEST")


# --- Sobre los datos reales de L5 ----------------------------------------------------------

L5 = "VLL_MONTAJE_L5"


@pytest.fixture(scope="module")
def l5():
    if not (stops.PROCESSED / L5 / "clean.csv").exists():
        pytest.skip("falta clean.csv: ejecutar antes eda/run_eda.py")
    return stops.classify(stops.load_clean(L5), L5)


def test_l5_dias_y_estaciones(l5):
    assert l5["fecha"].nunique() == 16 and l5["op"].nunique() == 91 and len(l5) == 91 * 16
    assert not {"2026-09-28", "2026-10-09", "2026-10-12", "2026-10-16"} & set(l5["fecha"])


def test_l5_casos_conocidos(l5):
    tipos = l5.groupby("op")["tipo"].agg(lambda t: set(t))
    assert tipos["PM2130"] == {TIPOS["error_registro"]}
    assert tipos["ST2235"] == {TIPOS["sensor"]}
    assert tipos["ST_0030"] == {TIPOS["error_registro"]}
    assert tipos["ST-2390"] == {TIPOS["microparada"]}
    assert set(l5.loc[l5["tipo"] == TIPOS["sensor"], "op"]) == {"ST2235"}


def test_l5_bloques(l5):
    b = l5.groupby("op")["bloque"].first()
    assert (b == "subconjunto").sum() == 7 and (b == "manipulador").sum() == 7
