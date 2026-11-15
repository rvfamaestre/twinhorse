# Material para la presentación

Estética: fondo blanco, texto casi negro, mucho aire y color solo para los estados (los mismos que en el 3D). Rojo = parada propia, ámbar = sin piezas, azul = bloqueada, gris = dato no fiable.

```bash
python slides/make_figures.py          # regenera figures/slides/*.png y *.pdf con los datos del repo
cd slides/latex && latexmk              # figures/slides/formulas.pdf y diagrams.pdf (un recorte por página), plataforma.pdf, logica.pdf y timesfm.pdf
for f in plataforma logica timesfm; do pdftoppm -r 300 -png -singlefile ../../figures/slides/$f.pdf ../../figures/slides/$f; done   # PNG para PowerPoint
```

Si no tienes el paquete `inter`, comenta su línea: sale con la tipografía por defecto.

## Guion propuesto (8 min)

| # | Título de la diapositiva | Visual |
| --- | --- | --- |
| 1 | La máquina que más se para no es la que más frena la línea | `figures/slides/01_paradoja` |
| 2 | Antes de contar paradas, hay que fiarse del dato | `figures/slides/02_antes_despues_limpieza` + `figures/slides/04_calidad_del_dato` |
| 3 | Un día de una máquina en cuatro estados | `formulas.tex`, páginas 1 y 2 |
| 4 | Lo que provocan las vecinas pesa 5 veces más | `figures/slides/03_inducida_vs_propia` + `figures/slides/05_mapa_estacion_dia` |
| 5 | Quién frena la línea: la regla de las flechas | `diagrams.tex`, página 2 + `formulas.tex`, página 5 |
| 6 | Un índice con desglose, nunca un número suelto | `figures/slides/07_indice_penalizacion` + `formulas.tex`, página 6 |
| 7 | De los datos a la decisión | `diagrams.tex`, página 1 |
| 8 | El gemelo: la línea viva, tramo a tramo | `figures/slides/08_gemelo_3d`, `figures/slides/09_gemelo_ficha_y_leyenda` y demo |
| 9 | Predecir lo normal para detectar lo raro | `figures/slides/06_prediccion_banda` + `formulas.tex`, páginas 8 y 9 |
| 10 | Hipótesis honestas: lo que deducimos y lo que falta confirmar | `diagrams.tex`, página 3 |
| 11 | El mismo criterio para cualquier línea | Sin visual: tres frases |

Vídeos de fondo para las diapositivas 1, 2, 3 a 6, 8 y 9 en `figures/video/`: guion y cómo regenerarlos en [`video/README.md`](video/README.md).

`formulas.tex` página 4 (tipo de parada) y página 7 (reconstrucción del día) sirven de apoyo si preguntan.
