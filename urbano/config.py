"""
Configuración del análisis urbano (manchas urbanas INEGI ↔ nodos NSRDB).

Este módulo es INDEPENDIENTE de `forecasting/`: no importa nada de ahí y no
modifica sus datos. Su único producto son dos CSV ligeros y versionados en
`Data/Tamaulipas/urbano/`, que después podrán usarse para agregar métricas de
pronóstico por ciudad.

DECISIÓN CENTRAL — por qué no basta un "punto dentro del polígono":
la malla NSRDB es de 0.04° (≈4.4 km en latitud, ≈4.1 km en longitud a 25 °N),
o sea celdas de ~18 km². De las 63 localidades urbanas de Tamaulipas solo un
puñado (Reynosa 170 km², Nuevo Laredo 127, Matamoros 118, Victoria 71, Tampico 55)
supera el área de UNA celda; la más chica —San Nicolás— mide 0.10 km², 180 veces
menos. Un `point-in-polygon` puro dejaría a la mayoría de las cabeceras sin
ningún nodo. Por eso la asignación es por INTERSECCIÓN CELDA↔MANCHA, con un
fallback explícito al nodo más cercano y una bandera de calidad que dice, para
cada ciudad, qué tan bien la representa su conjunto de nodos.
"""
from __future__ import annotations
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = "Tamaulipas"
CVE_ENT = "28"                       # clave INEGI de Tamaulipas

# --------------------------------------------------------------------------- #
# Fuente: Marco Geoestadístico del INEGI
# --------------------------------------------------------------------------- #
# El paquete estatal se sirve como ZIP bajo un id de producto por edición. El id
# de abajo es el del Marco Geoestadístico 2025 (ficha de biblioteca 794551163061).
# Para cambiar de edición basta cambiar ID_PRODUCTO y EDICION.
EDICION_MG = "2025"
ID_PRODUCTO_MG = "794551163061"
URL_MG = (
    "https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/"
    f"bvinegi/productos/geografia/marcogeo/{ID_PRODUCTO_MG}/"
    f"{CVE_ENT}_tamaulipas.zip"
)

# El shapefile crudo (74 MB) NO se versiona: vive en cache/, que está en .gitignore.
DIR_CACHE = os.path.join(RAIZ, "cache", "inegi")
ZIP_MG = os.path.join(DIR_CACHE, f"mg{EDICION_MG}_{CVE_ENT}_tamaulipas.zip")
DIR_MG = os.path.join(DIR_CACHE, f"mg{EDICION_MG}_{CVE_ENT}")
DIR_SHP = os.path.join(DIR_MG, "conjunto_de_datos")

# Capas del MG que usamos (prefijo = clave de entidad).
def capa(sufijo: str) -> str:
    """Ruta al shapefile `28<sufijo>.shp` del paquete estatal."""
    return os.path.join(DIR_SHP, f"{CVE_ENT}{sufijo}.shp")

CAPA_LOCALIDADES = "l"      # localidades amanzanadas (polígono) -> la mancha urbana
CAPA_MUNICIPIOS = "mun"     # áreas geoestadísticas municipales
CAPA_LOC_RURAL_PUNTO = "lpr"  # localidades rurales puntuales
CAPA_AGEB_URBANA = "a"      # AGEB urbanas (desagregación dentro de ciudades)

# --------------------------------------------------------------------------- #
# Malla NSRDB
# --------------------------------------------------------------------------- #
META_NODOS = os.path.join(RAIZ, "Data", REGION, "metadata_nodos_tamaulipas.csv")
RUTA_REGIONES = os.path.join(RAIZ, "Data", REGION, "regiones_tamaulipas.csv")
PASO_MALLA = 0.04           # grados; verificado sobre la metadata (136 lat × 75 lon)

# --------------------------------------------------------------------------- #
# CRS
# --------------------------------------------------------------------------- #
# 4326 para la malla (así vienen lat/lon del NSRDB) y 6372 (Cónica Conforme de
# Lambert de México, metros) para TODO cálculo de área, distancia o intersección.
# El MG ya viene en 6372, así que no se le aplica ninguna reproyección de ida.
CRS_GEO = "EPSG:4326"
CRS_METRICO = "EPSG:6372"
CRS_MAPA = "EPSG:3857"      # Web Mercator, solo para pegar mosaicos de fondo

# --------------------------------------------------------------------------- #
# Parámetros de la asignación
# --------------------------------------------------------------------------- #
# Dos manchas urbanas separadas por menos de esto se consideran un mismo
# CONGLOMERADO urbano (p. ej. Tampico–Cd. Madero–Altamira–Miramar). Es una
# alternativa data-driven a la lista oficial de zonas metropolitanas: no depende
# de una delimitación externa y se recalcula sola si cambia la edición del MG.
GAP_CONGLOMERADO_M = 2000.0

# Umbrales de la bandera `calidad` (ver nodos/asignacion.py).
MIN_NODOS_ALTA = 3          # >= 3 nodos con centro dentro de la mancha
MIN_NODOS_MEDIA = 1         # >= 1 nodo con centro dentro de la mancha

# --------------------------------------------------------------------------- #
# Salidas
# --------------------------------------------------------------------------- #
DIR_SALIDA_DATOS = os.path.join(RAIZ, "Data", REGION, "urbano")     # CSV versionados
DIR_SALIDA_MAPAS = os.path.join(RAIZ, "Results", REGION, "urbano")  # PNG/HTML

CSV_CIUDADES = os.path.join(DIR_SALIDA_DATOS, "ciudades_tamaulipas.csv")
CSV_NODOS_CIUDADES = os.path.join(DIR_SALIDA_DATOS, "nodos_ciudades.csv")
CSV_RESUMEN = os.path.join(DIR_SALIDA_DATOS, "resumen_cobertura.csv")
GPKG_MANCHAS = os.path.join(DIR_CACHE, "manchas_urbanas_28.gpkg")   # geometrías, no versionadas


# --------------------------------------------------------------------------- #
# Series climáticas por ciudad (urbano/clima/)
# --------------------------------------------------------------------------- #
DIR_CLIMA = os.path.join(DIR_SALIDA_DATOS, "clima")


def csv_clima_diario(ambito: str = "ciudades") -> str:
    """Resumen diario del ámbito. Cada ámbito tiene su propio archivo."""
    return os.path.join(DIR_CLIMA, f"diario_{ambito}.csv")


def csv_clima_horario(ambito: str = "ciudades") -> str:
    return os.path.join(DIR_CLIMA, f"horario_{ambito}.csv")


def parquet_clima_horario(ambito: str = "ciudades") -> str:
    return os.path.join(DIR_CLIMA, f"horario_{ambito}.parquet")


CSV_CLIMA_DIARIO = csv_clima_diario()
CSV_CLIMA_HORARIO = csv_clima_horario()
# El horario son ~527 000 filas: por omisión va a parquet (que `.gitignore` ya
# excluye bajo Data/**/*.parquet) y el CSV versionado es el resumen diario.
PARQUET_CLIMA_HORARIO = parquet_clima_horario()

ANIOS_CLIMA = (2020, 2021, 2022, 2023, 2024)
TOP_CIUDADES = 12          # las 12 manchas urbanas de mayor área


def ruta_clima(base: str, ponderar: bool) -> str:
    """
    Ruta de salida del clima, con sufijo `_simple` en el promedio sin ponderar.

    Los dos modos escriben archivos DISTINTOS a propósito: si compartieran
    nombre, correr el pipeline en el otro modo sobrescribiría el anterior en
    silencio y nadie sabría cuál de los dos está leyendo.
    """
    if ponderar:
        return base
    raiz, ext = os.path.splitext(base)
    return f"{raiz}_simple{ext}"
