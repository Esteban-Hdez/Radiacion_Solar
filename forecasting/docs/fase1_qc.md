# Fase 1 — Control de calidad y exploración

Bitácora de la primera fase del pipeline de pronóstico. Objetivo: conocer la
estructura de los datos, aplicar control de calidad, y dejar una serie limpia de
un nodo de arranque para las fases de modelado.

## 1. Qué se construyó

| Archivo | Función |
|---|---|
| `forecasting/config.py` | Rutas, años, definición de horas operativas y **clasificación anti-leakage** de variables. |
| `forecasting/data/loaders.py` | `cargar_nodo()` (serie multi-año con índice horario contiguo) y `resumen_calidad_nodos()` (métricas por nodo en lotes). |
| `forecasting/data/qc.py` | `seleccionar_nodo_arranque()`, `reporte_qc()` y `tabla_fill_flag()`. |
| `notebooks/01_exploracion_qc.ipynb` | Notebook narrado de esta fase. |

## 2. Estructura de los datos (verificada)

- Consolidados horarios en `Data/Tamaulipas/<AÑO>/Finales/completo/`.
- **4384 nodos**, cadencia **horaria en UTC**, 8760 filas/nodo/año, 31 columnas.
- Años consolidados: **2017 y 2020–2024** (faltan 2018, 2019 y 2025).
- kt (=ghi/clearsky_ghi) ya viene acotado a [0,1]; ~47 % de horas son operativas.

## 3. Selección del nodo de arranque

Criterio automático (en `seleccionar_nodo_arranque`): nodos con datos completos
en todos los años → fracción de relleno por debajo de la mediana → el más cercano
a Cd. Victoria (para interpretar resultados).

- **Nodo elegido: `1736`** — lat 23.73, lon −99.18, 381 msnm (Cd. Victoria).
- 2192 nodos de calidad cumplían el criterio.
- Serie limpia guardada: `Results/Tamaulipas/forecast/nodo_1736_serie.parquet`.

## 4. Resultados del QC (nodo 1736, 2020–2024)

- **43 848 horas** contiguas, **0 timestamps faltantes**, 0 duplicados.
- **0 valores físicamente imposibles** (rangos de `config.RANGOS_FISICOS`).
- **46.9 %** horas operativas; kt sin NaN; **0 casos kt>1**.
- kt fuertemente sesgado a 1 (**mediana 0.993**): región casi siempre despejada.
  Implicación: *smart persistence* será un baseline duro; el valor del modelo
  está en predecir bien la cola nubosa (kt bajos).
- Drivers (correlación con kt en operativas): `cloud_type` −0.67, `dni` +0.83
  (ambos **observados** → van rezagados); UV redundante (≈ f(ghi)) → se descarta.

## 5. Hallazgo: `fill_flag` NO coincide con la documentación

> Documento dedicado con fuentes exactas, método de búsqueda e implicaciones:
> [`hallazgo_fill_flag.md`](hallazgo_fill_flag.md). Resumen abajo.

`REFERENCIA_NSRDB.md` documenta `fill_flag` como categórica 0–5. La columna real
va **0–100** con 29 valores discretos. La categórica 0–7 corresponde a
**`cloud_fill_flag`** (verificado: `cloud_fill_flag` ∈ [0,7]).

La tabla `Results/Tamaulipas/forecast/fill_flag_frecuencia_global_2020_2024.csv`
(todos los nodos, 2020–2024) muestra un patrón **monótono** que sugiere que
`fill_flag` es un **porcentaje de relleno del pixel satelital**:

| fill_flag | % obs | kt medio (op) | cloud_type medio |
|---|---|---|---|
| 0 | 90.9 % | 0.845 | 1.94 |
| 4–11 | ~2.2 % | 0.75→0.73 | ~3 |
| 29–43 | ~1.3 % | 0.60→0.56 | ~4.5–4.9 |
| 100 | 0.83 % | 0.614 | 5.79 |

A mayor `fill_flag`: **baja kt**, **sube nubosidad** y sube `cloud_fill_flag`.
Es decir, valores altos = pixel más rellenado = retrieval de peor calidad,
asociado a condiciones nubladas.

### Confirmado en el código fuente de NSRDB

`fill_flag` en el producto **agregado** es el **porcentaje de sub-muestras
(vecinos espaciales × ventana temporal) que fueron rellenadas** al agregar a la
malla/hora final. En `nsrdb/aggregation/aggregation.py`, método
`Aggregation.fill_flag`:

```python
data[(data > 0)] = 1          # binariza: cualquier flag>0 -> "fue rellenado"
data = a.spatial_sum(data)    # suma sobre vecinos espaciales (nn)
data = a.time_sum(data)       # suma sobre la ventana temporal (w)
data /= len(nn) * w / 100     # = 100 * n_rellenadas / (n_vecinos * ventana)
```

Es decir `fill_flag = 100 · (nº rellenadas / (len(nn)·w))`. En nuestros datos el
denominador es **28** (`len(nn)·w = 28`): por eso los valores son
`round(k/28·100)` para k=0…28 y "avanzan de ~4 en 4". **No es la categórica 0–5**
de la documentación vieja (esa corresponde a `fill_flag` del producto *no*
agregado; aquí `cloud_fill_flag` ∈ [0,7] es el flag de relleno de nubes).

**Interpretación**: `fill_flag` = % del insumo satelital que fue *gap-filled*
(MLClouds) para esa celda-hora. 0 = observación limpia; 100 = totalmente
rellenada. Es una **métrica de calidad**, no un predictor.

**Decidido/pendiente**: (a) corregir `REFERENCIA_NSRDB.md`; (b) evaluar usar
`fill_flag` como umbral (p. ej. descartar del target horas con fill_flag alto).

Fuentes: [aggregation.py (NREL/nsrdb)](https://raw.githubusercontent.com/NREL/nsrdb/main/nsrdb/aggregation/aggregation.py),
[árbol del repo](https://github.com/NREL/nsrdb).

## 6. Siguiente paso

Fase 2: baseline *smart persistence* (`kt(t+1)=kt(t)`) + métricas de referencia
(RMSE/MAE/MBE sobre GHI reconstruido + forecast skill), como piso a superar.
