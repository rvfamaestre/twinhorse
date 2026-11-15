# EDA por línea

```
python eda/run_eda.py                          # todas las líneas del CSV
python eda/run_eda.py --line VLL_MONTAJE_L5    # solo una
python eda/run_eda.py --data otra.csv --config otra_config.csv
python -m pytest tests                         # comprueba el pipeline con una línea inventada
```

Por cada línea sale `eda/output/<línea>/EDA.md`, sus 6 figuras en `figures/eda/<línea>/` y las tablas limpias en `data/processed/<línea>/`.
Solo hace falta pandas y matplotlib.

## Añadir una línea nueva

1. Meter sus filas en la tabla de datos y su orden en la de configuración (mismas columnas que ahora). Si los datos son semanales y no traen `Jour`, también vale.
2. Ejecutar `python eda/run_eda.py --line <línea>`. Sin configurar nada ya funciona.
3. Si hace falta, crear `lines/<línea>.json` con lo que solo sabe la planta. Cualquier campo de `LineSettings` en `backend/pipeline/settings.py` se puede pisar:

```json
{
  "dp_target": 90,
  "tcy_target": 80,
  "off_flow": ["Manipulador_1"],
  "parallel_groups": [["ST_A", "ST_B"]],
  "subassemblies": ["ST_X1", "ST_X2"]
}
```

El mismo fichero lleva los tramos de la lógica de paradas (`tramos`, `hipotesis_tramos`, ver `backend/logic/README.md`).

## Qué se deduce solo y qué se configura

| Se deduce de los datos | Se configura en `lines/<línea>.json` |
| --- | --- |
| Tiempo requerido por periodo (el TR que más se repite, 22 h en L5) | Objetivos de Dp y Tcy (por defecto 90 % y 80 cmin) |
| Días sin producción | Estaciones fuera del flujo principal |
| Grupos de estaciones en paralelo | Grupos en paralelo, si la detección no basta |
| Fuera de servicio, sensor, reloj y contadores raros | Umbrales de cada regla |
|  | Subconjuntos que se montan aparte (solo agrupan los informes) |

El código no tiene ningún nombre de estación escrito. Todo lo que es de L5 está en `lines/VLL_MONTAJE_L5.json`.
