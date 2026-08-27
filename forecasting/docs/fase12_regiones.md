# Fase 12 — Bloques por REGIÓN administrativa de Tamaulipas (con halo)

Primer experimento a escala de región. Responde a la pregunta operativa que dejó la
fase 11: el estado entero no cabe en RAM, ¿cómo se parte y cuánto se pierde al partir?

## Por qué no se puede entrenar el estado entero

Curva medida en la Ubuntu (RTX 4090, 125 GB), feature-set de exp07 v4, cuatro puntos
reales — 144 / 300 / 500 / 1000 nodos:

| nodos | filas | tiempo | pico RAM |
|---|---|---|---|
| 144 | 6.3 M | 29 s | 10.0 GB |
| 300 | 13.2 M | 62 s | 18.4 GB |
| 500 | 21.9 M | 101 s | 30.2 GB |
| 1000 | 43.8 M | 209 s | 60.9 GB |

Ajuste lineal casi perfecto (**R² = 0.9995**):

```
tiempo ≈ 0.21 s × N        pico RAM ≈ 0.060 GB × N
```

Extrapolado a los 4384 nodos: **~263 GB** y 15 min. El tiempo es irrelevante; la RAM
es el muro. Con 119 GB disponibles el techo práctico está en ~1900 nodos.

## Por qué regiones y no bloques arbitrarios

Las 6 regiones oficiales del estado (Gobierno de Tamaulipas — 43 municipios) dan una
partición con significado administrativo, útil para reportar resultados a terceros, y
de tamaño manejable. La asignación nodo→región está en
`Data/Tamaulipas/regiones_tamaulipas.csv`, generada por `Utils/asignar_regiones.py`
con polígonos de OSM (origen `INEGI MGN 2014 v6.2`), filtrando por el prefijo `28` de
`INEGI:MUNID` — filtrar por nombre daría falsos positivos, porque Victoria,
Bustamante, Aldama, Camargo o Jiménez existen también en estados vecinos.

| región | municipios | nodos | +halo r3 | pico RAM est. |
|---|---|---|---|---|
| **Centro** (Victoria) | 13 | **1500** | 1894 | 114 GB |
| Fronteriza | 10 | 928 | 1006 | 61 GB |
| Valle de San Fernando | 4 | 689 | 943 | 57 GB |
| Sur | 5 | 483 | 697 | 42 GB |
| Altiplano | 5 | 471 | 630 | 38 GB |
| Mante | 6 | 313 | 534 | 33 GB |

Aviso importante: **las regiones NO son regímenes climáticos distintos.** Medido sobre
731 nodos (2023–24), la fracción de rampa fuerte va de 0.106 (Fronteriza) a 0.123
(Sur) — un 14 % de rango relativo — y el kt medio varía en la tercera cifra. La única
región físicamente peculiar es **Altiplano** (1539 m de media frente a 70–327 m del
resto). O sea: las regiones se usan como criterio de PARTICIÓN, no como hipótesis de
que haya seis climas que aprender por separado.

## El halo, y por qué es obligatorio

Cortar por una frontera administrativa rompe los vecindarios espaciales. Nodos con
vecindario r2 **completo**:

| región | dentro del estado | solo dentro de su región | pérdida |
|---|---|---|---|
| Mante | 78 % | 41 % | −36 pp |
| Sur | 78 % | 53 % | −25 pp |
| Valle de San Fernando | 82 % | 63 % | −19 pp |
| Altiplano | 71 % | 54 % | −17 pp |
| Centro | 90 % | 73 % | −17 pp |
| Fronteriza | 47 % | 42 % | −4 pp |
| **TOTAL** | **75 %** | **58 %** | **−17 pp** |

Con `kt_vecinos_mean_r2` como 2ª feature del modelo, eso ataca justo lo que mejor
funciona. La solución:

> **entrenar** sobre `región + halo de 3 celdas` (~13 km) · **evaluar** solo sobre la región

Implementado en `forecasting/data/regiones.py` (`bloque_region`, `con_halo`) y en el
runner vía `ExperimentoConfig.nodos_eval`: los nodos de halo entran al entrenamiento y
a la validación de early stopping, pero se filtran antes de calcular métricas, así que
la población evaluada es exactamente la región y las cifras son comparables entre
regiones.

(Fronteriza solo pierde 4 pp porque ya está rota de origen: el 53 % de sus vecinos
caen en Texas o en el Golfo. Arreglarla de verdad exigiría descargar la franja NSRDB
del lado estadounidense.)

## Ingeniería de memoria: `float32`

El pico es ~3× el dataset final, y todo está en la etapa de construcción de features.
`ExperimentoConfig.float32=True` baja las features (no las META) a float32 **por nodo,
antes de concatenar** — tiene que ser ahí, porque el pico está en la concatenación y
en los bloques espaciales; downcastear el resultado final no ahorraría nada. Es
lossless de cara al modelo: XGBoost convierte internamente a float32 de todos modos.

Efecto medido en Centro: pico **94.5 GB** frente a los ~114 GB proyectados en float64
(−17 %). Dataset en disco: 5.6 GB para 1894 nodos.

## Resultados — exp09 v1, región Centro (test 2024)

1500 nodos evaluados + 394 de halo · 64 features · best_iteration 657 · **7 min 44 s**,
pico **94.5 GB**.

**Skill 0.1542** — RMSE 75.00 vs persistence 88.66 W/m², R² 0.933, sobre 6.18 M filas.

### ¿Aporta escalar de 144 a 1500 nodos?

El global no es comparable con exp07 v4: son poblaciones de test distintas (el
`RMSE_persistence` lo delata, 86.41 vs 88.66). La comparación honesta es **pareada
sobre los 117 nodos que ambos evalúan**:

| | exp07 v4 (144 nodos) | exp09 v1 (1500 nodos) |
|---|---|---|
| skill medio | 0.1284 | **0.1392** |
| RMSE medio | 75.15 | **74.23** W/m² |

**+0.0109 de skill (+8.5 % relativo), −0.92 W/m² de RMSE, y mejora en 94 de 117 nodos
(80 %).** La mediana del delta es +0.0085, el p10 −0.0026: la mejora es pequeña pero
sistemática, casi nunca perjudica. Es coherente con la redundancia espacial medida
(kt correlaciona 0.73 a 42 km): multiplicar los nodos por 10 multiplica las filas por
10 pero la información efectiva mucho menos.

### Por régimen

| régimen | n | skill | vs exp07 v4 |
|---|---|---|---|
| rampa fuerte (>0.25) | 780 701 | **0.259** | 0.220 |
| rampa moderada | 1 194 435 | 0.141 | 0.129 |
| **rampa suave (<0.1)** | 4 206 667 | **−0.733** | −0.675 |
| despejado (kt≥0.7) | 4 616 672 | 0.196 | 0.150 |
| parcial (0.3–0.7) | 1 126 590 | 0.172 | 0.152 |
| cubierto (kt<0.3) | 440 041 | 0.005 | 0.030 |

El bloque grande mejora donde el modelo ya ganaba (rampa fuerte 0.220 → **0.259**) y
**empeora en cubierto** (0.030 → 0.005, R² −3.27). El agujero de la rampa suave sigue
igual de abierto: es el 68 % de las horas y el modelo pierde contra persistence por
un margen enorme. Escalar nodos no lo toca, como estaba previsto.

### Distribución espacial y relieve

Skill por nodo dentro de Centro: min 0.065, mediana 0.156, max 0.215. **Ningún nodo
con skill negativo.** La correlación con la altitud es **−0.406**: cuanto más alto el
nodo, peor pronostica el modelo. Es la primera señal cuantitativa de que el relieve
importa — y respalda tratar Altiplano (1539 m) como caso aparte.

### Importancias

`kt_lag1` 0.508, luego el bloque de vecinos: `kt_vecinos_mean` (r1) 0.130,
`kt_vecinos_mean_r3` 0.124, `cloud_op_vecinos_mean` 0.074, `kt_vecinos_mean_r2` 0.022.

Cuidado con leer demasiado en el reparto entre radios: r1/r2/r3 son muy colineales y
el gain se traslada entre ellos con facilidad. Lo estable es el **total del bloque de
vecinos: 0.276 aquí frente a 0.283 en exp07 v4** — prácticamente idéntico. El
vecindario aporta lo mismo con 144 que con 1500 nodos.

## Las 6 regiones (test 2024)

Estado completo: **4384 nodos**, 22.5 min de cómputo en total.

| v | región | nodos | halo | msnm | RMSE persist | RMSE mod | **skill** | R² | best_iter | tiempo | pico RAM |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v1 | Centro | 1500 | 394 | 327 | 88.66 | 75.00 | 0.1542 | 0.933 | 657 | 7:44 | 94.5 GB |
| v2 | Fronteriza | 928 | 78 | 70 | 87.61 | 74.80 | 0.1463 | 0.928 | 275 | 3:53 | 50.5 GB |
| v3 | Valle de San Fernando | 689 | 254 | 113 | 86.29 | 73.56 | 0.1475 | 0.933 | 312 | 3:38 | 46.4 GB |
| v4 | **Sur** | 483 | 214 | 118 | **91.69** | 76.59 | **0.1647** | 0.926 | 454 | 2:41 | 35.5 GB |
| v5 | **Altiplano** | 471 | 159 | **1543** | 87.80 | 75.82 | **0.1364** | 0.934 | **1037** | 2:30 | 32.2 GB |
| v6 | Mante | 313 | 221 | 325 | 84.03 | **71.34** | 0.1510 | 0.939 | 515 | 2:05 | 27.6 GB |

**Los skills entre regiones NO son comparables directamente**: cada una evalúa una
población distinta y el `RMSE_persistence` mide lo difícil que es la región, no lo
bueno que es el modelo. Sur tiene el mejor skill (0.165) *y* la persistence más mala
(91.69): es la región más difícil, y por eso es donde más se gana. Mante tiene el
mejor RMSE absoluto (71.34) simplemente porque es la región más fácil (persistence
84.03).

### El resultado que sí importa

**Ninguno de los 4384 nodos del estado tiene skill negativo.** El estado entero queda
cubierto por seis modelos que baten a persistence en todos y cada uno de sus nodos.
El rango por nodo va de 0.058 (Mante) a 0.215 (Centro), con las medianas de las seis
regiones apretadas entre 0.137 y 0.165.

### El relieve es el factor discriminante

- Entre regiones: **skill ~ altitud = −0.687**; skill ~ nº de nodos = +0.102 (o sea:
  el tamaño del bloque no explica nada, la altitud sí).
- Por nodo, sobre los 4384: skill ~ altitud = **−0.303** (dentro de Centro era −0.406).
- **Altiplano es el caso aparte**, como se sospechaba desde la climatología: el skill
  más bajo (0.136) y, sobre todo, **1037 iteraciones** de best_iteration frente a las
  275 de Fronteriza — casi 4× más árboles para ajustar la misma señal. La sierra es
  genuinamente más difícil de modelar, no solo de pronosticar.

### Régimen: el patrón se repite en las seis

`skill_rampa_fuerte` entre 0.239 y 0.276, `skill_rampa_suave` entre −0.661 y −0.786,
`skill_cubierto` entre −0.088 y +0.005. El agujero de la rampa suave y el de cubierto
son **estructurales del enfoque, no de una región concreta**: aparecen idénticos en
llanura costera, frontera y sierra. Confirma que arreglarlos es trabajo de modelado
(gating por régimen), no de datos ni de escala.

### Coste real medido (float32)

Con los seis puntos, la curva se recalibra:

```
pico RAM ≈ 0.050 GB × N      tiempo ≈ 0.233 s × N
```

frente a los 0.060 GB/nodo de float64 (−17 %). Extrapolado a 4384 nodos en un solo
bloque: **219 GB** — sigue sin caber, lo que confirma que la partición es necesaria y
no un rodeo. Datasets en disco: 19 GB para las seis.

## Testing

`forecasting/tests/test_regiones.py` (+12): la asignación cubre los 4384 nodos una sola
vez, las 6 regiones particionan el estado (disjuntas y exhaustivas), Victoria cae en
Centro, el halo contiene a la región y crece monótono con el radio, ningún nodo del
halo excede el radio en distancia de Chebyshev, `nodos_eval` separa entrenamiento de
evaluación, y `a_float32` no toca las META y preserva los valores. Suite total: **55**.

## Reproducir

```bash
conda run -n rs python -m forecasting.experiments.run exp09_regiones --version v1
```

Centro es la región más grande y **pica a 94.5 GB**. Si hay algo más corriendo en la
máquina, conviene el tope por cgroup para que falle limpio en vez de invocar al OOM
killer del sistema:

```bash
systemd-run --user --scope -p MemoryMax=100G \
  conda run -n rs python -m forecasting.experiments.run exp09_regiones --version v1
```

Alternativa si va justo: halo de radio 2 (1769 nodos en vez de 1894).

## Siguiente

- **Matriz de transferencia**: entrenar en una región y evaluar en otra. Ahora hay
  base para sospechar el resultado — las cinco regiones de llanura se parecen mucho
  entre sí (skill 0.146–0.165, best_iter 275–515) y **Altiplano** se separa (0.136,
  best_iter 1037). La hipótesis: un modelo de llanura sirve para las cinco y la
  sierra necesita el suyo, o sea **dos modelos, no seis**.
- **Rampa suave** (skill −0.66 a −0.79 sobre ~68 % de las horas, idéntico en las seis
  regiones): el mayor déficit del proyecto. Es estructural del enfoque; ni la escala
  ni la partición lo tocan. Un gating por volatilidad reciente es el siguiente paso
  natural.
- **Cubierto** con skill ≈ 0 o negativo en cinco de seis regiones — segundo agujero
  estructural, del mismo tipo.
- **Fronteriza** ganaría con descargar la franja NSRDB del lado de Texas: es la única
  región cuyo problema de vecindarios no lo arregla el halo.
