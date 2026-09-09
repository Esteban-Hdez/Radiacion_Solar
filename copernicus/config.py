"""
Configuración de la descarga de ERA5 (Copernicus CDS).

El objetivo es COMPARAR fuentes: los mismos puntos que ya tenemos en NSRDB
(malla de 4 km, satélite GOES + PSM v4) medidos ahora con dos reanálisis de
resolución distinta. De ahí las decisiones de abajo.

## Un solo bounding box, no 43 peticiones

Los 43 nodos están repartidos por todo Tamaulipas. Pedir cada punto por separado
multiplicaría por 43 el número de entradas en la cola del CDS, que es el cuello
de botella real —la descarga en sí es de megabytes—. Se pide un rectángulo que
los cubra a todos y luego se extrae la celda más cercana a cada nodo.

## Troceado por MES

El CDS rechaza o encola indefinidamente las peticiones grandes. Un mes por
petición es el tamaño que ya se comprobó que funciona, y además hace la descarga
reanudable: si se corta, se retoma en el mes que faltaba.

## Credenciales

Salen de `.env` (ignorado por git) con las claves `URL_ERA5` y `KEY_ERA5`.
Nunca se escriben en el código ni en los notebooks.
"""
from __future__ import annotations
import os

from dotenv import dotenv_values

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = "Tamaulipas"

# --------------------------------------------------------------------------- #
# Credenciales
# --------------------------------------------------------------------------- #
RUTA_ENV = os.path.join(RAIZ, ".env")


def credenciales() -> tuple[str, str]:
    """
    `(url, key)` del CDS, leídas de `.env`.

    Se lee con la ruta EXPLÍCITA del repo en vez de con `load_dotenv()`, que
    busca el archivo a partir del directorio de trabajo: desde un notebook o un
    script en otra carpeta no lo encontraría y devolvería `None` sin avisar.
    """
    env = {**dotenv_values(RUTA_ENV), **os.environ}
    url, key = env.get("URL_ERA5"), env.get("KEY_ERA5")
    faltan = [n for n, v in (("URL_ERA5", url), ("KEY_ERA5", key)) if not v]
    if faltan:
        raise RuntimeError(
            f"Faltan {faltan} en {RUTA_ENV} (o en el entorno). El archivo está "
            "en .gitignore; añade ahí tus credenciales del CDS.")
    return url.strip(), key.strip()

# --------------------------------------------------------------------------- #
# Dominio y periodo
# --------------------------------------------------------------------------- #
# Los 43 nodos van de 22.25 a 27.45 °N y de -99.78 a -97.50 °E. Se añade medio
# grado de margen para que ningún nodo quede en el borde del recorte y para que
# la búsqueda de celda de tierra más cercana (ERA5-Land) tenga dónde buscar.
AREA = [27.75, -100.10, 21.95, -97.20]          # N, W, S, E, como pide el CDS

ANIOS = (2020, 2021, 2022, 2023, 2024)          # los mismos que el NSRDB
MESES = tuple(range(1, 13))

# --------------------------------------------------------------------------- #
# Productos
# --------------------------------------------------------------------------- #
# `paso_acumulacion` es el dato crítico: dice cómo convertir `ssrd` (J/m²) a
# W/m². En ERA5 la acumulación es sobre la hora anterior; en ERA5-Land es desde
# las 00 UTC del día. Aplicar la regla equivocada da una irradiancia que crece
# a lo largo del día: absurda, pero no evidentemente rota.
PRODUCTOS = {
    "single": {
        "dataset": "reanalysis-era5-single-levels",
        "resolucion_deg": 0.25,
        "extra": {"product_type": ["reanalysis"]},
        "paso_acumulacion": "horario",
        "descripcion": "ERA5 single levels, ~31 km",
    },
    "land": {
        "dataset": "reanalysis-era5-land",
        "resolucion_deg": 0.1,
        "extra": {},
        "paso_acumulacion": "desde_00utc",
        "descripcion": "ERA5-Land, ~9 km (solo tierra)",
    },
}

# Variables con contraparte en NSRDB. Se omite la precipitación: NSRDB no la
# trae, así que no aporta nada a una comparación entre fuentes.
VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "surface_pressure",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_solar_radiation_downwards",
]

# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #
DIR_BASE = os.path.join(RAIZ, "Data", REGION, "era5")


def dir_crudos(producto: str) -> str:
    return os.path.join(DIR_BASE, producto, "crudos")


def dir_nc(producto: str) -> str:
    """NetCDF ya normalizados (el CDS entrega ZIP cuando hay varios flujos)."""
    return os.path.join(DIR_BASE, producto, "nc")


def dir_series(producto: str) -> str:
    return os.path.join(DIR_BASE, producto, "series")


def archivo_crudo(producto: str, anio: int, mes: int) -> str:
    return os.path.join(dir_crudos(producto), f"era5_{producto}_{anio}_{mes:02d}.nc")


# Los 43 nodos a extraer: uno por cabecera municipal (ver urbano/mapas/nodo.py).
CSV_NODOS = os.path.join(RAIZ, "Data", REGION, "urbano",
                         "nodos_interes_municipios.csv")
