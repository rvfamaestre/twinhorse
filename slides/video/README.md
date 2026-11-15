# Vídeos para la presentación

Cinco vídeos cortos para poner de fondo mientras se habla, uno por bloque de la charla de 8 minutos. Son 1920×1080, 60 fps, H.264 y sin sonido. Cada uno termina quieto en su último fotograma, que también está en PNG por si el vídeo no carga.

| # | Vídeo (`figures/video/`) | Dura | Diapositivas | Qué se ve |
| --- | --- | --- | --- | --- |
| 1 | `01_paradoja.mp4` | 14 s | 1 | El ranking «se para más» se reordena al sumar lo que cada máquina hace perder a sus vecinas. ST-0260 pasa de 11 h a 186 h y ST-2390 cae al último puesto |
| 2 | `02_dato.mp4` | 15 s | 2 | Las 1.820 filas en una rejilla y la limpieza por niveles: 4 días sin producción (1.456), 7 manipuladores (1.344) y 3 estaciones sin dato fiable (1.296 entran en el ranking). En lo que queda, 145 filas reescaladas a 22 h y 32 con el contador de la línea |
| 3 | `03_propagacion.mp4` | 25 s | 3 a 6 | Una parada propia en ST-0260: cola y bloqueo antes, sin piezas después. Luego la regla de las flechas y el índice: 11 + 108 + 67 = 186 h |
| 4 | `04_gemelo.mp4` | 43 s | 8 | El dashboard real: vista general, los motores del día que estima TimesFM, «Frenan» y la ficha de ST-0260, histórico a ×600, la leyenda que enseña y el modo oscuro |
| 5 | `05_prediccion.mp4` | 15 s | 9 | TimesFM predice la semana de golpe. La banda p10–p90 es lo normal y el día que se sale (2,6 h) es un aviso |

Las diapositivas 7, 10 y 11 van sin vídeo.

Los números salen de los ficheros del repo (`scenes/data.json`, generado por `data.py`). No hay nada escrito a mano.

## En PowerPoint

1. Insertar → Vídeo → Este dispositivo. Así el vídeo queda dentro del `.pptx`.
2. En Reproducción, «Iniciar: automáticamente». Sin repetir: al acabar se queda en el último fotograma, que resume la diapositiva.
3. El vídeo 4 dura más que el resto. Si la demo en directo falla, este vídeo la sustituye.

## Regenerarlos

Hace falta Node 20 o superior, Google Chrome instalado y `ffmpeg` en el PATH.

```bash
python slides/video/data.py      # desde la raíz: números reales → slides/video/scenes/data.json
cd slides/video
npm install
node render.mjs                  # vídeos 1, 2, 3 y 5 → figures/video/
node capture_gemelo.mjs          # vídeo 4: antes, el frontend (npm run dev) y la API (python -m backend.api)
```

- `node render.mjs 03_propagacion --stills 4,12` saca PNG sueltos de esos segundos para revisar sin grabar.
- Para ver una escena en el navegador: `python -m http.server -d slides/video/scenes 8080` y abrir `http://localhost:8080/01_paradoja.html`. Se reproduce en bucle; con `?t=5` se queda en el segundo 5.

## Cómo están hechos

- **1, 2, 3 y 5** (`scenes/*.html`): SVG con la misma paleta, tipografía (Inter) y estados que el dashboard. Cada escena es una función pura del tiempo, `render(t)`, así que se graba fotograma a fotograma, en paralelo y sin saltos.
- **4** (`capture_gemelo.mjs`): el dashboard de verdad en Chrome, con un cursor dibujado encima. El reloj de la página es falso y las animaciones CSS se avanzan a mano, así que cada fotograma es exacto y el vídeo sale igual cada vez.
