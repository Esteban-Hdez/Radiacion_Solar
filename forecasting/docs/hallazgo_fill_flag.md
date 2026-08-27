# Procedencia y calidad del dato NSRDB: `fill_flag`, `cloud_fill_flag` y `clearsky_*`

> Documento de referencia sobre la **calidad y la procedencia** de los datos NSRDB que
> usa el proyecto. Explica cómo se fabrica realmente cada celda-hora del dataset, qué
> significa cada bandera, cómo se calcula el cielo despejado, y los dos hallazgos que
> más condicionan el modelado: **lo que el proveedor imputa son justamente los
> episodios que nos interesan**, y **`clearsky_*` no es una variable astronómica**.
> Ver también `fase1_qc.md` (bitácora) y `catalogo_features.md`.

---

## 0. Resumen

1. Son **dos columnas distintas** que se confunden con facilidad: `cloud_fill_flag` es
   una **categórica 0–7** (*cómo* se rellenó) y `fill_flag` es un **porcentaje 0–100**
   (*cuánto* del insumo venía relleno).
2. `fill_flag` avanza "de 4 en 4" porque es `round(k/28·100)`, y ese **28 = 4 vecinos
   espaciales × 7 pasos temporales** de la agregación de 2 km/5 min a 4 km/30 min.
3. Las 8 categorías de `cloud_fill_flag` **no están documentadas en ningún sitio
   único**: las escriben tres módulos distintos del pipeline sobre el mismo array.
4. El **9.5 %** de las horas operativas de 2024 lleva algún relleno; el GHI de esas
   horas es en parte una **predicción de red neuronal (MLClouds)**, no una medición.
5. **Hallazgo crítico 1**: la tasa de imputación en las horas de **rampa fuerte es
   3.4× la de las horas tranquilas** (20.8 % vs 6.1 %). El proveedor imputa
   preferentemente los episodios difíciles, que son exactamente donde nuestro modelo
   aporta valor.
6. **Hallazgo crítico 2**: `clearsky_ghi/dni/dhi` **no son astronómicas**. Salen del
   modelo REST2, que recibe **10 entradas de las que solo 2 son geométricas**; las
   otras 8 son estado atmosférico de MERRA-2. A ángulo solar fijo el clearsky varía un
   **4–6 %** (y el difuso un 25–33 %). En operación **no serían known-future**.

---

## 1. El problema de partida

La referencia interna `Data/Tamaulipas/REFERENCIA_NSRDB.md` documentaba `fill_flag`
como una categórica 0–5 (Missing Image, Low Irradiance, …). Pero en nuestros parquet
`fill_flag` toma **29 valores discretos entre 0 y 100** (0, 4, 7, 11, 14, …, 96, 100).
No cuadraba. La categórica que describía esa referencia pertenece al producto **no
agregado**; nosotros usamos el **GOES aggregated PSM v4**, donde la variable significa
otra cosa.

---

## 2. Las dos columnas, lado a lado

| | `cloud_fill_flag` | `fill_flag` |
|---|---|---|
| Tipo | categórica | porcentaje |
| Valores en nuestros datos | **0–7** (8 categorías) | **0–100** (29 valores) |
| Responde a | *cómo* se rellenó la propiedad de nube | *qué fracción* del insumo agregado venía rellena |
| Dónde nace | módulos de gap-fill (pre-agregación) | módulo de agregación |
| Uso correcto | diagnóstico del método de relleno | **métrica de calidad del dato** |

Las "7 categorías" de la documentación son `cloud_fill_flag`. Los "valores de 4 en 4"
son `fill_flag`. **No tienen por qué coincidir: son cosas diferentes.**

---

## 3. `cloud_fill_flag` — las 8 categorías y quién las escribe

La razón por la que no se encuentra una lista completa es que **no existe**: los
códigos los asignan tres módulos distintos del pipeline sobre el mismo array, y
ninguno documenta los de los otros. Reconstruida a partir del código fuente:

| código | significado | módulo que lo asigna | % en 2024 |
|---|---|---|---|
| **0** | sin relleno — recuperación satelital limpia | — | **94.36 %** |
| 1 | falta `cloud_type` en ese paso temporal | `gap_fill/cloud_fill.py` | 1.29 % |
| 2 | falta `cloud_type` en toda la serie → se asume despejado | `gap_fill/cloud_fill.py` | 1.10 % |
| 3 | falta una propiedad de nube en hora diurna nublada | `gap_fill/cloud_fill.py` | 0.64 % |
| 4 | faltan propiedades de nube en toda la serie | `gap_fill/cloud_fill.py` | 0.69 % |
| 5 | se forzó el límite de cielo despejado (`enforce_clearsky`) | `gap_fill/irradiance_fill.py` | 0.64 % |
| 6 | irradiancia NaN o negativa | `gap_fill/irradiance_fill.py` | 0.75 % |
| **7** | **relleno por MLClouds** (red neuronal guiada por física) | `gap_fill/mlclouds_fill.py` | 0.52 % |

Líneas exactas del código para los casos menos evidentes:

```python
# gap_fill/irradiance_fill.py
fill_flag[mask] = 5                                   # enforce_clearsky()
new_fill_flag[np.isnan(irrad) | (irrad < 0)] = 6

# gap_fill/mlclouds_fill.py
fill_flag[mask_fill_flag_opd] = 7    # fill_flag=7 is mlcloud fill
fill_flag[mask_fill_flag_reff] = 7   # fill_flag=7 is mlcloud fill
```

---

## 4. `fill_flag` — la fórmula y de dónde sale el 28

En el producto agregado, `fill_flag` es el **porcentaje de sub-muestras (vecinos
espaciales × ventana temporal) que estaban rellenadas** al construir la celda-hora
final. Método `Aggregation.fill_flag` en `nsrdb/aggregation/aggregation.py`:

```python
data[(data > 0)] = 1          # binariza: cualquier cloud_fill_flag>0 -> "fue rellenado"
data = a.spatial_sum(data)    # suma sobre los vecinos espaciales (nn)
data = a.time_sum(data)       # suma sobre la ventana temporal (w)
data = a.reduce_timeseries(data)
data /= len(nn) * w / 100     # -> porcentaje
```

es decir

```
fill_flag = 100 · (nº sub-muestras rellenadas) / (len(nn) · w)
```

### La descomposición del 28

En nuestro producto `len(nn) · w = 28`, y el código permite descomponerlo:

- **`nn` = 4 vecinos espaciales.** El número de vecinos se calcula como
  `k = ceil(final_sres² / source_sres²)`. Para pasar de **2 km a 4 km**:
  `ceil(16/4) = 4`, o sea la celda de 4 km agrega las 2×2 celdas de 2 km que contiene.
- **`w` = 7 pasos temporales.** Es la ventana móvil al pasar de **5 min a 30 min**
  (el código usa `w=7` para fuente de 5 min, `w=4` para 10 min, `w=3` para 15 min).

**4 × 7 = 28 sub-muestras por celda-hora.** De ahí que haya exactamente 29 valores
posibles (k = 0…28) y que el paso alterne 4, 3, 4, 3… — es el redondeo entero de
fracciones con denominador 28 (100/28 ≈ 3.57).

Verificado contra nuestros datos: los 29 valores observados coinciden **exactamente**
con `round(k/28·100)` para k = 0…28.

### La relación entre ambas columnas

Como la agregación binariza el flag de origen (`data[data > 0] = 1`), se deduce que

> **`fill_flag` = % de las 28 sub-muestras cuyo `cloud_fill_flag` era distinto de 0.**

Son la misma información a dos resoluciones: una categórica antes de agregar, un
porcentaje después.

---

## 5. Cómo se crean realmente estos datos

La cadena completa que produce cada valor de GHI de nuestro dataset:

1. **Imagen satelital GOES** (Este/Oeste) a **2 km y 5 min** sobre CONUS.
2. **Recuperación de propiedades de nube** desde la imagen: máscara de nube,
   `cloud_type`, profundidad óptica y radio efectivo de partícula.
3. **Gap-fill** de lo que la recuperación no resolvió — noche, reflejo especular del
   sol, nieve, fallos del algoritmo. Primero los métodos clásicos (códigos 1–6) y
   luego **MLClouds**, una red neuronal guiada por física que *predice* las
   propiedades de nube faltantes (código 7).
4. **Datos atmosféricos auxiliares de MERRA-2**: presión, humedad, viento, aerosoles,
   ozono, agua precipitable.
5. **Transferencia radiativa**: el modelo all-sky (PXS/FARMS) calcula GHI y DHI; el
   **DNI** se deriva con DISC. El cielo despejado (`clearsky_ghi/dni/dhi`) se calcula
   aparte con **REST2**.
6. **Agregación** de 2 km/5 min a **4 km/30 min** — las 4×7 = 28 sub-muestras. Aquí
   nace `fill_flag`.
7. Nosotros descargamos con `interval=60`. Como los 29 valores siguen encajando con
   denominador 28, el producto horario **hereda** el `fill_flag` de 30 min en vez de
   re-agregarlo: es una selección temporal, no un promedio adicional.

**Implicación de fondo**: el "GHI observado" contra el que entrenamos y evaluamos
**no es una medición en superficie**. Es la salida de un modelo de transferencia
radiativa alimentado con propiedades de nube estimadas desde satélite y, en una
fracción de los casos, imputadas por una red neuronal. Nuestro techo de precisión está
acotado por el error de esa cadena, no solo por el nuestro.

---

## 6. `clearsky_ghi/dni/dhi` — cómo se calculan y por qué NO son astronómicas

Las tratamos en `config.py` como `DETERMINISTAS` (known-future en τ, sin rezagar).
El nombre induce a error: son deterministas **dado el reanálisis**, no por geometría.

### El modelo y sus diez entradas

El cielo despejado sale de **REST2** (Gueymard 2008), invocado en
`nsrdb/all_sky/all_sky.py`:

```python
rest_data = rest2(surface_pressure, surface_albedo, ssa, asymmetry,
                  solar_zenith_angle, radius, alpha, beta, ozone,
                  total_precipitable_water)
```

| # | entrada | naturaleza | ¿está en nuestro dataset? | cómo la clasificamos |
|---|---|---|---|---|
| 1 | `surface_pressure` | atmosférica (MERRA-2) | sí (`pressure`) | OBSERVADA → rezagada |
| 2 | `surface_albedo` | superficie (MODIS/IMS) | sí | OBSERVADA → rezagada |
| 3 | `ssa` | aerosol (MERRA-2) | sí | OBSERVADA → rezagada |
| 4 | `asymmetry` | aerosol (MERRA-2) | sí | OBSERVADA → rezagada |
| 5 | **`solar_zenith_angle`** | **astronómica** | sí | DETERMINISTA |
| 6 | **`radius`** (Sol-Tierra) | **astronómica** | se deriva del índice temporal | — |
| 7 | `alpha` (Ångström) | aerosol (MERRA-2) | sí | OBSERVADA → rezagada |
| 8 | `beta` | derivada de AOD y `alpha` | sí (`aerosol_optical_depth`) | OBSERVADA → rezagada |
| 9 | `ozone` | atmosférica (MERRA-2) | sí | OBSERVADA → rezagada |
| 10 | `total_precipitable_water` | atmosférica (MERRA-2) | sí (`precipitable_water`) | OBSERVADA → rezagada |

**Solo 2 de 10 son astronómicas.** Y las **ocho restantes están en nuestro dataset**,
donde las clasificamos como observadas y las rezagamos — mientras que el `clearsky_*`
que se calcula a partir de ellas entra **sin rezagar**.

### Cuánto pesa la parte atmosférica (medido)

Nodo 1736, 2024, agrupando por ángulo cenital fijo — así lo que queda es 100 % atmósfera:

| zenital | `clearsky_ghi` sd | amplitud | `clearsky_dni` sd | `clearsky_dhi` sd |
|---|---|---|---|---|
| 30° ± 0.5 | 4.1 % | 17.4 % | 10.6 % | 32.6 % |
| 45° ± 0.5 | 5.7 % | 22.4 % | 10.8 % | 24.4 % |
| 60° ± 0.5 | 6.2 % | 26.5 % | 15.5 % | 30.6 % |

El "cielo despejado" **no es una curva geométrica fija**: a la misma altura solar varía
±4–6 % (1σ) en GHI y el difuso hasta un 33 %. Los impulsores dominantes son el **agua
precipitable** (correlación −0.73 a −0.87) y el **AOD** (−0.60 a −0.69).

Persistencia horaria de esas entradas (horas operativas 2024, nodo 1736):

| variable | `corr(t, t−1)` | cambio \|Δ\| medio en 1 h |
|---|---|---|
| `asymmetry` | +0.998 | 0.00 % |
| `surface_albedo` | +0.993 | 0.14 % |
| `ozone` | +0.991 | 0.36 % |
| `precipitable_water` | +0.985 | 3.34 % |
| `alpha` | +0.966 | 2.84 % |
| `pressure` | +0.963 | 0.07 % |
| `aerosol_optical_depth` | +0.958 | **10.96 %** |

### `clearsky_dhi` es redundante

La relación de cierre `GHI = DNI·cos(z) + DHI` se cumple en nuestros datos con residuo
medio **+0.002 W/m²**, sd 0.29 y máximo 0.50 (puro redondeo a `int16`), en el **100 %**
de las horas operativas — y vale igual para la terna all-sky.

Es decir, `clearsky_dhi` **no aporta información independiente**: es función exacta de
`clearsky_ghi`, `clearsky_dni` y `solar_zenith_angle`, que ya son features. No es un
error (XGBoost tolera la redundancia) pero explica por qué el gain se reparte entre
ellas, y es la primera candidata si alguna vez se quiere adelgazar el feature-set.

### Implicación 1 — inconsistencia formal en el anti-leakage (menor)

Dar `clearsky_ghi(τ)` sin rezagar equivale a pasarle al modelo una función determinista
del estado en τ de AOD, agua precipitable y ozono, variables que rezagamos en todas las
demás features. Es una inconsistencia real, pero **poco grave**, por tres razones:

1. Por construcción REST2 es un modelo **sin nubes**: `clearsky_*` no contiene nada de
   la información nubosa, que es la parte impredecible y la que determina kt. **No hay
   fuga del target.**
2. Las entradas persisten muchísimo (tabla de arriba, `corr(t,t−1)` 0.958–0.998), así
   que la diferencia entre usarlas en τ o en τ−1 es pequeña frente a la dispersión
   climatológica del 4–6 %.
3. `clearsky_ghi(τ)` es **estructuralmente necesario**: el GHI se reconstruye como
   `kt_pred × clearsky_ghi(τ)`. No es opcional.

> Pendiente si se quiere cerrar del todo: **recomputar REST2 con entradas rezagadas** y
> medir la diferencia. Tenemos las diez entradas en el dataset, así que el experimento
> es acotado. No se ha hecho.

### Implicación 2 — en operación NO son known-future (esta sí importa)

En un pronóstico real no se conoce el AOD ni el agua precipitable del futuro. En
nuestro dataset histórico `clearsky_*` viene de **reanálisis MERRA-2**, es decir, de
información posterior al momento de emisión. Para desplegar habría que calcular el
clearsky con aerosoles y vapor **pronosticados** (CAMS, NWP), y eso mete error en una
variable que hoy tratamos como exacta.

Orden de magnitud: con RMSE ~75 W/m² sobre un GHI medio de ~500–570 en horas
operativas, un error del 4 % en clearsky son ~20–28 W/m² que se propagan
**multiplicativamente** al reconstruir el GHI — del orden del 30 % de nuestro RMSE.

- **Para t+1**: manejable. Persistir las entradas atmosféricas una hora apenas las
  mueve (≤3 % salvo el AOD).
- **Para día-adelante**: no. En 24 h el AOD y el agua precipitable cambian mucho, y el
  clearsky pronosticado deja de ser un detalle. **Hay que tratarlo como una fuente de
  error propia y medirla**, no asumirla nula.

---

## 7. El hallazgo crítico: se imputa justo lo que nos interesa

Sobre las **18.1 M de horas operativas de 2024** (todos los nodos), el **9.5 %** tiene
`fill_flag > 0`. Pero ese relleno **no está repartido al azar**.

### Por régimen de rampa

| régimen | % de las horas | **% imputado** | fill_flag medio | vs global |
|---|---|---|---|---|
| rampa suave (<0.1) | 68.9 % | **6.1 %** | 1.94 | 0.64× |
| rampa moderada (0.1–0.25) | 19.1 % | 14.5 % | 5.36 | 1.54× |
| **rampa fuerte (>0.25)** | 12.0 % | **20.8 %** | 8.91 | **2.20×** |

**Una hora de rampa fuerte tiene 3.4 veces más probabilidad de estar imputada que una
hora tranquila** (20.8 % vs 6.1 %). Y aunque las rampas fuertes son solo el 12 % de las
horas, concentran el **26.3 %** de todo el relleno.

### Por régimen de nubosidad

| régimen | % de las horas | **% imputado** | `cloud_fill_flag>0` | vs global |
|---|---|---|---|---|
| cubierto (kt<0.3) | 6.6 % | 11.3 % | 8.65 % | 1.20× |
| **parcial (0.3–0.7)** | 17.8 % | **18.5 %** | **15.26 %** | **1.96×** |
| despejado (kt≥0.7) | 75.7 % | 7.2 % | 3.72 % | 0.76× |

Matiz importante y algo contraintuitivo: **el régimen más imputado no es el cubierto,
sino el parcialmente nublado** (18.5 % vs 11.3 %). Tiene sentido físico — la nubosidad
rota da píxeles mixtos y bordes de nube, que es el caso más difícil para la
recuperación satelital. Un cielo totalmente cubierto es más fácil de identificar que
uno a medias.

### El caso extremo

Las celdas-hora **totalmente imputadas** (`fill_flag = 100`, las 28 sub-muestras
rellenadas) son el **0.47 %** de las horas operativas, con kt medio 0.740 frente a
0.822 global, y el 14.2 % de ellas cae en régimen cubierto.

### Por qué esto importa

La coincidencia es exacta y desafortunada: **el régimen donde nuestro modelo gana
(rampa fuerte, skill 0.24–0.28 en las seis regiones) es el mismo donde la etiqueta es
menos fiable**. Parte de lo que el modelo aprende a predecir en esos episodios no es
la física de la nube, sino **la interpolación de MLClouds** — y parte de nuestro error
residual puede ser ruido de etiqueta, no error del modelo.

---

## 8. ¿Filtrar por `fill_flag`? Análisis y recomendación

Cuánto se descartaría (horas operativas, global 2020–2024, tabla
`Results/Tamaulipas/forecast/fill_flag_frecuencia_global_2020_2024.csv`):

| Umbral (descartar si …) | % horas descartadas | kt medio de lo descartado |
|---|---|---|
| `fill_flag > 0` | 12.2 % | 0.68 |
| `fill_flag > 25` | 5.5 % | 0.62 |
| `fill_flag > 50` | 3.2 % | 0.62 |
| `fill_flag > 75` | 1.6 % | 0.63 |

(Nodo 1736 casi idéntico: 11.7 % / 5.9 % / 3.6 % / 1.8 %.)

- **A favor de filtrar**: en esas horas el "GHI observado" es en buena parte imputado.
  Como target introduce **ruido de etiqueta**, y el modelo aprende a reproducir una
  interpolación. Un umbral alto (`>75` o `>90`) quita lo peor (~1–2 %) con impacto
  mínimo sobre el volumen.
- **En contra**: esas horas son **donde el modelo aporta valor frente a persistence**.
  Filtrar agresivamente (`>0`) sube artificialmente las métricas porque quitas lo
  difícil, produce un modelo que no habrá visto cielos rotos, y **rompe la
  contigüidad temporal** que necesitan los lags y las features de advección.

**Recomendación vigente**: **no filtrar por defecto**. Mantener todas las horas
operativas y **reportar métricas segmentadas** por tramo de `fill_flag` — que es
exactamente lo que hace el pipeline (`limpio_ff0` vs `rellenado_ff_pos` en
`metrics_global.csv` de cada experimento). Si acaso, usar `>90` como estudio de
sensibilidad, nunca como filtro base.

> **Regla dura**: si se filtra, hacerlo **solo sobre el target** (la fila a predecir),
> jamás sobre las features rezagadas. Un lag puede provenir de una hora rellenada sin
> problema; lo que se cuida es no *entrenar ni evaluar contra* una etiqueta imputada.

`fill_flag` **nunca** debe usarse como feature predictiva: es metadato de calidad del
proveedor, no información física disponible en tiempo de pronóstico.

---

## 9. Fuentes

| Fuente | URL | Qué aporta |
|---|---|---|
| Código de agregación | https://raw.githubusercontent.com/NREL/nsrdb/main/nsrdb/aggregation/aggregation.py | **Definición autoritativa** de `fill_flag`; cálculo de `nn` y `w` |
| Gap-fill de nubes | https://raw.githubusercontent.com/NREL/nsrdb/main/nsrdb/gap_fill/cloud_fill.py | Códigos 1–4 |
| Gap-fill de irradiancia | https://raw.githubusercontent.com/NREL/nsrdb/main/nsrdb/gap_fill/irradiance_fill.py | Códigos 5 y 6 |
| MLClouds fill | https://raw.githubusercontent.com/NREL/nsrdb/main/nsrdb/gap_fill/mlclouds_fill.py | Código 7 |
| Modelo all-sky | https://raw.githubusercontent.com/NREL/nsrdb/main/nsrdb/all_sky/all_sky.py | **Llamada a REST2** con sus 10 entradas; `calc_dhi` |
| README all-sky | https://raw.githubusercontent.com/NREL/nsrdb/main/nsrdb/all_sky/README.rst | PXS All-Sky; citas a REST2 (Gueymard 2008) y FARMS |
| Repo NSRDB | https://github.com/NREL/nsrdb | Pipeline completo; REST2, DISC, MERRA-2 |
| MLClouds | https://github.com/NREL/mlclouds | La red neuronal de relleno |
| API del producto | https://developer.nrel.gov/docs/solar/nsrdb/nsrdb-GOES-aggregated-v4-0-0-download/ | Lista de variables (no define `fill_flag`) |
| Contacto NREL | nsrdb@nrel.gov | Consultas específicas |

---

## 10. Método de búsqueda (replicable)

Lo que funcionó, por si hay que repetirlo con otra variable derivada:

1. **Confirmar el patrón numérico en los propios datos** antes de buscar nada: valores
   únicos y sus diferencias. Aquí, encajar con `round(k/28·100)` ya decía que era un
   porcentaje con denominador 28.
2. **Priorizar el código sobre la prosa.** Las páginas de "lista de variables"
   (Microsoft AI-for-Earth, openEDI, el manual PDF) dan el nombre pero no la
   definición. Los valores *derivados* se definen en el pipeline que los genera.
3. **Localizar el archivo sin clonar**: pedir el árbol por la API de GitHub
   (`https://api.github.com/repos/NREL/nsrdb/git/trees/main?recursive=1` — ojo, hoy
   responde 301, hay que seguir el redirect con `curl -L`) y filtrar por `fill`,
   `gap`, `aggregat`, `flag`.
4. **Leer el `raw`** del archivo y buscar dónde se divide por un conteo o se multiplica
   por 100.
5. **No asumir que una enumeración existe.** Aquí los 8 códigos estaban repartidos
   entre tres módulos; hubo que leerlos todos y unir.

> Regla general: **variable derivada ⇒ ir al código de agregación/gap-fill antes que a
> la documentación de usuario.**
