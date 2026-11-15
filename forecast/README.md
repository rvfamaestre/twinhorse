# Predicción por línea (TimesFM 3.0)

```
pip install "timesfm[torch]"                                   # 3.0.2, CPU vale; pesos 1,3 GB la primera vez
python forecast/run_forecast.py backtest                       # compara modelos (unos 2 min en CPU)
python forecast/run_forecast.py backtest --solo-informe        # rehace el informe sin volver a predecir
python forecast/run_forecast.py predict --horizon 1            # mañana, para el dashboard
python forecast/run_forecast.py predict --horizon 5 --off 2026-10-30   # semana, con un día sin producción
python forecast/run_forecast.py predict --modelo timesfm       # forzar una variante (bandas de TimesFM)
python -m pytest tests                                         # sin descargar nada; RUN_TIMESFM=1 para probar el modelo real
```

Las tablas y los informes salen en `forecast/output/<línea>/` y las figuras en `figures/forecast/<línea>/`. Vale para cualquier línea, igual que el EDA: lee los datos con `backend/pipeline`.

## Ficheros

| Fichero | Qué es |
| --- | --- |
| `series.py` | Series por estación y métrica (TAP, DES, SAT) más las piezas al día de la línea, el calendario y las paradas largas |
| `model.py` | TimesFM 3.0 y las referencias (último valor y media), todos con los deciles p10 a p90 |
| `backtest.py` | Predice días ya conocidos y mide error, cobertura de la banda y series ganadas |
| `run_forecast.py` | Línea de comandos, informe `BACKTEST.md` y figura |

## Salidas

- `BACKTEST.md`: qué modelo gana en cada métrica, a un día y a la semana.
- `backtest_predicciones.csv`: cada predicción del backtest con sus deciles (p10 a p90) y el valor real. Las métricas usan p10, p50 y p90; las figuras pintan la banda en degradado con los intervalos centrales del 80, 60, 40 y 20 %, sin mediana. Con `escenario == "dia"` y `modelo == "timesfm"` están las bandas a un día vista de los 5 días de prueba.
- `forecasts.csv`: `op, fecha, metrica, p10, p50, p90, modelo`. Para cada métrica se usa la variante que ganó el backtest.
- `forecast.json`: lo mismo agrupado por estación, para el campo `forecast` del JSON del dashboard.
- `paradas_largas.csv`: estación-días con paradas de más de 5 min de media, posibles intervenciones planificadas.

## Variantes

| Variante | Qué usa |
| --- | --- |
| `ultimo_valor` | Mañana igual que hoy |
| `media` | Mañana como la media del contexto |
| `timesfm` | Solo la serie |
| `timesfm_calendario` | Más día de la semana, primer día tras una parada y víspera de parada |
| `timesfm_vecinas` | Más el TAP de la estación anterior (para DES) y de la siguiente (para SAT) |

Si dos variantes fallan dentro de un 1 % la una de la otra, gana la más simple.
