# Dashboard 3D · Rol 3

Gemelo digital isométrico de la línea. Lee el contrato JSON (`src/contract/types.ts`) y no calcula nada del negocio: pinta lo que manda la API.

```bash
cd frontend
npm install
npm run mock      # genera public/mock/line_state.mock.json desde los datos limpios del EDA
npm run dev       # http://localhost:5173
```

En otra terminal, desde la raíz del repo: `python -m backend.api` (sirve la línea en `/api/line` y calcula la predicción).

`npm run mock` necesita el entorno Python del repo activado (ver [docs/USAGE.md](../docs/USAGE.md)). `npm run sim:check` compara el día reconstruido con los totales reales.

## De dónde lee

`VITE_DATA_SOURCE` (ver `.env.example`):

| Valor | Qué hace |
| --- | --- |
| `auto` (por defecto) | Prueba `/api/line`; si no responde, enseña el mock y sigue probando cada 30 s. Cambia solo cuando la API arranca. |
| `api` | Solo la API real. Es lo que usa la imagen de producción. |
| `mock` | Solo el mock. |

En local, Vite reenvía `/api` a `http://localhost:8000`, donde escucha `python -m backend.api` (FastAPI), así que la API no necesita CORS. La pantalla de predicción solo funciona con la API: el navegador no ejecuta ningún modelo.

## Cómo está hecho

```
src/
  contract/   tipos del contrato y validación (si la API manda algo raro, sale un aviso y se pinta lo demás)
  data/       fuentes intercambiables (api, mock) y sondeo con ETag y reintentos
  domain/     grafo de la línea, planta (posiciones), tramos, estados y avisos: puro, sin React
  sim/        reconstrucción determinista del día a partir de los totales diarios (pulmones finitos, max-plus)
  scene/      escena 3D: modelos hechos por código, piezas móviles, cámara isométrica por tramos
  state/      reloj (ahora / histórico), pantalla (planta / predicción), navegación y avisos leídos
  ui/         cabecera, barra de tiempo, leyenda animada, ficha de estación y panel de avisos
```

- **Flujo vivo:** los palés avanzan por las cintas; una máquina parada acumula cola detrás y deja hueco delante. No es un vídeo: se calcula el estado de cada máquina en cada instante con la simulación del día, que reproduce las paradas propias y los motores reales de ese día.
- **Ahora** reconstruye el último día con datos a la hora actual; **histórico** permite elegir día, reproducir a ×1–×600 y saltar a una hora.
- **Predicción** (`#prediccion` en la URL): serie, contexto, horizonte, día de origen y modelo (TimesFM 3.0, media o último valor). La banda se pinta con los deciles en degradado, sin mediana, y si el horizonte cae en días con datos marca los que se salen del 80 %.
- **Estética:** blanco, tinta casi negra y un solo gris; el color queda para los estados. Sin sombras ni tarjetas flotantes, solo líneas finas. Tipografía Inter servida con el bundle (`@fontsource-variable/inter`).
- **Leyenda que enseña** (en «?»): al pulsar un estado se explica con una mini animación y la planta ilumina solo las máquinas en ese estado.
- **Recta o serpenteada** (`domain/layout.ts`, `snakeLayout`): la misma planta doblada en filas. Dobla por huecos entre dos estaciones sueltas sin pulmón ni rama que los cruce. La simulación usa siempre la planta recta y las piezas se colocan en la dibujada, así que los números no cambian con la forma. `npm run snake:check` lo comprueba con el mock.
- **Motores del día en «Ahora»:** estimación de TimesFM con covariables (`GET /api/estimate`, `backend/api.py`): calendario del día y, de los días anteriores, motores y horas de parada, sin piezas y bloqueada de la línea. Lo hecho hasta la hora que se mira es ese total al ritmo de la reconstrucción. En una comparación sobre los 11 días con al menos 5 de historia, todas las opciones fallan unos 30 motores de media (un 2 %): con 16 días, las covariables apenas mejoran la media simple y la banda p10–p90 sale estrecha.
- **Logos de HORSE y de la Cátedra de Industria Inteligente (Comillas ICAI)** en carteles de la pared del fondo (`public/brand/`), alternados cada 28 m. El de HORSE es el SVG de su web; el de la cátedra, recortado de la portada de su memoria anual 2025 y pasado a blanco sobre transparente, que el cartel pinta sobre azul ICAI (#014593, `ICAI_BLUE` en `scene/Scene.tsx`).
- **Modo oscuro:** tokens CSS en `html[data-theme="dark"]` y colores de la nave en `scene/palette.ts` (`ENV`).
- **Idiomas** (`src/i18n/`): español, inglés y francés, con las mismas claves en los tres diccionarios (TypeScript avisa si falta una). Los números y los días de la semana siguen el idioma (`domain/format.ts`). Los avisos llegan en español desde el backend; en inglés y francés se componen en el navegador con sus datos (tipo, máquina, día, horas). Las banderas son SVG propios (`ui/flags.tsx`): Windows no pinta los emojis de bandera.

- Nada lleva nombres de estación escritos: el layout sale de `order`, `group`, `parallel_with` y `branch`. Otra línea funciona igual.
- Navegación: `←/→`, los bordes de la escena o un arrastre largo (o deslizar dos dedos en horizontal) cambian de tramo; con zoom de cerca el arrastre es libre. `V` abre la vista general, `espacio` pausa el histórico y `Esc` cierra lo último abierto. La rueda, deslizar en vertical o pellizcar hacen zoom hacia el puntero, proporcional al gesto. Lo que se mueve a mano no se deshace al abrir paneles.
- Avisos: icono sobre la máquina (relleno si no se ha leído), y panel con filtros por gravedad, tipo, tramo, estación, día y leídos.

## Campos que el Rol 3 propone añadir al contrato

Son opcionales: sin ellos el dashboard funciona, pero se ve menos.

| Campo | Para qué |
| --- | --- |
| `daily[].blocks_line`, `daily[].induced_h` | Flechas y anillo de «frena la línea» día a día |
| `penalty.blocking_days`, `penalty.blocked_neighbours` | A quién frena y cuántos días |
| `ranking_own` | Ranking «se para mucho» al lado del de penalización |
| `meta.generated_at` | Saber si hay datos nuevos y avisar de lo que cambia |
| `meta.excluded_days`, `quality` | Capa de calidad del dato y días sin producción en la línea de días |
| `daily[].flags`, `kpi.s_per_stop` | Vista de mantenimiento |
| `uvt`, `branch` | Agrupar por UVT y separar subconjuntos cuando la planta lo confirme |
| `forecast.model` | Decir qué modelo hizo la banda (TimesFM, prueba…) |
| `alerts` | Avisos ya decididos por el backend (gravedad, tipo, estación, día). El dashboard solo los filtra, ordena y marca como leídos |
| `topology` | Por dónde van las piezas (paralelos, entradas laterales, subconjuntos, pulmones). Es una hipótesis deducida de los datos |

## Despliegue privado en Google Cloud

1. Dos servicios de Cloud Run: este (`Dockerfile`, puerto 8080, nginx sin privilegios) y la API de FastAPI. Los dos con `--no-allow-unauthenticated` y `--ingress internal-and-cloud-load-balancing`.
2. Un balanceador HTTPS externo con NEG serverless: `/api/*` a la API y el resto al dashboard. Mismo origen, sin CORS.
3. Identity-Aware Proxy en el balanceador, abierto solo a las cuentas de Google Workspace de la empresa. El navegador no guarda claves ni tokens.
4. Región en la UE (por ejemplo `europe-southwest1`, Madrid) para que los datos de planta no salgan de Europa.

La imagen no publica el mock y el nginx manda CSP estricta: el navegador solo habla con su propio origen. El bundle no llama a ningún servicio externo, ni fuentes, ni CDN, ni analítica.
