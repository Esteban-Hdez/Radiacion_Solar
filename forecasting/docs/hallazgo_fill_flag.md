# Hallazgo: qué es realmente `fill_flag` en el producto NSRDB agregado

> Documento dedicado. Resume qué se encontró, las fuentes exactas, cómo se buscó,
> la evidencia en nuestros datos y las implicaciones de usarlo como filtro del
> target. Ver también `fase1_qc.md` (bitácora de la fase) y `README.md`.

## 1. El problema

La columna `fill_flag` de nuestros parquet de Tamaulipas toma **29 valores
discretos entre 0 y 100** (0, 4, 7, 11, 14, …, 96, 100) que "avanzan de ~4 en 4".
La referencia interna `Data/Tamaulipas/REFERENCIA_NSRDB.md` la documentaba como
una **categórica 0–5** (Missing Image, Low Irradiance, …), lo cual **no coincide**
con lo observado. Había que averiguar el significado real.

## 2. Qué se encontró (definición correcta)

En el producto **GOES aggregated PSM v4**, `fill_flag` es el **porcentaje de
sub-muestras (vecinos espaciales × ventana temporal) que fueron rellenadas
(*gap-filled* por MLClouds)** al agregar a la celda-hora final.

Fórmula real (método `Aggregation.fill_flag` en `nsrdb/aggregation/aggregation.py`):

```python
data[(data > 0)] = 1          # binariza: cualquier flag>0 -> "fue rellenado"
data = a.spatial_sum(data)    # suma sobre vecinos espaciales (nn)
data = a.time_sum(data)       # suma sobre la ventana temporal (w)
data /= len(nn) * w / 100     # = 100 * n_rellenadas / (len(nn) * w)
```

Es decir:

```
fill_flag = 100 · (nº sub-muestras rellenadas) / (len(nn) · w)
```

- **0** = celda-hora construida con observación satelital limpia.
- **100** = celda-hora totalmente rellenada (todo el insumo fue imputado).
- Es una **métrica de calidad del dato**, NO la categórica 0–5 (esa pertenece al
  producto *no* agregado). El flag categórico de relleno de nubes aquí es
  `cloud_fill_flag` ∈ [0, 7].

### Por qué "de 4 en 4": el denominador es 28

Los 29 valores encajan **exactamente** con `round(k/28 · 100)` para k = 0…28.
Por tanto en nuestro producto `len(nn) · w = 28`: cada celda-hora agrega 28
sub-muestras y `fill_flag` es el % de ellas que se rellenó. El "paso ~4" alterna
4,3,4,3… porque es el redondeo entero de fracciones con denominador 28
(100/28 ≈ 3.57).

## 3. Fuentes exactas

| Fuente | URL | Qué aporta |
|---|---|---|
| Código de agregación NSRDB | https://raw.githubusercontent.com/NREL/nsrdb/main/nsrdb/aggregation/aggregation.py | **Definición autoritativa** (método `Aggregation.fill_flag`). |
| Árbol del repo (API) | https://api.github.com/repos/NREL/nsrdb/git/trees/main?recursive=1 | Localizar el archivo sin clonar. |
| Repo NSRDB | https://github.com/NREL/nsrdb | Pipeline oficial (`nsrdb/gap_fill/`, `nsrdb/aggregation/`). |
| MLClouds (gap-fill) | https://github.com/NREL/mlclouds | Qué es el "gap fill" de propiedades de nube. |
| NSRDB docs (Data Model) | https://nrel.github.io/nsrdb/overview/data_model.html | Marco de agregación. |
| API producto agregado | https://developer.nrel.gov/docs/solar/nsrdb/nsrdb-GOES-aggregated-v4-0-0-download/ | Lista de variables del producto (no define fill_flag en detalle). |
| Manual NSRDB (PDF) | https://www.nrel.gov/docs/fy12osti/54824.pdf | Contexto general histórico. |
| Contacto NREL | nsrdb@nrel.gov | Consultas específicas (mandar evidencia). |

## 4. Cómo se buscó (método replicable)

1. **Confirmar el patrón numérico** en los propios datos: valores únicos y sus
   diferencias → coinciden con `round(k/28·100)` ⇒ es un % con denominador 28.
2. **Priorizar el código sobre la prosa**: las páginas de "lista de variables"
   (Microsoft AI-for-Earth, openEDI, manual PDF) solo listan el nombre sin
   definirlo. Los valores *derivados* (flags, agregados) se definen en el pipeline
   que los genera → repo `github.com/NREL/nsrdb`.
3. **Ubicar el archivo sin clonar** pidiendo el árbol por la API de GitHub y
   filtrando por `fill`, `gap`, `aggregat`, `flag` → `nsrdb/aggregation/aggregation.py`.
4. **Leer el `raw`** del archivo y buscar dónde se divide por un conteo / ×100.
5. **Búsqueda de código** cuando aplique: en https://github.com/search (pestaña
   *Code*) `repo:NREL/nsrdb fill_flag`, o `gh search code --repo NREL/nsrdb fill_flag`.
6. **Queries de buscador**: nombre exacto entre comillas + producto/versión, p. ej.
   `NSRDB PSM v4 GOES aggregated "fill_flag" gap fill`.

Regla general: variable derivada ⇒ ir al código de agregación/gap-fill antes que
a la documentación.

## 5. Evidencia en nuestros datos

Tabla `Results/Tamaulipas/forecast/fill_flag_frecuencia_global_2020_2024.csv`
(todos los nodos, 2020–2024). A mayor `fill_flag`: **baja kt** y **sube nubosidad**,
consistente con "más relleno = peor calidad = más nublado":

| fill_flag | % obs | kt medio (op) | cloud_type medio |
|---|---|---|---|
| 0 | 90.9 % | 0.845 | 1.94 |
| 4–11 | ~2.2 % | 0.75 → 0.73 | ~3 |
| 29–43 | ~1.3 % | 0.60 → 0.56 | ~4.5–4.9 |
| 100 | 0.83 % | 0.614 | 5.79 |

## 6. Implicaciones de usarlo (o no) como filtro del target

Se plantea usar `fill_flag` **solo** como filtro de la **variable objetivo**, al
mismo nivel que `solar_zenith_angle < 85` y `clearsky_ghi > 0` (nunca como feature).
Cuánto se descarta y de qué tipo (horas operativas):

| Umbral (descartar si …) | % horas op. descartadas (global) | kt medio de lo descartado |
|---|---|---|
| `fill_flag > 0` | 12.2 % | 0.68 |
| `fill_flag > 25` | 5.5 % | 0.62 |
| `fill_flag > 50` | 3.2 % | 0.62 |
| `fill_flag > 75` | 1.6 % | 0.63 |

(Nodo 1736 casi idéntico: 11.7 % / 5.9 % / 3.6 % / 1.8 %.)

**Dato crítico**: lo que se descarta son sistemáticamente las **horas nubladas**
(kt ≈ 0.62–0.68 vs 0.825 global). Es justo la **cola difícil** del problema.

- **A favor de filtrar**: en esas horas el "GHI observado" es en gran parte
  *imputado* por MLClouds, no una medición → como target introduce ruido de
  etiqueta; el modelo aprendería a predecir una interpolación. Un umbral alto
  (p. ej. `> 75` o `> 90`) quita lo peor (~1–2 %) con impacto mínimo.
- **En contra de filtrar**: esas horas nubladas son **donde el modelo aporta valor
  frente a persistence**. Filtrar agresivamente (p. ej. `> 0`) sube artificialmente
  las métricas (quitas lo difícil) y produce un modelo que no verá cielos nublados
  en test → **sesgo optimista** y mala generalización operativa. Además rompe la
  contigüidad temporal (huecos en la serie) que necesitan los lags.

**Recomendación**: NO filtrar por defecto en el arranque; mantener todas las horas
operativas y **reportar métricas segmentadas por tramo de `fill_flag`** (limpio vs
rellenado). Si acaso, usar un umbral **conservador** (`> 90`) como estudio de
sensibilidad, nunca como filtro base. Decisión pendiente del usuario.

> Importante: si se filtra, hacerlo **solo sobre el target** (la fila a predecir),
> jamás sobre las features rezagadas — un lag puede provenir de una hora rellenada
> sin problema; lo que se cuida es no *entrenar/evaluar contra* una etiqueta imputada.
