# Plan de equipo · Reto LOSSIA

13 nov 2026

> Plan inicial, escrito al empezar el reto. Lo que se construyó al final (estructura, comandos y resultados) está en [USAGE.md](USAGE.md) y [RESULTS.md](RESULTS.md); por ejemplo, la API (`backend/api.py`) solo sirve la línea y la predicción al momento, y el JSON de la línea lo genera `frontend/scripts/build_mock.py`.

Construimos un gemelo digital isométrico de la línea L5 que dice, para cada máquina y cada día, si se para por sí misma, si la paran sus vecinas o si el dato no es fiable. Cuatro roles trabajan en paralelo sobre un contrato JSON fijado en la primera media hora, y el código se congela a las 14:30.

## Lo que dicen los datos

La máquina que más se para no es la que penaliza: el ranking ingenuo por parada propia (TAP) saca PM2130, ST2235, ManBM2_1, Ma_BM2_2 y MANOP749, que son fallos de dato o manipuladores. Tras limpiar, las que más se paran son ST-2390 (Dp 77,3 %, 393 paradas por cada 1.000 piezas, 68 h propias), PM2250 (Dp 85,0 %) y ST_0100 (Dp 89,6 %).

Las que frenan a sus vecinas son otras. Con la regla de las flechas (ver Rol 2), ST-0260 y ST-0830 frenan la línea los 16 días: ST-0260 deja a ST0259 saturada 108 h y ST-0830 deja a ST-0840 sin piezas 50 h. Esa diferencia entre «se para mucho» y «penaliza la línea» es el mensaje central del reto.

La tabla de datos tiene 1.820 filas: 91 operaciones × 20 días (semanas 40 a 43, de lunes a viernes). Hay una fila por máquina y día, no por semana como decía la diapositiva. Los tiempos están en horas y cada día requiere 22 h (24 h menos 2 h de pausas).

| Hallazgo | Riesgo si no se trata | Regla de limpieza |
| --- | --- | --- |
| 4 días sin producción con TAP = 22 h en las 91 máquinas: S40 lunes, S41 viernes, S42 lunes (12 de octubre) y S42 viernes | Cada máquina suma 88 h de parada propia falsa y la disponibilidad se hunde | Día no productivo si la mediana de TBF de la línea es 0. Se excluye. Quedan 16 días |
| 161 filas suman más de 22 h (máximo 26,4 h), casi todas en 15 máquinas (PM_0090, PM_0110, ST-0830, ST2135, ST2376…). Otras 73 filas no llegan a 20 h | TBF inflado, Tcy inflado: PM_0090 pasa de 81,8 a 76,7 cmin al corregir | Reescalar TBF, TAP, DES y SAT a 22 h y marcar la fila |
| PM2130: TBF = 0 y TAP = 22 h los 16 días | Sale como la peor máquina con 352 h | Fuera de servicio o by-pass: fuera del ranking, en gris en el 3D |
| ST2235: unas 22.000 paradas propias al día, 2.382 piezas al día (la línea hace unas 1.530) y Dp 20 % | Falsa alarma en lo más alto del ranking | Marcar «dato no fiable» si NAP > NPR o NPR > 1,3 × la mediana de la línea |
| Contadores rotos: ST_0030 todo a cero; ST-0295 cuenta 41 piezas en 16 días; Ma_BM1_2, Ma_VES_0, Ma_VESRE y ManBM2_1 trabajan sin contar piezas | Tcy y Fpm absurdos (ST-0295 sale con 44.404 cmin) | Si el contador falla, usar el NPR de la línea y marcar la fila |
| ST2376 y ST-2375 hacen unas 12.000 piezas cada una, la mitad que el resto. ST_3300 cuenta 41.124 (1,7 veces) | Parecen máquinas lentas (150 a 180 cmin) | Tratar ST2376 + ST-2375 como una estación doble. ST_3300: doble conteo, marcar |
| La configuración mezcla nombres (ST_0015, ST-0050, ST0261). ST0261 va antes que ST0259 y los bloques ST_0820–ST-0850 y ST_3100–ST_3300 van después de ST_2410 | Uniones fallidas y línea mal ordenada en el 3D | Unir por el nombre exacto. El orden lo da `Orden_OP`, nunca el número del nombre |

Con el Tcy corregido solo dos máquinas superan los 80 cmin: ST-0830 (82,0) y PM2110 (80,8). Son las candidatas a cuello de botella estructural, distintas de las que fallan por paradas.

## Arquitectura y contrato de datos

Todo el núcleo es Python determinista: mismas entradas, misma salida, sin azar. El 3D no calcula nada, solo pinta lo que le da la API. Así los cuatro roles trabajan en paralelo desde el minuto 30.

1. `ingest`: lee los dos CSV, une por Línea + Operación y valida columnas y tipos.
2. `clean`: aplica las reglas de la tabla anterior. Cada fila lleva su lista de flags.
3. `kpis`: Dp, Tcy, Fpm y TAI por máquina y día, y acumulados.
4. `logic`: clasifica cada máquina-día y calcula el índice de penalización con su desglose y su frase explicativa.
5. `forecast` y `whatif`: módulos aparte que leen la salida de `kpis`. Si fallan, el resto sigue funcionando.
6. `export`: escribe `data/processed/line_state.json`. FastAPI lo sirve y el frontend solo lee la API.

Stack: Python 3.11 con pandas y FastAPI; frontend con Vite, React, react-three-fiber y drei. Los días van como fecha ISO: `Jour` 1 es lunes, así que S40 lunes es 2026-09-28 y S42 lunes es 2026-10-12, el festivo.

Contrato (lo escriben Rol 1 y Rol 2 juntos en la primera media hora; Rol 3 arranca con una copia rellena a mano):

```json
{
  "meta": {"line": "VLL_MONTAJE_L5", "required_h": 22,
           "targets": {"tcy_cmin": 80, "dp_pct": 90},
           "days": ["2026-09-29", "2026-09-30"]},
  "stations": [{
    "op": "ST-2390", "order": 75,
    "group": "main | subassembly | manipulator",
    "parallel_with": null,
    "kpi": {"dp": 77.3, "tcy": 57.0, "fpm": 393, "tbf_h": 232.4,
            "tap_h": 68.3, "des_h": 34.9, "sat_h": 6.1},
    "status": "propia | inducida_anterior | inducida_siguiente | dato_no_fiable | fuera_servicio | ok",
    "flags": [],
    "penalty": {"rank": 1, "own_h": 68.3, "induced_on_neighbours_h": 0.0},
    "explanation": "ST-2390 pierde 68 h por paradas propias...",
    "daily": [{"day": "2026-09-29", "tbf": 0, "tap": 0, "des": 0,
               "sat": 0, "npr": 0, "status": "ok"}],
    "forecast": {"metric": "tap_h", "days": [], "p10": [], "p50": [], "p90": []}
  }],
  "ranking": ["ST-2390", "PM2250", "ST_0100"]
}
```

Endpoints: `GET /api/line`, `GET /api/station/{op}`, `GET /api/ranking` y `POST /api/whatif` con `{op, dp_target}`.

## Reparto en cuatro roles

Backend y lógica van separados: Rol 1 deja los datos limpios y servidos, Rol 2 decide qué significa cada parada. Rol 1 termina antes porque el dataset es pequeño, así que se queda con las diapositivas desde las 13:00.

| Rol | Responsable de | Entrega | A quién y cuándo |
| --- | --- | --- | --- |
| 1 · Datos y backend | ingest, clean, export, API y diapositivas | `clean.parquet` con flags, `line_state.json` y API | A Rol 2 en H+1:30; a Rol 3 a las 13:30 |
| 2 · Lógica de paradas | KPIs, propia frente a inducida, índice de penalización y frases | Campos `kpi`, `status`, `penalty` y `explanation` | A Rol 1 en H+3:00 |
| 3 · Dashboard 3D | Escena isométrica, interacción, panel de detalle y vídeo de respaldo | Web que lee la API | Demo cerrada a las 14:30 |
| 4 · Predicción y simulación | forecast, whatif, coordinación y ensayos | Campo `forecast`, `/api/whatif` y el backtest | A Rol 1 en H+3:30 |

H+0 es la hora a la que empezáis a programar.

### Rol 1 · Datos y backend

- [x] Repo con `backend/`, `frontend/`, `data/raw` y `data/processed`; una rama por rol y `main` siempre arranca.

  Ordenado para la entrega (commit `5f0436a`, 14 nov): datos del reto en `data/raw/`, tipo de parada en `stops/`, un solo `tests/` (`python -m pytest`, 60 pruebas), una sola configuración por línea en `lines/` y todos los comandos desde la raíz. Sin nombres del equipo en los ficheros y sin la presentación del reto.

- [x] Contrato JSON con Rol 2 y un `line_state.mock.json` para Rol 3, en los primeros 30 minutos.
- [x] `ingest.py`: leer los CSV, unir con la configuración y comprobar que salen 91 operaciones y 20 días.
- [x] `clean.py`: una función por regla de la tabla de hallazgos, cada una con su comprobación (por ejemplo, «tras limpiar quedan 16 días»).
- [x] Tabla de calidad del dato: cuántas filas toca cada regla. Va tal cual a una diapositiva.
- [ ] `export.py` y FastAPI con los cuatro endpoints y CORS abierto para el frontend. Hecho en parte: `backend/api.py` sirve `/api/line` (el JSON de `frontend/scripts/build_mock.py`) y `/api/forecast` (predicción al momento); sin `/api/station`, `/api/ranking` ni `/api/whatif`.
- [ ] Desde las 13:00, diapositivas: un mensaje por diapositiva, capturas del 3D y la tabla de calidad. Material en `slides/`: figuras, capturas del 3D, fórmulas y guion.

### Rol 2 · Lógica de paradas

Las fórmulas salen de la presentación del reto (1 h = 6.000 cmin):

```math
Dp = \frac{TBF}{TBF + TAP} \geq 90\,\% \qquad T_{cy} = \frac{6000 \cdot TBF}{NPR} \leq 80\ \text{cmin} \qquad F_{pm} = 1000 \cdot \frac{NAP}{NPR} \qquad TAI = DES + SAT
```

- [x] KPIs por máquina y día y acumulados, sobre los datos limpios de Rol 1.
- [x] Estado de cada máquina-día, en este orden: `fuera_servicio`, `dato_no_fiable` y, si no, la mayor de las tres pérdidas. TAP da `propia`, DES da `inducida_anterior` (le faltan piezas) y SAT da `inducida_siguiente` (no puede soltar la pieza). `ok` si Dp ≥ 90 % y las pérdidas quedan bajo un umbral fijo que se enseña en la diapositiva.
- [x] Regla de las flechas (Kuo, Lim y Meerkov, para líneas en serie), día a día: la estación i frena la línea si SAT de la anterior > DES de i y DES de la siguiente > SAT de i. Contar en cuántos de los 16 días se cumple.
- [x] Vecinas reales: saltar las estaciones fuera de servicio o con dato no fiable, juntar ST2376 + ST-2375 y tratar aparte los subconjuntos (ST_0820–ST-0850, ST_3100–ST_3300) y los manipuladores.
- [x] Índice de penalización = horas propias (TAP) + horas que hace perder a sus vecinas (SAT de la anterior + DES de la siguiente) los días que cumple la regla. Siempre con su desglose, nunca un número suelto.
- [x] Falsas alarmas a flags, fuera del ranking: sensor (NAP > NPR), contador roto y reloj de más de 22 h.
- [x] Frase por plantilla, sin LLM. Ejemplo: «ST-2390 pierde 68 h propias en 16 días (Dp 77 %, objetivo 90 %). Se para 393 veces cada 1.000 piezas, unos 25 s cada vez: son microparadas, no averías largas.»
- [x] Prueba de robustez: el top 3 debe salir igual con y sin la reescala a 22 h. Si cambia, se cuenta en la presentación.

Dos cosas a revisar primero. ST-0260 registra unas 17,9 h al día, así que le faltan 4 h: confirmar con Rol 1 antes de señalarla. ST-2390 no cumple la regla en acumulado porque también pasa 35 h sin piezas: hay que mirarla día a día.

### Rol 3 · Dashboard 3D isométrico

- [x] Escena en react-three-fiber con cámara ortográfica en vista isométrica (45° de giro, unos 35° de inclinación), zoom y solo cuatro giros fijos.
- [x] Una caja por estación en el orden de `Orden_OP`, en serpiente (filas de unas 15) unidas por una cinta. Subconjuntos y manipuladores como ramas laterales; ST2376 y ST-2375 lado a lado. Es un esquema por orden, no el plano real de la nave, y se dice así en la demo.
- [ ] Color según `status`: rojo parada propia, ámbar sin piezas (DES), azul bloqueada (SAT), verde ok y gris rayado para dato no fiable o fuera de servicio. La altura de la caja es la pérdida en horas.
- [ ] Deslizador de los 16 días y botón de acumulado.
- [x] Clic en una estación: panel con KPIs frente a objetivo, la frase de `explanation`, gráfico diario y la banda de predicción si existe.
- [ ] Ranking de penalizantes al lado; al pasar el ratón se ilumina la estación en el 3D.
- [ ] Flechas de la regla de Rol 2 sobre la cinta, apuntando a la estación que frena.
- [ ] Plan B si a las 12:00 el 3D no avanza: la misma línea en SVG con transformación isométrica. No hizo falta.
- [ ] A las 14:30, grabar un vídeo de 60 s de la demo por si falla el directo.

### Rol 4 · Predicción y simulación

- [ ] Coordinar: cinco minutos de puesta en común cada hora y cortar lo que no vaya a llegar.
- [x] Backtest de predicción (detalle en la sección siguiente): contexto S40–S42, predecir S43 y comparar con dos referencias ingenuas.
- [x] Banda de normalidad p10–p90 por estación para TAP y DES. Un día fuera de banda es una alerta en el 3D.

  Con TimesFM 3.0 en lugar de Chronos-2. Los avisos del 3D usan la banda de TAP.

- [ ] What-if: «si ST-2390 sube a Dp 90 %, ¿cuántos motores más al día?». Horas propias recuperadas por piezas por hora, con techo en la estación más lenta: 22 h a 82 cmin (ST-0830) dan unos 1.610 motores al día frente a los 1.530 actuales. No se hizo.
- [ ] Entregar el campo `forecast` y `/api/whatif` a Rol 1 en H+3:30. El campo `forecast` sí; `/api/whatif` no se hizo.
- [ ] Ensayos con cronómetro: dos pasadas completas antes de las 15:15.

## Predicción de series temporales

Sí, pero como módulo de alerta y no como núcleo. Cada máquina tiene solo 16 días productivos, y con tan poca historia un modelo preentrenado casi no puede ganar a «mañana como la media». Lo que sí aporta es una banda de normalidad y una predicción condicionada a las vecinas.

Modelo: Chronos-2 de Amazon, con 120 M de parámetros y licencia Apache-2.0. Funciona sin entrenar, acepta covariables pasadas y futuras, aprende de un grupo de series a la vez y corre en CPU. La alternativa es TimesFM 3.0 de Google (septiembre de 2026), también con covariables, pero sus pesos son de uso no comercial: valen para el hackathon, no para llevarlos a planta.

1. Una serie por estación y métrica (TAP, DES, SAT y Dp), indexada por día productivo del 1 al 16. Se quitan los festivos y se ponen fechas seguidas para que el modelo no vea huecos.
2. Condicionada: DES de una estación con el TAP de la anterior como covariable, y SAT con el TAP de la siguiente. Responde a «si mi vecina se para más, ¿cuánto me llega a mí?», que es justo la parada inducida del reto.
3. Backtest honesto: contexto S40–S42 (11 días), predecir los 5 días de S43 y medir el error absoluto medio frente al último valor y frente a la media. Si no gana, se cuenta en la presentación.
4. En el dashboard: banda p10–p90 en el panel de cada estación. Si el valor real del día se sale de la banda, la estación parpadea.
5. Determinismo: Chronos-2 devuelve cuantiles directamente, sin muestreo, así que la misma entrada da la misma salida. Se calcula una vez y se guarda en el JSON; el dashboard nunca ejecuta el modelo.
6. Escalabilidad: si llegan los datos por evento de los 3 GB, el mismo módulo da predicciones por hora sin cambiar el código.

```python
# pip install "chronos-forecasting>=2.0"
from chronos import Chronos2Pipeline

pipe = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
pred = pipe.predict_df(
    ctx,                 # op, day, des_h y la covariable tap_prev_h
    prediction_length=5,
    quantile_levels=[0.1, 0.5, 0.9],
    id_column="op", timestamp_column="day", target="des_h",
)
```

## Ideas

Las cuatro primeras son la demo mínima. Si a las 13:30 están hechas, se suman las siguientes; si no, no se empieza nada nuevo.

| Idea | Qué enseña al jurado | Quién | Prioridad |
| --- | --- | --- | --- |
| Línea 3D con semáforo por estación y deslizador de días | Dónde se pierde el tiempo, de un vistazo | Rol 3 | Imprescindible |
| Ranking «se para mucho» frente a «frena la línea», lado a lado | El mensaje del reto en una imagen | Rol 2 | Imprescindible |
| Ficha «¿por qué se paró?» con frase por plantilla | Se entiende sin conocer el proceso | Rol 2 y Rol 3 | Imprescindible |
| Capa de calidad del dato: estaciones no fiables en gris rayado, con el motivo | La calidad del EDA, visible en la demo | Rol 1 y Rol 3 | Imprescindible |
| Flechas de bloqueo animadas: la parada viaja hacia atrás (SAT) y hacia delante (DES) | Parada propia frente a inducida, sin palabras | Rol 3 | Si da tiempo |
| What-if: mover la Dp de una estación y ver los motores al día que se ganan | Dónde conviene intervenir | Rol 4 | Si da tiempo |
| Banda de predicción y alerta de día anómalo | Aviso antes de que pase | Rol 4 | Si da tiempo |
| Dos vistas: jefe de unidad (ranking y horas) y mantenimiento (Fpm, segundos por parada, falsas alarmas) | El mismo criterio para dos perfiles, como pide el reto | Rol 3 | Extra |
| Mapa de calor estación × día y Pareto de horas perdidas | Patrones por día de la semana | Rol 1 | Extra |
| Informe PDF de una página por estación | Algo que el jefe de unidad se lleva a la reunión | Rol 1 | Extra |
| Preguntas en lenguaje natural sobre lo ya calculado: el LLM solo redacta, nunca calcula | Acceso para perfiles no técnicos | Rol 4 | Extra |

## Calendario hasta las 15:30

El código se congela a las 14:30 para tener una hora de ensayo. Cada hora en punto, cinco minutos de puesta en común que lleva Rol 4.

1. H+0:00 a H+0:30, todos: repo, ramas, contrato JSON y mock. Nadie programa lógica antes de tener el contrato.
2. H+1:30: Rol 1 entrega los datos limpios con flags. Rol 3 tiene la línea 3D pintando el mock.
3. H+3:00: Rol 2 entrega estados, ranking y frases. Rol 4 tiene el backtest.
4. 12:00: se decide si sigue el 3D o se pasa al plan B en SVG.
5. 13:00: Rol 1 pasa a las diapositivas.
6. 13:30: integración, el 3D lee la API real. Se corta lo que no esté entre las cuatro ideas imprescindibles.
7. 14:30: código congelado, solo arreglos. Vídeo de respaldo grabado.
8. 14:30 a 15:15: dos ensayos completos con cronómetro.
9. 15:30: entrega.

## Guion de la presentación (8 minutos)

La demo ocupa casi tres minutos porque es lo que más se recuerda. Cada bloque lo cuenta una persona distinta y nadie lee la diapositiva.

1. 0:00 a 0:45, el problema: hoy cada analista llega a una conclusión distinta. Gancho: «la máquina que más se para no es la que más penaliza».
2. 0:45 a 2:00, EDA: los 4 días sin producción codificados como parada, las 15 máquinas con más de 22 h al día y los contadores rotos. Diapositiva del ranking antes y después de limpiar.
3. 2:00 a 3:15, método: KPIs del reto, parada propia frente a inducida, regla de las flechas e índice con desglose. Todo determinista.
4. 3:15 a 6:00, demo del 3D: una máquina que se para mucho (ST-2390), una que frena la línea (ST-0830 o ST-0260) y una falsa alarma (ST2235). Si falla el directo, el vídeo.
5. 6:00 a 7:00, predicción y what-if, con el resultado del backtest tal como salga.
6. 7:00 a 8:00, valor y siguiente paso: el mismo criterio para todas las plantas, módulos que se cambian por separado y preparado para datos por evento.

## Preguntas abiertas para la organización

La primera cambia el alcance, así que hay que preguntarla en la primera media hora.

- [ ] Las notas hablan de unos 3 GB (fotos, vibraciones, atornilladores), pero en la carpeta solo está la tabla diaria de 1.820 filas. ¿Hay más datos? Si no, el análisis de vibraciones queda fuera.
- [ ] ¿PM2130 está fuera de servicio o en by-pass?
- [ ] ¿ST2235 registra microparadas reales o es un sensor que rebota?
- [ ] ¿Las 22 h diarias ya descuentan las pausas? ¿Por qué hay filas de hasta 26,4 h?
- [ ] ¿El orden de la configuración es el flujo físico? ¿Qué son los bloques ST_0820–ST-0850 y ST_3100–ST_3300 que van después de ST_2410?
- [ ] Las notas dicen 3.000 motores al día y los datos dan unos 1.530 por estación. ¿Hay otra línea u otro dato que no vemos?
- [ ] ¿Hay un plano de la nave para que el 3D respete la disposición real?
