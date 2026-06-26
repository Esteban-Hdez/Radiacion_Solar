# Pipeline de descarga por región y año (`Utils/descarga_regiones/`)

Paquete que descarga y consolida cualquier año de **Tamaulipas (4384 nodos)** y
**Puerto Rico (754 nodos)** usando las **coordenadas reales finales** de cada región
(`Data/Tamaulipas/metadata_nodos_tamaulipas.csv`,
`Data/Puerto_Rico/metadata_nodos_pr.csv`). El orquestador multi-región es
`descargar_regiones.py` (`python -m Utils.descarga_regiones`).

El ejemplo de abajo usa Tamaulipas, pero aplica igual a Puerto Rico cambiando la
región/metadata.

Como esas coordenadas son centros de celda de la rejilla 0.04° ya confirmados por
la API, **no hay que regenerar la malla ni deduplicar ni verificar alineación**:
solo se descargan las series del año pedido sobre esos mismos nodos. El `nodo_id`
es idéntico entre años, así que todo es comparable y se une por `nodo_id`.

> Estos scripts **reemplazan**, para años nuevos, a los de configuración inicial de
> 2017 (`descarga_masiva_tamaulipas.py`, `parche_tamaulipas_v4.py`,
> `consolidar_tamaulipas_completo.py`), que quedaron como histórico del armado.

Ejecutar **como módulo** desde la raíz del proyecto.

> **Orquestador recomendado:** `Utils/descarga_regiones/descargar_regiones.py` engloba estos scripts y
> corre **varias regiones** (Tamaulipas y Puerto Rico) y varios años de una sola vez
> (descarga → parche → consolidación). Ver la guía de comandos completa en
> **[`GUIA_COMANDOS.md`](../../GUIA_COMANDOS.md)**.
>
> **Día bisiesto (29-feb):** desde 2026-06 el pipeline **incluye el 29-feb por
> defecto** (años bisiestos = 8784 h; normales = 8760 h). Para años homogéneos de
> 8760 h, añadir `--excluir-bisiesto` a cualquiera de los comandos.

---

## Flujo para un año nuevo (ej. 2018)

```bash
# 1) Descargar (reanudable; respeta el límite diario de la API)
python -m Utils.descarga_regiones.descargar_anio --anio 2018
#    opcional: guardar metadatos del año -> 'todos' (47 campos) o 'cambian' (solo por nodo)
python -m Utils.descarga_regiones.descargar_anio --anio 2018 --metadatos todos

# 2) Recuperar nodos que fallaron por red (si los hubo)
python -m Utils.descarga_regiones.parche_anio --anio 2018

# 3) Consolidar el dataset COMPLETO unificado
python -m Utils.descarga_regiones.consolidar_anio --anio 2018
```

Estructura creada (parametrizada por año):

```
Data/Tamaulipas/2018/
  crudos_api/                              nodo_<0..4383>_2018_v4.parquet  + nodos_completados_2018.log
  Finales/completo/
    dataset_tamaulipas_completo_24h_2018.parquet
  metadata_nodos_2018.csv                  (solo si --guardar-metadatos)
```

El dataset COMPLETO sale con la misma ingeniería que 2017 (datetime, dtypes
compactos int16/int8/float32, `minute` eliminado, columnas UV renombradas, orden
`nodo_id`→`datetime`, compresión zstd).

---

## Scripts

| Script | Qué hace |
|---|---|
| `_comun.py` | utilidades compartidas: credenciales, carga de las coordenadas finales, descarga de un nodo-año, rutas por año. |
| `descargar_anio.py` | descarga los 4384 nodos para `--anio`. Reanudable (checkpoint), maneja 429. Opciones `--metadatos {todos,cambian}`, `--limite N`, `--excluir-bisiesto`. |
| `parche_anio.py` | re-descarga los nodos faltantes del año (fallas de red). Ahora **también guarda metadata** con `--metadatos`. |
| `recuperar_metadata.py` | recupera la cabecera de nodos que ya tienen parquet pero **sin fila de metadata** (típico de parches antiguos). Reusable por región/año/ids. |
| `consolidar_anio.py` | une los crudos del año en el dataset COMPLETO (`Finales/completo/`). |
| `consultar_cupo.py` | consulta el cupo diario restante de la API (cuesta 1 petición). |
| `descargar_varios_anios.py` | orquestador **solo Tamaulipas** (legacy). Para multi-región usar `Utils/descarga_regiones/descargar_regiones.py`. |

---

## Descarga secuencial de varios años (desatendida)

Procesa los años en orden: por cada uno, descarga → parche (máx. 2 intentos) →
consolida si están los 4384 nodos. Si tras 2 parches aún faltan nodos (red), pasa
al siguiente año. Si la API agota la cuota diaria (429), se detiene de forma segura
y es **reanudable** al día siguiente con el mismo comando. Solo 2018 guarda
metadatos (`--metadatos cambian`).

```bash
conda activate rs
PYTHONUNBUFFERED=1 nohup python -m Utils.descarga_regiones.descargar_varios_anios \
  --anios 2018 2019 2020 2021 2022 2023 \
  > Data/Tamaulipas/registro_multianio.log 2>&1 &

# seguir el avance:
tail -f Data/Tamaulipas/registro_multianio.log
```

---

## Metadatos opcionales por año (`--metadatos`)

Guarda `Data/Tamaulipas/<anio>/metadata_nodos_<anio>.csv`:

- **`--metadatos todos`** — toda la cabecera de NSRDB (47 campos): localización,
  unidades por variable, diccionarios de `cloud_type`/`fill_flag`, husos y versión.
- **`--metadatos cambian`** — solo los que **varían por nodo**: `location_id`,
  `latitude`, `longitude`, `elevation`.
- *(sin la opción)* — no guarda metadatos.

Los campos **constantes** (unidades, diccionarios de códigos, husos `−6`,
`version=4.0.1`) están documentados en
**`Data/Tamaulipas/REFERENCIA_NSRDB.md`** — útil para decodificar `cloud_type`
(0 Clear … 12 Smoke) y `fill_flag` (1 Missing Image … 5 Rayleigh Violation).

> El `.env` debe tener `API_KEY` y `EMAIL_USUARIO`.
