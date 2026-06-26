# Pipeline Puerto Rico — NSRDB PSM v4

Descarga y consolidación del dataset solar de **Puerto Rico** desde la API NSRDB v4
(GOES aggregated), usando el mismo pipeline anual multi-región (`Utils/descarga_regiones/descargar_regiones.py`).
La malla de nodos (coordenadas) es la misma para cualquier año.

Todos los scripts viven en `Utils/` y usan rutas relativas a la **raíz del
proyecto** (ejecutar desde el directorio raíz). Ver la guía de comandos completa en
**[`GUIA_COMANDOS.md`](../../GUIA_COMANDOS.md)**.

---

## TL;DR — estado final

- **754 nodos/celdas reales** de la rejilla NSRDB v4 (0.04°), índice continuo `0…753`.
- Metadata espacial (year-agnostic): `Data/Puerto_Rico/metadata_nodos_pr.csv`
  (`nodo_id, latitude, longitude, msnm`).
- Dataset COMPLETO 2024 (provisional, **sin 29-feb**): 754 × 8760 = **6 605 040 filas**
  `Data/Puerto_Rico/2024/Finales/completo/dataset_pr_completo_24h_2024.parquet`
- Historia previa (malla 0.02° con 2480 nodos): `Data/Puerto_Rico/historico_2480_0.02/`
  (metadata original intacta, por si se quiere reconstruir).
- Provenance del recorte: `Data/Puerto_Rico/malla_4km_propuesta/`
  (`metadata_nodos_pr_4km.csv` y `mapeo_pr_4km.csv` viejo→nuevo).

La malla **conserva las 754 celdas completas**, incluyendo:
- las **158 celdas con `msnm==0`** (mar/costa) — no se filtraron;
- las **109 celdas al este** (lon > −65.1, lat 17.65–18.77) sobre las **Islas
  Vírgenes (USVI/BVI)**, fuera de PR — se decidió mantenerlas.

---

## El hallazgo clave (rejilla NSRDB)

La malla de referencia original (`metadata_nodos_pr.csv`, 2480 nodos) se generó con
paso **0.02°**, el **doble de fino** que la rejilla real de NSRDB v4, que es de
**0.04°**. Como la malla era más densa que la rejilla real, varios nodos distintos
caían en la **misma celda** del satélite → duplicados.

Síntoma detectado al comparar las coordenadas solicitadas con las que devolvió la
API en la descarga 2024: un **desvío uniforme de exactamente 0.01°** en lat y lon en
los 2480 nodos. Al deduplicar por `location_id` (el identificador real de celda de
NSRDB) los **2480 nodos colapsan en solo 754 celdas físicas únicas**:

| Nodos por celda real | Nº de celdas |
|---|---|
| 1 (único)            | 71  |
| 2                    | 143 |
| 3                    | 37  |
| 4                    | 503 |

Es decir, **1726 de los 2480 nodos eran copias** (mismo `location_id`, misma serie
temporal). Las 503 celdas con 4 nodos son el patrón de sobre-muestreo 2×2 (cuatro
puntos a 0.02° dentro de una celda de 0.04°).

> Tamaulipas **no** tuvo este problema en su malla final: su rejilla a 0.04° coincide
> exacta con NSRDB (Δ=0, location_id únicos).

---

## Qué se hizo (corrección)

1. **`Utils/descarga_regiones/generar_malla_pr_4km.py`** — construyó la malla correcta a partir de las
   **coordenadas reales** devueltas por la API (deduplicando por `location_id`),
   reindexó `0…753` y dejó en staging la metadata + el mapeo viejo→nuevo, más un mapa
   de verificación con fondo satelital (`Results/Puerto_Rico/malla_4km_propuesta.png`).
2. **`Utils/descarga_regiones/filtrar_pr_4km.py`** — aplicó la malla sobre lo ya descargado (año 2024):
   - verificó que los duplicados fueran **idénticos** antes de borrar nada;
   - movió la metadata original a `historico_2480_0.02/` y la reemplazó por la de 754;
   - filtró y reindexó los crudos (de 2480 → 754, eliminando los duplicados);
   - regeneró el dataset completo consolidado.

Ninguna operación perdió información: los nodos eliminados eran copias exactas y el
mapeo permite reconstruir la estructura previa.

---

## Pendiente / siguiente paso

El dataset 2024 actual es **provisional**: proviene de crudos descargados **antes**
del arreglo del día bisiesto, por lo que **no incluye el 29-feb** (8760 h en vez de
8784). Para tener 2024 definitivo con el 29-feb, re-descargar con la malla nueva
(ahora son **754 consultas** en vez de 2480):

```bash
# El pipeline es reanudable; borrar primero el año para forzar la re-descarga con bisiesto:
rm -rf Data/Puerto_Rico/2024
python -m Utils.descarga_regiones --regiones puerto_rico --anios 2024 --metadatos todos
```

(Por defecto el 29-feb va **incluido**; añadir `--excluir-bisiesto` solo si se quieren
años homogéneos de 8760 h.)
