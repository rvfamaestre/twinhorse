# Tipo de parada por máquina y día

Cada máquina y día productivo recibe un tipo por reglas fijas, sin modelo. Lee la limpieza del EDA (`data/processed/<línea>/clean.csv`), así que antes hay que ejecutar `eda/run_eda.py`.

```
python stops/classify.py --line VLL_MONTAJE_L5   # data/processed/<línea>/stops.csv y stops_resumen.csv
python stops/plots.py --line VLL_MONTAJE_L5      # stops/output/<línea>/STOPS.md y sus figuras
python -m pytest tests/test_stops.py
```

## Reglas

La primera que se cumple decide el tipo:

1. `error_registro`: la máquina no registra nada o está fuera de servicio.
2. `sensor`: más paradas propias que piezas con un contador creíble (NAP > NPR).
3. `error_registro`: contador de piezas roto o doble.
4. Si se pierde al menos 1 h (TAP + DES + SAT), manda la mayor: `saturacion` (SAT), `desabastecimiento` (DES), o, si es TAP, `microparada` (menos de 60 s por parada) o `parada_larga`.
5. `ok`: día sin pérdidas relevantes.

Los umbrales están en `classify.py` (`MICRO_S`, `PERDIDA_MIN_H`). Los subconjuntos y manipuladores solo cambian la columna `bloque`, y salen de `lines/<línea>.json` (`subassemblies` y `off_flow`).

La lógica de paradas (`backend/logic/status.py`) usa estados más gruesos. `STOP_TYPE_TO_STATUS` traduce estos tipos a sus nombres y un test comprueba en L5 que, donde las dos ven una pérdida, coinciden en cuál.

## Salidas

| Fichero | Qué es |
| --- | --- |
| `data/processed/<línea>/stops.csv` | Una fila por máquina y día: tipo, motivo, horas perdidas y segundos por parada |
| `data/processed/<línea>/stops_resumen.csv` | Días de cada tipo por máquina y su tipo más frecuente |
| `stops/output/<línea>/STOPS.md` | Informe (figuras en `figures/stops/<línea>/`) con el mapa máquina × día, los totales, el umbral de microparada y las paradas fuera de la banda de TimesFM (si existe el backtest de `forecast/`) |
