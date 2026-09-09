# Fuentes geográficas y de datos del proyecto

Qué se descargó, de dónde, con qué herramientas y en qué sistema de coordenadas.
Pensado para citar en la metodología: cada fuente lleva su edición exacta, su URL
y la fecha en que se bajó.

Última revisión: **2026-09-09**.

---

## Aviso de terminología: "malla" son dos cosas distintas

En este proyecto conviven dos tipos de referencia espacial y conviene no
mezclarlos al escribir:

| | qué es | ejemplo |
|---|---|---|
| **Marco geoestadístico** | polígonos vectoriales de unidades administrativas | municipios, localidades urbanas |
| **Malla / retícula** | rejilla regular de puntos o celdas | NSRDB 0.04°, ERA5 0.25° y 0.1° |

Los municipios y cabeceras **no** se ubican con una malla: se ubican con el
**Marco Geoestadístico Nacional** del INEGI, que es cartografía vectorial.

---

## 1 · Marco Geoestadístico Nacional (MGN) — INEGI

Es la base de todo lo administrativo: municipios, localidades y sus polígonos.

| campo | valor |
|---|---|
| Producto | Marco Geoestadístico, **edición 2025** |
| Cobertura | Paquete estatal **Tamaulipas** (clave de entidad `28`) |
| Id de producto | `794551163061` |
| Formato | Shapefile (ESRI), 15 capas |
| Tamaño | 74 MB comprimido |
| Fecha del paquete | 2025-12-03 (sello interno del ZIP) |
| **Descargado** | **2026-09-07** |

**URL directa**

```
https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/bvinegi/productos/geografia/marcogeo/794551163061/28_tamaulipas.zip
```

Portal del programa: <https://www.inegi.org.mx/programas/mg/>

Para cambiar de edición basta editar `EDICION_MG` e `ID_PRODUCTO_MG` en
`urbano/config.py`; si el INEGI retira el id, la descarga falla con un mensaje
que dice qué actualizar.

### Capas del paquete estatal

Las **dos que usa el pipeline** van marcadas:

| capa | registros | geometría | contenido |
|---|---|---|---|
| **`28l`** ✅ | 1 314 | polígono | **localidades amanzanadas** (campo `AMBITO`: Urbana/Rural) — la *mancha urbana* |
| **`28mun`** ✅ | 43 | polígono | **áreas geoestadísticas municipales** |
| `28ent` | 1 | polígono | área geoestadística estatal |
| `28a` | 2 472 | polígono | AGEB urbanas |
| `28ar` | 742 | polígono | AGEB rurales |
| `28m` | 97 980 | polígono | manzanas |
| `28lpr` | 13 896 | punto | localidades rurales puntuales |
| `28cd` | 1 294 | multipunto | caseríos dispersos |
| `28e` | 257 467 | línea | ejes de vialidad |
| `28fm` | 432 917 | línea | frentes de manzana |
| `28pe` / `28pem` | 1 188 / 126 | polígono | polígonos externos |
| `28sia` / `28sil` / `28sip` | 6 485 / 4 409 / 14 546 | pol./lín./punto | servicios e infraestructura |

`28a` y `28lpr` están declaradas en `urbano/config.py` para uso futuro, pero el
código actual **no las lee**.

### Lo que el MGN NO trae

**No indica cuál localidad es la cabecera municipal.** El MGN solo da la clave
`CVE_LOC`. Se usó durante un tiempo la convención "la localidad `0001` es la
cabecera" y **es falsa en 1 de los 43 municipios** (ver §2).

---

## 2 · Catálogo Único de Claves de Áreas Geoestadísticas (AGEEML) — INEGI

Necesario porque el MGN no marca las cabeceras. Su tabla de municipios trae las
columnas `CVE_CAB` y `NOM_CAB`.

| campo | valor |
|---|---|
| Producto | Catálogo Único de Claves… (AGEEML), tabla de **municipios** |
| Tamaño | 532 KB |
| **Descargado** | **2026-09-08** |

```
https://www.inegi.org.mx/contenidos/app/ageeml/catun_municipio.zip
```

Portal: <https://www.inegi.org.mx/app/ageeml/>

**El caso que lo motivó — Gómez Farías (municipio 011):** su localidad `0001` es
*Loma Alta (Loma Alta de Gómez Farías)*, la más poblada, pero la cabecera es
*Gómez Farías*, la `0036`. Es la **única excepción de los 43**, y basta una para
que un catálogo de cabeceras muestre el pueblo equivocado. Confirmado también con
el [Gobierno de Tamaulipas](https://www.tamaulipas.gob.mx/estado/municipios/gomez-farias/):
*"Gómez Farías (cabecera municipal), poblado Loma Alta, …"*.

Las 43 filas resultantes se versionan en `Data/Tamaulipas/cabeceras_inegi.csv`
para que el pipeline no dependa de la red ni de que la URL siga viva.

---

## 3 · Mallas de datos

### 3.1 NSRDB — NREL (la malla principal del proyecto)

| campo | valor |
|---|---|
| Producto | **NSRDB GOES aggregated, PSM v4** (`version = 4.0.1`) |
| Resolución | **0.04°** ≈ 4.4 km (lat) × 4.1 km (lon) → celdas de ~18 km² |
| Nodos en Tamaulipas | **4 384** (136 lat × 75 lon, con recorte) |
| Periodo en disco | **2020–2024** (previsto extender a 2025) |
| Paso temporal | horario, **UTC** |

Endpoint de descarga (ver `Utils/descarga_regiones/`):

```
https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv
```

Documentación de variables y unidades: `Data/Tamaulipas/REFERENCIA_NSRDB.md`.

**Nota de altura**, importante al comparar con estaciones: la meteorología del
NSRDB proviene de la reanálisis **MERRA-2**. `temperature` sale de `T2M` (**2 m**)
y `wind_speed`/`wind_direction` de `U2M`/`V2M` (**2 m**, *no* los 10 m de la
convención OMM). `relative_humidity` y `dew_point` son **derivadas**, no medidas.

### 3.2 ERA5 — Copernicus (CDS)

Se usan dos productos para comparar contra el NSRDB en los mismos puntos:

| producto | dataset del CDS | resolución |
|---|---|---|
| ERA5 single levels | `reanalysis-era5-single-levels` | **0.25°** ≈ 31 km |
| ERA5-Land | `reanalysis-era5-land` | **0.1°** ≈ 9 km (**solo tierra**) |

Portal: <https://cds.climate.copernicus.eu/> · acceso por `cdsapi` con
credenciales en `.env` (`URL_ERA5`, `KEY_ERA5`), nunca en el código.

**Disponibilidad verificada el 2026-09-09: 2025 está completo en ambos.**
No se dio por hecho: ERA5-Land suele ir con dos o tres meses de retraso, así que
`copernicus.descarga --disponibilidad ANIO` lo comprueba con una petición mínima.

Dos diferencias que afectan a cualquier comparación:

- **`ssrd` acumula distinto en cada producto**: ERA5 sobre la hora anterior,
  ERA5-Land **desde las 00 UTC del día**. Detalle completo en
  `copernicus/README.md`.
- **El viento de ERA5 es a 10 m** y el del NSRDB a 2 m. No son el mismo dato.

---

## 4 · OpenStreetMap

Dos usos, ninguno en el cálculo de manchas urbanas:

1. **Regiones administrativas** (`Utils/asignar_regiones.py`, trabajo previo):
   relaciones `boundary=administrative` con `admin_level=6`, vía **Overpass API**,
   filtradas por la etiqueta `INEGI:MUNID` con prefijo `28`. El propio OSM declara
   que esos polígonos derivan del **MGN 2014 v6.2**. Sirven para las 6 regiones
   oficiales del estado, no para los municipios del análisis urbano.
2. **Mosaicos de referencia** de los mapas `_base` (carreteras, calles,
   topónimos), vía `contextily`. Solo fondo cartográfico.

El servidor de mosaicos de OSM rechaza el *user-agent* por omisión de
`contextily` con un 403; `urbano/mapas/estilo.py` declara uno propio, como pide
su política de uso. Los mosaicos se cachean en `cache/tiles/`.

---

## 5 · Sistemas de coordenadas

| EPSG | nombre | uso en el proyecto |
|---|---|---|
| **6372** | Cónica Conforme de Lambert de México (ITRF2008) | **Todo** cálculo de área, distancia e intersección. Es el CRS nativo del MGN. |
| **4326** | WGS 84 lat/lon | Coordenadas de los nodos NSRDB y de las celdas ERA5 |
| **3857** | Web Mercator | **Solo** para pegar mosaicos de fondo |

Dos cosas que dependen de esto:

- Las áreas urbanas y las distancias nodo↔ciudad se calculan **siempre en 6372**;
  hacerlo en 4326 daría "grados cuadrados", que no son km².
- En los mapas con mosaico (3857) la **barra de escala se corrige por
  `1/cos(latitud)`**: en Web Mercator el "metro" del eje no es un metro en el
  suelo, y a 25 °N el error sería del 10 %.

---

## 6 · Herramientas

| paquete | versión | para qué |
|---|---|---|
| `geopandas` | 1.1.3 | shapefiles, intersecciones, joins espaciales |
| `shapely` | 2.1.2 | geometría (áreas, distancias, uniones) |
| `pyproj` | 3.7.2 | reproyecciones |
| `pyogrio` | 0.13.0 | motor de E/S vectorial |
| `contextily` | 1.7.0 | mosaicos de referencia |
| `folium` | 0.20.0 | mapa interactivo |
| `xarray` | 2026.7.0 | NetCDF de ERA5 |
| `cdsapi` | 0.7.7 | cliente del Copernicus CDS |
| `netcdf4` / `dask` | 1.7.4 / 2026.8.0 | lectura y cómputo diferido |

Entorno conda `rs`; todas fijadas en `requeriments.txt`.

---

## 7 · Qué se versiona y qué se regenera

Los crudos son grandes y reproducibles, así que **no** van al repo. Lo que sí se
versiona es el resultado ligero y la receta para rehacerlo.

| se versiona | se regenera |
|---|---|
| `Data/Tamaulipas/cabeceras_inegi.csv` (43 filas) | `cache/inegi/` — paquetes del INEGI (74 MB) |
| `Data/Tamaulipas/urbano/*.csv` — manchas, nodos, cobertura | `cache/tiles/` — mosaicos OSM |
| `nodos_interes*.csv` — nodos señalados a mano | `Data/**/era5/` — NetCDF y series (GB) |
| `Results/Tamaulipas/urbano/*.png` — mapas | `Data/**/*.parquet` — datasets NSRDB |

Comandos para rehacerlo todo:

```bash
conda run -n rs python -m urbano.construir            # MGN + manchas + nodos + mapas
conda run -n rs python -m urbano.data.cabeceras       # catálogo de cabeceras
conda run -n rs python -m copernicus.descarga         # ERA5
```

---

## Cómo citar

- INEGI (2025). *Marco Geoestadístico, diciembre 2025.* Instituto Nacional de
  Estadística y Geografía. Paquete estatal Tamaulipas (28).
- INEGI. *Catálogo Único de Claves de Áreas Geoestadísticas Estatales,
  Municipales y Localidades.* Tabla de municipios.
- NREL. *National Solar Radiation Database (NSRDB), GOES aggregated PSM v4.0.1.*
  National Renewable Energy Laboratory.
- Hersbach, H. et al. *ERA5 hourly data on single levels* y *ERA5-Land hourly
  data*, Copernicus Climate Change Service (C3S) Climate Data Store.
- OpenStreetMap contributors. Datos bajo ODbL.
