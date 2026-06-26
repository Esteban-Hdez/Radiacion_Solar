# Pipeline Puerto Rico 2017 — NSRDB PSM v4

Scripts de **descarga y preprocesamiento** del dataset solar de Puerto Rico,
año 2017, generación **PSM v4 (GOES aggregated)** de NSRDB/NREL.

La malla es de **2,480 nodos**, extraídos del archivo HDF5 oficial
`Data/datos_nsrdb/nsrdb_puerto_rico_2017.h5`. Cada nodo se descarga vía la API
NSRDB como una serie horaria de 8,760 registros (año completo, intervalo 60 min).

> **Nota de ejecución:** todos los scripts usan rutas relativas a la **raíz del
> proyecto** (`Data/...`), por lo que deben ejecutarse desde el directorio raíz,
> no desde esta carpeta:
> ```bash
> python Utils/puerto_rico_v4_2017/<script>.py
> ```

---

## Flujo del pipeline

```
extraer_coordenadas.py            (auxiliar: metadata espacial de los nodos)
        │
        ▼
descarga_masiva_v4_completa.py    [1] descarga todas las variables por nodo
        │                             → Data/Puerto_Rico_v4_2017/crudos_api/2017_V4_Completo/  (2480 parquet)
        │
        ├─ parche_red_v4.py        [1b] re-descarga nodos faltantes por fallas de red
        │
        ▼
consolidar_limpiar_v4.py          [2] une los 2480 parquet en un solo dataset
        │                             → Finales/completo/dataset_maestro_v4_2017_completo.parquet  ◄── COMPLETO
        ▼
filtro_diurno_v4.py               [3] filtra horas diurnas y recorta columnas
                                      → Finales/filtrado/dataset_v4_filtrado_diurno_2017.parquet  ◄── FILTRADO
```

---

## Scripts

### `extraer_coordenadas.py`  *(auxiliar)*
Lee el grupo `meta` del HDF5 y exporta la topología espacial de los 2,480 nodos
(lat, lon, elevación→`msnm`, etc.).
- **Entrada:** `Data/datos_nsrdb/nsrdb_puerto_rico_2017.h5`
- **Salida:** `Data/Puerto_Rico_v4_2017/metadata_nodos_pr.csv`

### `descarga_masiva_v4_completa.py`  *(paso 1 — descarga)*
Descarga **todas** las variables de la API v4 (sin `attributes`, matriz completa)
para cada nodo y las guarda como parquet individual. Tolerante a fallos mediante
un log de checkpoint; reanudable.
- **Entrada:** coordenadas del HDF5 (2,480 nodos)
- **Salida:** `Data/Puerto_Rico_v4_2017/crudos_api/2017_V4_Completo/nodo_<id>_2017_v4.parquet`
- **Checkpoint:** `Data/Puerto_Rico_v4_2017/crudos_api/nodos_completados_v4.log`

### `parche_red_v4.py`  *(paso 1b — recuperación)*
Escanea el directorio de salida, detecta qué nodos (de 0 a 2479) faltan por
fallas de red y los vuelve a descargar. Ejecutar antes de consolidar si la
descarga masiva se interrumpió.

### `consolidar_limpiar_v4.py`  *(paso 2 — consolidación → COMPLETO)*
Une los 2,480 parquet en un único dataset maestro, normaliza nombres de columnas
a snake_case y valida la integridad (2480 × 8760 = 21,724,800 filas). Ofrece
borrar los parquet individuales tras una validación exitosa.
- **Salida:** `Data/Puerto_Rico_v4_2017/Finales/completo/dataset_maestro_v4_2017_completo.parquet`
  - **21,724,800 filas × 31 columnas** (todas las variables, las 24 h)

### `filtro_diurno_v4.py`  *(paso 3 — filtrado → FILTRADO)*
Selecciona las variables relevantes, crea el índice `datetime` y aplica el
**doble filtro astronómico** (`clearsky_ghi > 0` **y** `solar_zenith_angle < 85°`)
para conservar solo horas diurnas.
- **Entrada:** `Finales/completo/dataset_maestro_v4_2017_completo.parquet`
- **Salida:** `Data/Puerto_Rico_v4_2017/Finales/filtrado/dataset_v4_filtrado_diurno_2017.parquet`
  - **10,273,022 filas × 17 columnas** (47.3 % retenido)

---

## Archivos resultantes (en `Data/Puerto_Rico_v4_2017/`)

| Ruta | Rol | Dimensiones |
|---|---|---|
| `Finales/completo/dataset_maestro_v4_2017_completo.parquet` | **COMPLETO** (crudo, todas las variables, 24 h) | 21,724,800 × 31 |
| `Finales/filtrado/dataset_v4_filtrado_diurno_2017.parquet` | **FILTRADO** (diurno, listo para modelado) | 10,273,022 × 17 |
| `metadata_nodos_pr.csv` | Metadata espacial de los 2,480 nodos | 2,480 filas |
| `crudos_api/2017_V4_Completo/` | descargas crudas por nodo de la API | 2,480 parquet |

### Columnas del dataset FILTRADO (17)
`nodo_id, datetime, year, month, day, hour, ghi, dni, dhi, clearsky_ghi,
temperature, pressure, wind_speed, precipitable_water, cloud_type,
solar_zenith_angle, RH_Promedio_Horario`

---

## Referencias en notebooks
- `get_data.ipynb` ejecuta `consolidar_limpiar_v4.py` y `filtro_diurno_v4.py`
  con la ruta actualizada `Utils/puerto_rico_v4_2017/...`.
