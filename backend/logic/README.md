# Lógica de paradas

Decide, para cada máquina y cada día, por qué se para y si frena la línea. Es Python determinista: con la misma entrada da siempre la misma salida, sin azar ni LLM. No contiene ningún nombre de máquina ni de línea. Los umbrales están en `config.py` y se pueden cambiar por línea.

Desde la raíz del repo:

```bash
python -m backend.logic --clean data/processed --out data/processed/logic/logic_state.json
python -m backend.logic.robustness --clean data/processed --out data/processed/logic/robustez.md
python -m pytest tests/test_logic.py
```

## Configuración por línea (`lines/<Linea>.json`)

Es el mismo fichero que usa la limpieza (`backend/pipeline/settings.py`). Una línea sin archivo funciona con los valores por defecto. Cualquier clave que no sea de la lógica ni de la limpieza da error.

| Clave | Qué es |
| --- | --- |
| `dp_target`, `tcy_target`, `required_h` | Objetivos de la línea, compartidos con la limpieza (`dp_target` en %) |
| `objetivos` | Campos de `Targets` que cambian, por ejemplo `{"tcy_max_cmin": 90}` |
| `tramos` | Topología confirmada: `{tramo: [operaciones]}`. Cada tramo es una cadena aparte en las flechas. Vacío = una sola cadena por `Orden_OP` |
| `hipotesis_tramos` | Topologías sin confirmar. Solo se usan como escenarios en la prueba de robustez |

## Prueba de robustez (`robustness.py`)

Cada escenario cambia una sola decisión respecto al base y lo recalcula todo:
- **Sin reescalar a 22 h:** las filas de más de 22 h, con sus horas originales.
- **Tiempo que falta:** en las filas cortas, el hueco hasta las 22 h se suma entero a la parada propia, a la falta de piezas o al bloqueo. Es el peor caso de cada lectura.
- **Hipótesis de tramos:** cada una de las que haya en `hipotesis_tramos`.

El informe dice si el top se mantiene, dónde queda el número 1 y qué máquinas cambian de veredicto.

`--clean` lee la limpieza de Rol 1: un `clean.csv`, o la carpeta `data/processed`, que trae uno por línea. Para trabajar sin limpieza, `--data data/raw/datos_hackaton.csv --config data/raw/config_hackaton.csv --provisional-clean` lee los CSV en bruto y solo quita los días no productivos.

## La limpieza de Rol 1 (`loaders.from_clean`)

| `clean.csv` | En la lógica |
| --- | --- |
| `tbf_h`, `tap_h`, `des_h`, `sat_h` (horas reescaladas) | `TBF`, `TAP`, `DES`, `SAT` |
| `npr_ef` (contador corregido) | `NPR` |
| `grupo` = `linea` | Flujo principal; `fuera_flujo` no entra en la cadena ni en el ranking |
| `paralelo` | `Paralelo`: la regla de Tcy se aplica a la estación entera (ver abajo) |
| `no_productivo` | Día descartado |
| `fuera_servicio` | `fuera_servicio` |
| `sin_datos`, `sensor_sospechoso`, `estacion_excluida` | `dato_no_fiable`, con el motivo |
| `contador_roto`, `contador_doble` | La fila vale para las horas, pero ese día no se miden Tcy ni Fpm, porque el contador es un sustituto |
| `tr_mayor`, `tr_menor` | Solo información: se copian a la salida |

## Entrada: una fila por máquina y día

| Columna | Obligatoria | Qué es |
| --- | --- | --- |
| `Linea`, `Operacion`, `Orden_OP` | sí | Identificación y orden en la línea |
| `day` | sí | Fecha ISO. `loaders.to_logic_input` la calcula a partir de `Year`, `Week` y `Jour` |
| `TBF`, `TAP`, `DES`, `SAT` | sí | Horas |
| `NAP`, `NPR` | sí | Paradas propias y piezas |
| `Planta` | no | Si falta, es el prefijo de la línea (`VLL_MONTAJE_L5` → `VLL`) |
| `Grupo` | no | Solo `principal` (el valor por defecto) entra en la cadena de las flechas y en el ranking. Los subconjuntos y manipuladores van con otro valor |
| `Paralelo` | no | Grupo en paralelo, por ejemplo `ST2376+ST-2375` |
| `flags` | no | Lista, o texto `a;b` |

Estos flags los entiende la lógica (los nombres se acuerdan con Rol 1):

| Flag | Efecto |
| --- | --- |
| `dia_no_productivo` | La fila se descarta |
| `fuera_servicio` | La máquina queda fuera de la cadena y del ranking ese día; las vecinas pasan a ser contiguas |
| `dato_no_fiable` | Igual que `fuera_servicio` |

El resto de flags no cambian el cálculo: solo se copian a la salida.

## Qué calcula

1. **KPIs** (`kpis.py`):
   - TR = TBF + TAP + DES + SAT
   - TAI = DES + SAT
   - Dp = TBF / (TBF + TAP)
   - Tcy = 6000·TBF / NPR
   - Fpm = 1000·NAP / NPR

   En los acumulados se suman primero las horas y después se calculan los ratios.

   En un grupo en paralelo, el Tcy es el de la estación entera: 6000 / Σ(NPR/TBF). El de cada máquina por separado se guarda en `tcy_machine`.
2. **Estado** (`status.py`), por este orden de prioridad:
   - `fuera_servicio` o `dato_no_fiable`;
   - `ok` si cumple Dp, Tcy y tiene poca parada inducida;
   - `lenta` si casi no se para pero su Tcy pasa del objetivo;
   - si no, la mayor de sus pérdidas, con los nombres oficiales del reto: `parada_propia` (TAP), `desabastecimiento` (DES) o `saturacion` (SAT). DES y SAT forman la parada inducida (TAI).

   En el JSON, `statuses` trae cada estado con su etiqueta oficial (por ejemplo, "Saturación (SAT)") y su familia (`parada_propia`, `parada_inducida`, `ciclo`, `ok`, `excluida`), para usarlos en la leyenda.

   La clasificación por tipo de parada (`stops/classify.py`) es más detallada y no se toca. `status.STOP_TYPE_TO_STATUS` traduce sus pérdidas a estos nombres: `microparada` y `parada_larga` son `parada_propia`; `desabastecimiento` y `saturacion` se llaman igual. Su `ok` usa otro umbral (1 h de pérdida) y su `error_registro` incluye el contador roto, así que no tienen equivalencia directa. Un test comprueba en L5 que, donde los dos ven una pérdida, coinciden en cuál.
3. **Regla de las flechas** (`arrows.py`, Kuo, Lim y Meerkov): para cada par de vecinas a → b, si SAT de a > DES de b la flecha es →; si no, ←. La máquina donde convergen las flechas es la que frena la línea. Se calcula para cada día y sobre el acumulado.
   - SAT y DES se comparan en % del **tiempo requerido**, no del registrado. Así, en una fila corta no se reparte el tiempo que falta. Es lo mismo que comparar horas, como hace `backend/pipeline/kpis.py`.
   - Un grupo en paralelo es **un solo nodo**: la media de sus máquinas, situado en la posición de la primera. En `arrows`, ese nodo aparece con su nombre (`ST2376+ST-2375`). Las horas que hace perder a sus vecinas se reparten entre sus máquinas.
   - La primera y la última máquina **también pueden** frenar la línea, como en el método original. Es la única diferencia con `backend/pipeline/kpis.py`; un test comprueba que en el resto coinciden.
4. **Índice de penalización** (`penalty.py`): IP = TAP + SAT de la anterior + DES de la siguiente. Los dos últimos términos solo cuentan los días en que la máquina frena la línea. Se entregan tres rankings: `penalizacion`, `se_para_mas` y `frena_linea`.
5. **Frase** (`explain.py`): plantilla fija que empieza por lo que más pesa.

## Salida (`Analysis.to_dict()`)

```
plants[] → lines[] → stations[] → sensors[]   (sensors vacío: sin datos todavía)
```

- **Cada línea** trae `targets`, `days`, `stations`, `arrows.total`, `arrows.daily[día]` y `ranking`.
- **Cada estación** trae `status`, `flags`, `kpi`, `penalty` (rank, desglose, días que frena), `explanation` y `daily[]`.
- **Unidades:** Dp y cuotas en %, horas y cmin con un decimal.

Para el 3D, `status` es el color. Que una máquina frene la línea es otra dimensión: `daily[].is_bottleneck` y `penalty.brakes_line_in_total`. Conviene pintarla por encima del color, porque una máquina puede frenar la línea y a la vez tener como mayor pérdida la falta de piezas (le pasa a ST-0260).
