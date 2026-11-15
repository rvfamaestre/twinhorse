"""La API del dashboard con los datos de L5. Usa las referencias (media, último valor): no carga TimesFM."""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from backend import api
from forecast import series

pytestmark = pytest.mark.skipif(not series.ingest.RAW_DATA.exists(), reason="sin los CSV del reto")
client = TestClient(api.app)  # sin `with`: no arranca la carga de TimesFM


def test_options_list_the_line_and_its_stations():
    o = client.get("/api/forecast/options").json()
    assert o["series"][0]["id"] == series.LINE_ID
    assert len(o["dates"]) == 16 and len(o["series"]) > 80
    assert o["quantiles"] == ["p10", "p20", "p30", "p40", "p50", "p60", "p70", "p80", "p90"]


def test_forecast_from_a_past_day_brings_the_real_values():
    r = client.post("/api/forecast", json={"series": "ST-2390", "metric": "tap_h", "context": 8, "horizon": 5,
                                           "origin": "2026-10-15", "model": "media"}).json()
    assert len(r["context"]["dates"]) == 8 and r["context"]["dates"][-1] == "2026-10-15"
    assert r["forecast"]["dates"] == ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]
    assert r["known"] == 5 and 0 <= r["inside_80"] <= 5
    bands = [r["forecast"][f"p{k}"] for k in range(10, 100, 10)]
    assert all(lo <= hi for a, b in zip(bands, bands[1:]) for lo, hi in zip(a, b))


def test_forecast_beyond_the_data_skips_weekends():
    r = client.post("/api/forecast", json={"series": series.LINE_ID, "metric": "npr", "context": 16, "horizon": 3,
                                           "model": "ultimo_valor"}).json()
    assert r["forecast"]["dates"] == ["2026-10-26", "2026-10-27", "2026-10-28"]
    assert r["known"] == 0


@pytest.mark.parametrize("body, status", [
    ({"series": "ST-2390", "metric": "tap_h", "context": 30, "horizon": 3, "model": "media"}, 422),  # más historia de la que hay
    ({"series": "ST-2390", "metric": "tap_h", "context": 5, "horizon": 3, "origin": "2026-10-16", "model": "media"}, 422),  # día sin producción
    ({"series": "NO_EXISTE", "metric": "tap_h", "context": 5, "horizon": 3, "model": "media"}, 422),
    ({"series": "ST-2390", "metric": "tap_h", "context": 5, "horizon": 30, "model": "media"}, 422),
])
def test_bad_requests_are_explained(body, status):
    r = client.post("/api/forecast", json=body)
    assert r.status_code == status and r.json()["detail"]


def test_line_state_is_served_with_etag():
    first = client.get("/api/line")
    assert first.status_code == 200 and first.json()["meta"]["line"] == "VLL_MONTAJE_L5"
    again = client.get("/api/line", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304


def test_estimate_of_the_day_uses_only_what_was_known_the_day_before():
    r = client.get("/api/estimate", params={"day": "2026-10-23"}).json()
    assert r["day"] == "2026-10-23" and r["context_days"] == 15  # los 15 días productivos anteriores
    d = r["deciles"]
    assert d["p10"] <= d["p50"] <= d["p90"]
    ids = {f["id"] for f in r["factors"]}
    assert {"dia_semana", "tras_parada", "vispera_parada", "motores_previos", "tap_linea", "des_linea", "sat_linea"} <= ids
    assert r["actual"] == 1574  # el dato real, solo para comprobar
    assert client.get("/api/estimate", params={"day": "2026-10-16"}).status_code == 422  # día sin producción
    assert client.get("/api/estimate", params={"day": "2026-09-30"}).status_code == 422  # sin historia suficiente
