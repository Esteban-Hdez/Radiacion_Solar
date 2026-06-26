# Pipeline Puerto Rico 2017 — NSRDB físico (HDF5) + complemento API v4

Scripts de **descarga y preprocesamiento** del dataset solar de Puerto Rico,
año 2017, construido a partir de los **archivos HDF5 oficiales** de NSRDB
(`Data/datos_nsrdb/nsrdb_puerto_rico_*.h5`, resolución nativa de 5 minutos,
2,480 nodos), complementado con dos variables descargadas de la **API v4**
que **no existen** en el HDF5 (`cloud_type`, `relative_humidity`).

> Este es el flujo **"v3"** (base física del HDF5). El flujo **v4** (todo desde
> la API v4) vive en `Utils/puerto_rico_v4_2017/`. El año 2017 es el **año de
> prueba**; `etl_solar.py` es genérico y sirve para cualquier año.

> **Nota de ejecución:** rutas relativas a la **raíz del proyecto**. Ejecutar
> desde el directorio raíz: `python Utils/puerto_rico_v3_2017/<script>.py`
> (`etl_solar.py` se invoca como módulo desde el notebook, no por CLI).

---

## Flujo del pipeline

```
                         HDF5 (5 min, 2480 nodos)
                          │                    │
   etl_solar.py [A]       │                    │   consolidar_v3_completo_24h.py [E]
   (horario + filtro      │                    │   (horario SIN filtro, mismas reglas)
    diurno)               ▼                    ▼
        intermedios/nsrdb_pr_preprocesado    física 24 h (en memoria)
        _2017.parquet/csv  (físico diurno)         │
                          │                         │
   API ─ descarga_masiva_2017.py [B] ─ crudos_api/2017/ (2480) ─ paso1 [C] ─┐
                          │                         │                        │
                          │                         │       intermedios/api_consolidada_2017.parquet (24 h)
                          ▼                         ▼                        │
   paso2_fusionar_datasets.py [D]            (fusión 24 h ⋈ 24 h) ◄──────────┘
   (preprocesado diurno ⋈ API)                      │
        │                                           ▼
        ▼                              Finales/completo/dataset_v3_completo_24h_2017.parquet  ◄── COMPLETO (24 h)
   Finales/filtrado/dataset_v3_filtrado_diurno_2017.parquet                                   ◄── FILTRADO (diurno)
```

¿Por qué se descargan `cloud_type` y `relative_humidity` de la API? Porque el
HDF5 de Puerto Rico **solo contiene** estas variables: `air_temperature`,
`clearsky_dhi/dni/ghi`, `dhi`, `dni`, `ghi`, `solar_zenith_angle`,
`surface_albedo`, `surface_pressure`, `total_precipitable_water`, `wind_speed`.
No trae nubosidad ni humedad relativa, así que se traen de la API v4 y se fusionan.

---

## Scripts y algoritmos

### `etl_solar.py`  *(paso A — ingeniería de características, base intermedia)*
Función `procesar_nsrdb_anual(h5_path, output_dir, formato_salida)`. Lee la matriz
cruda de 5 min `(105 120 pasos × 2 480 nodos)`, le aplica el `psm_scale_factor`
de cada variable, la remodela a `(8 760 horas, 12 sub-pasos, nodos)` y **colapsa
los 12 registros intrahorarios** con una regla distinta por variable:

| Regla | Algoritmo | Variables |
|---|---|---|
| **Promedio** | `np.nanmean` sobre los 12 sub-pasos | `ghi`, `dni`, `dhi`, `clearsky_ghi`, `air_temperature`, `surface_pressure`, `wind_speed`, `total_precipitable_water` |
| **Minuto 30** | toma el sub-paso índice 6 (minuto :30, instante representativo) | `solar_zenith_angle` |
| **Moda** | `scipy.stats.mode` | `cloud_type` *(condicional)* |
| **Máximo** | `np.nanmax` | `cloud_opacity` *(condicional)*, `RH_Max_Intrahorario` |
| **Promedio + Máximo** | ambas reglas sobre la misma variable | `relative_humidity` → `RH_Promedio_Horario` *(condicional)* |

> Las reglas marcadas *(condicional)* solo se ejecutan si la variable existe en
> el HDF5. En el HDF5 de Puerto Rico **no existen** `cloud_type`,
> `relative_humidity` ni `cloud_opacity`, así que para 2017 estas reglas no
> producen columnas — esas variables llegan por la API (pasos B–D).

**Filtro diurno (doble criterio astronómico)** aplicado al final:
`clearsky_ghi > 0` **y** `solar_zenith_angle < 85°` → descarta noche y crepúsculos.

- **Salida:** `Data/Puerto_Rico_v3_2017/intermedios/nsrdb_pr_preprocesado_2017.{parquet,csv}`
  - **10,220,576 filas × 13 columnas** (físico, solo horas diurnas) — base intermedia
  - *(el `output_dir` lo decide el notebook que invoca la función)*

### `descarga_masiva_2017.py`  *(paso B — descarga complementaria)*
Descarga de la API v4 **solo** `cloud_type, relative_humidity, air_temperature`
(60 min, 24 h) para los 2,480 nodos. Reanudable vía log de checkpoint.
- **Salida:** `Data/Puerto_Rico_v3_2017/crudos_api/2017/nodo_<id>_2017.parquet` (2,480 archivos)
- **Checkpoint:** `Data/Puerto_Rico_v3_2017/crudos_api/nodos_completados_2017.log`

### `paso1_consolidar_api.py`  *(paso C — consolidación de la API)*
Une los 2,480 parquet de la API en una sola tabla, normaliza columnas y elimina
`minute`. Valida `2480 × 8760 = 21,724,800` filas.
- **Salida:** `Data/Puerto_Rico_v3_2017/intermedios/api_consolidada_2017.parquet` (24 h, 8 columnas)

### `paso2_fusionar_datasets.py`  *(paso D — fusión diurna → FILTRADO)*
**Inner merge** del preprocesado físico (ya diurno) con la API consolidada, por
la llave `[nodo_id, year, month, day, hour]`. Al ser *inner*, la API se recorta
a las horas diurnas. Descarta la `temperature` de la API (conserva la
`air_temperature` del HDF5).
- **Salida:** `Data/Puerto_Rico_v3_2017/Finales/filtrado/dataset_v3_filtrado_diurno_2017.parquet`
  - **10,220,576 filas × 17 columnas** (físicas + `cloud_type` + `relative_humidity`, **diurno**)

### `consolidar_v3_completo_24h.py`  *(paso E — fusión 24 h → COMPLETO)*
Reconstruye la base física horaria **sin** el filtro diurno (reutilizando las
mismas reglas de `etl_solar`: promedio intrahorario y minuto-30 para el ángulo
cenital) y la fusiona con la API consolidada (24 h). Equivale al COMPLETO de v4.
- **Salida:** `Data/Puerto_Rico_v3_2017/Finales/completo/dataset_v3_completo_24h_2017.parquet`
  - **21,724,800 filas × 17 columnas** (físicas + `cloud_type` + `relative_humidity`, **24 h**)
  - *Validado:* al aplicar el filtro diurno a este dataset se obtienen exactamente
    10,220,576 filas, idénticas al FILTRADO.

---

## Archivos resultantes (en `Data/Puerto_Rico_v3_2017/`)

| Ruta | Rol | Dimensiones |
|---|---|---|
| `Finales/completo/dataset_v3_completo_24h_2017.parquet` | **COMPLETO** (todas las variables, **24 h**) | 21,724,800 × 17 |
| `Finales/filtrado/dataset_v3_filtrado_diurno_2017.parquet` | **FILTRADO** (todas las variables, **diurno**) | 10,220,576 × 17 |
| `intermedios/nsrdb_pr_preprocesado_2017.parquet` / `.csv` | base física diurna (paso previo a la fusión) | 10,220,576 × 13 |
| `intermedios/api_consolidada_2017.parquet` | complemento meteo de la API (24 h) | 21,724,800 × 8 |
| `crudos_api/2017/` | descargas crudas por nodo de la API | 2,480 parquet |

> Con esta organización **v3 queda paralelo a v4**: el **completo** es de 24 h con
> todas las variables y el **filtrado** es su subconjunto diurno
> (`clearsky_ghi > 0` y `solar_zenith_angle < 85°`).

---

## Referencias en notebooks
- `analisis.ipynb` importa `from Utils.puerto_rico_v3_2017.etl_solar import procesar_nsrdb_anual` y escribe el preprocesado a `intermedios/` (rutas ya actualizadas).
