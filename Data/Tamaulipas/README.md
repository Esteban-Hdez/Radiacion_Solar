# Pipeline Tamaulipas — NSRDB PSM v4 (año de prueba 2017)

Descarga, confirmación de coordenadas, deduplicación, **filtrado de costa** y
consolidación del dataset solar de **Tamaulipas** desde la API NSRDB v4 (GOES
aggregated). El año 2017 es el **año de prueba**; la malla de nodos (coordenadas)
es la misma para cualquier año.

Todos los scripts viven en `Utils/` y usan rutas relativas a la **raíz del
proyecto** (ejecutar desde el directorio raíz).

---

## TL;DR — estado final

- **4384 nodos** sobre tierra, coordenadas **100 % confirmadas por la API**, índice
  continuo `0…4383`. (Se partió de 4940 solicitados → 4501 celdas reales únicas →
  4384 tras quitar 117 nodos de mar/laguna/isla.)
- Dataset COMPLETO unificado (24 h, todas las variables), listo para modelos:
  `Data/Tamaulipas/2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet`
- Metadata espacial (year-agnostic): `Data/Tamaulipas/metadata_nodos_tamaulipas.csv`
- Historia previa (4501 nodos, con mar): `Data/Tamaulipas/historico_4501_con_mar/`
  (intacta, por si se desea reincluir esos nodos).

---

## El hallazgo clave (rejilla NSRDB)

La malla se generó con paso **0.038°**, pero la rejilla real de NSRDB v4 es de
**0.04°**. Por eso las coordenadas solicitadas no coinciden con las que devuelve el
satélite ("desfasamiento") y, al ser la malla **más densa** que la rejilla real,
varios nodos distintos caen en la **misma celda** → duplicados.

El *snapping* de NSRDB es determinista (rejilla regular):

```
paso       = 0.04°
offset lat = 0.01°   ->  rejilla lat: ..., 22.37, 22.41, 22.45, ...
offset lon = 0.02°   ->  rejilla lon: ..., -99.06, -99.02, -98.98, ...
empates    = round half AWAY FROM ZERO   (lat -> norte, lon -> oeste)
```

Validado contra **4927/4927** nodos confirmados por la API. (Ojo: la reconstrucción
puramente matemática tiene un detalle de punto flotante en las fronteras exactas de
celda; por eso las coordenadas definitivas son las **confirmadas por la API**, no las
reconstruidas.)

---

## Etapas del pipeline

### 1. Generación de la malla
- **`Utils/legacy/generar_malla_tamaulipas.py`** — frontera de Tamaulipas (OSM), disparo de
  calibración a la API para anclar la rejilla, expansión matemática y recorte
  *point-in-polygon*. ⚠️ Usa `RESOLUCION_GRADOS = 0.038` (origen del desfase; para
  años/regiones nuevas conviene **0.04°**).
- Salida: `Data/Geometria/metadata_nodos_tamaulipas.csv` (4940 nodos solicitados).

### 2. Descarga masiva
- **`Utils/legacy/descarga_masiva_tamaulipas.py`** — descarga las series horarias (todas las
  variables) de los 4940 nodos. Guardó las coordenadas **solicitadas** y la elevación,
  pero **no** las coordenadas reales del satélite.
- **`Utils/legacy/parche_tamaulipas_v4.py`** — re-descarga nodos que fallaron por red.
- Salida cruda: `Data/API_Historico/Tamaulipas_2017_V4_Completo/` (4940 parquet) — se
  conserva como **archivo completo** (no se borra).

### 3. Confirmación de coordenadas reales (API)
- **`Utils/legacy/verificar_alineacion_espacial.py`** — consulta a la API la metadata de cada
  nodo para recuperar su `Latitude`/`Longitude` reales.
- **`Utils/legacy/completar_nodos_faltantes_tamaulipas.py`** — completa los nodos que fallaron
  por red (`lat_nrel = 0`). Resultado: **4940 coordenadas 100 % confirmadas**.
- Salida: `Data/Geometria/metadata_nodos_tamaulipas_final.csv`.
- **`Utils/legacy/reconstruir_coordenadas_grid.py`** y **`graficar_malla_reconstruida.py`** —
  reconstrucción matemática (referencia), **superada** por la verdad de la API.

### 4. Deduplicación + reindexado continuo
- **`Utils/legacy/deduplicar_dataset_tamaulipas.py`** — identifica los **439 duplicados**
  (8.89 %) y se queda con los **4501 nodos canónicos**, renumerados de forma continua
  (0…4500) en el nombre y en el `nodo_id` interno de cada parquet.
- Análisis de duplicados: `Data/Geometria/metadata_nodos_tamaulipas_dedup.csv`.

### 5. Consolidación del dataset COMPLETO
- **`Utils/legacy/consolidar_tamaulipas_completo.py`** — une los parquet en un único archivo
  con **ingeniería para modelos** (ver más abajo).

### 6. Filtrado de nodos sobre agua (mar / laguna / isla)
Los nodos costeros sobre agua (elevación `msnm == 0`) no son de interés. Se
identificaron y se seleccionó manualmente cuáles quitar (**117 nodos**); quedaron
**4384** sobre tierra.
- **`Utils/legacy/identificar_nodos_mar_tamaulipas.py`** — detecta candidatos por `msnm == 0`
  y/o por una selección manual (`--seleccion`), y pinta un mapa de diagnóstico
  (`Results/Tamaulipas/nodos_mar_candidatos.png`).
- **`Utils/seleccion_lasso.py`** (`SelectorNodos`) — selección **interactiva** por lasso
  en el notebook (`%matplotlib widget`); exporta a `nodos_a_eliminar.csv`.
- **`Utils/mapa_interactivo.py`** (`mapa_nodos`) — mapa folium con zoom + satélite para
  inspeccionar nodos puntuales.
- **`Utils/legacy/filtrar_nodos_tamaulipas.py`** — quita los nodos de `nodos_a_eliminar.csv`,
  **reindexa** continuo (0…4383) nombre + `nodo_id` interno, y regenera la metadata y el
  dataset COMPLETO con los **mismos nombres**. No destructivo: archiva la versión de
  4501 (con mar) en `historico_4501_con_mar/`. Ejecutar como módulo:
  `python -m Utils.legacy.filtrar_nodos_tamaulipas`.

> Nota: quedaron a propósito **4 nodos `msnm == 0`** rodeados de tierra (cuerpos de
> agua interiores), para no abrir huecos en la malla terrestre.

> El dataset **filtrado** (diurno) aún no se genera.

---

## Estructura de datos

```
Data/Tamaulipas/
  README.md
  metadata_nodos_tamaulipas.csv          ◄ metadata definitiva (4384 nodos, year-agnostic)
  2017/
    crudos_api/                          4384 parquet por nodo (índice continuo 0..4383)
    Finales/
      completo/
        dataset_tamaulipas_completo_24h_2017.parquet   ◄ DATASET UNIFICADO (4384)
  historico_4501_con_mar/                ◄ versión previa con nodos de mar (intacta)
    metadata_nodos_tamaulipas.csv        (4501)
    nodos_a_eliminar.csv                 (117 nodos seleccionados para quitar)
    nodos_mar_candidatos.csv
    2017/crudos_api/  (4501 parquet)  ·  2017/Finales/completo/ (dataset 4501)

Data/API_Historico/
  Tamaulipas_2017_V4_Completo/           archivo crudo completo (4940 nodos, intacto)

Data/Geometria/                          artefactos del proceso (referencia)
  metadata_nodos_tamaulipas.csv          malla solicitada 0.038° (4940)
  metadata_nodos_tamaulipas_final.csv    4940 nodos con coord real confirmada por API
  metadata_nodos_tamaulipas_dedup.csv    análisis de duplicados (es_duplicado, celda_id)
  metadata_nodos_tamaulipas_reconstruido.csv   reconstrucción matemática (referencia)
  validacion_malla_*.png                 mapas de validación

Results/Tamaulipas/                      mapas y gráficos generados (PNG)
```

---

## Metadata espacial — `Data/Tamaulipas/metadata_nodos_tamaulipas.csv`

4384 filas, una por nodo. Es la **misma para cualquier año** (coordenadas y elevación
no cambian).

| Columna | Descripción |
|---|---|
| `nodo_id` | índice continuo 0…4383 (coincide con el nombre del parquet y su columna interna) |
| `nodo_id_4501` | id en la versión deduplicada con mar (trazabilidad al histórico) |
| `nodo_id_original` | id en la malla cruda de 4940 (trazabilidad) |
| `latitude`, `longitude` | coordenadas **reales** confirmadas por la API (rejilla 0.04°) |
| `msnm` | elevación (m sobre el nivel del mar) |
| `celda_id` | id de celda real NSRDB |

La unión con cualquier dataset se hace por **`nodo_id`**.

---

## Dataset COMPLETO — `dataset_tamaulipas_completo_24h_2017.parquet`

| | |
|---|---|
| Filas | **38,403,840** (4384 nodos × 8760 h, **24 h**, sin filtrar) |
| Columnas | 31 (todas las variables) |
| Tamaño | ~760 MB (compresión **zstd**) |
| Orden | por `nodo_id`, luego `datetime` |

**Ingeniería para modelos:**
- `datetime` como índice temporal (a la hora); filas ordenadas `nodo_id` → `datetime`.
- **dtypes compactos:** `int16` (`nodo_id`, irradiancias, `pressure`, `wind_direction`),
  `int8` (`month`/`day`/`hour`, `cloud_type`, flags), `float32` (resto). Antes int64/float64.
- Eliminada `minute` (constante = 30, redundante).
- Columnas UV renombradas: `ghi_uv_280_400`, `ghi_uv_295_385`.
- **Sin coordenadas por fila** (normalizadas en la metadata); se unen por `nodo_id`.

Columnas: `nodo_id, datetime, year, month, day, hour, ghi, dni, dhi, clearsky_ghi,
clearsky_dni, clearsky_dhi, solar_zenith_angle, cloud_type, cloud_fill_flag, fill_flag,
temperature, dew_point, relative_humidity, pressure, precipitable_water, wind_speed,
wind_direction, surface_albedo, aerosol_optical_depth, alpha, asymmetry, ssa, ozone,
ghi_uv_280_400, ghi_uv_295_385`.

### Uso en modelos

```python
import pandas as pd
df   = pd.read_parquet('Data/Tamaulipas/2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet')
meta = pd.read_csv('Data/Tamaulipas/metadata_nodos_tamaulipas.csv')

# Añadir coordenadas/elevación como features estáticas (si se necesitan):
df = df.merge(meta[['nodo_id', 'latitude', 'longitude', 'msnm']], on='nodo_id', how='left')
```

---

## Visualización

- **`Utils/mapas_espaciales.py`** (`MapaEspacial`) — mapas estáticos (PNG) de cualquier
  variable, con filtros anual/mensual/diario, agregación `media` o `suma_diaria` y panel
  4x3 de 12 meses. Paleta intuitiva automática por variable. CLI y API en Python.
- **`Utils/mapa_interactivo.py`** (`mapa_nodos`) — mapa folium con zoom + satélite.
- Salidas en `Results/Tamaulipas/`.

---

## Descargar más años (pipeline anual)

Las coordenadas reales de los **4384 nodos** ya están confirmadas y son
reutilizables. Para un año nuevo **no** se regenera la malla ni se deduplica: solo
se descargan las series de esos mismos nodos. Scripts en **`Utils/descarga_regiones/`**
(ejecutar como módulo desde la raíz):

```bash
# 1) descargar (reanudable; --limite N para pruebas; --metadatos {todos,cambian} opcional)
python -m Utils.descarga_regiones.descargar_anio --anio 2018 --metadatos todos
# 2) recuperar faltantes por red
python -m Utils.descarga_regiones.parche_anio --anio 2018
# 3) consolidar el COMPLETO del año
python -m Utils.descarga_regiones.consolidar_anio --anio 2018
```

Crea `Data/Tamaulipas/<anio>/crudos_api/` y
`.../Finales/completo/dataset_tamaulipas_completo_24h_<anio>.parquet` (misma
ingeniería que 2017). Detalles en `Utils/descarga_regiones/README.md`.

> Para regiones/años nuevos **desde cero** conviene generar la malla directamente a
> **0.04°** anclada a la rejilla real (evita el desfase del paso 0.038°).

### Metadatos de NSRDB (`--metadatos {todos,cambian}`)

Opción para guardar `Data/Tamaulipas/<anio>/metadata_nodos_<anio>.csv`:

- **`--metadatos todos`** — toda la cabecera de NSRDB (47 campos: localización +
  unidades + diccionarios de códigos + husos + versión).
- **`--metadatos cambian`** — solo los campos que **varían por nodo**: `location_id`,
  `latitude`, `longitude`, `elevation`. (El resto es constante.)
- *(sin la opción)* — no guarda metadatos.

Los campos **constantes** (unidades por variable, husos `local_time_zone=−6`,
`version=4.0.1` y los **diccionarios** de `cloud_type` 0–12 y `fill_flag` 1–5 que
decodifican esas columnas categóricas) están documentados una sola vez en
**[`REFERENCIA_NSRDB.md`](REFERENCIA_NSRDB.md)**.
