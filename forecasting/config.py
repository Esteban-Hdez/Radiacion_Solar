"""
Configuración central del pipeline de pronóstico de GHI horaria (Tamaulipas).

Aquí viven las DECISIONES METODOLÓGICAS del proyecto, en un solo lugar, para que
todo el pipeline (QC, features, modelos, validación) las respete sin duplicarlas:

- Target = kt = ghi / clearsky_ghi. El GHI se reconstruye como kt * clearsky_ghi.
- Solo horas OPERATIVAS: clearsky_ghi > 0 y solar_zenith_angle < ZENITH_MAX.
- Validación temporal walk-forward (sin shuffle).
- nodo_id NO se codifica one-hot: el nodo se describe con lat/lon/msnm.
- Baseline obligatorio: smart persistence kt(t+1) = kt(t).

La clave anti-fuga-temporal es la clasificación de variables por lo que se conoce
en el instante de predecir (ver GRUPOS más abajo).
"""
from __future__ import annotations
import os

# --------------------------------------------------------------------------- #
# Rutas y años
# --------------------------------------------------------------------------- #
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = "Tamaulipas"


def ruta_parquet(anio: int) -> str:
    """Parquet consolidado horario (24 h, todas las variables) de un año."""
    return os.path.join(
        RAIZ, "Data", REGION, str(anio), "Finales", "completo",
        f"dataset_tamaulipas_completo_24h_{anio}.parquet")


META_NODOS = os.path.join(RAIZ, "Data", REGION, "metadata_nodos_tamaulipas.csv")
DIR_RESULTADOS = os.path.join(RAIZ, "Results", REGION, "forecast")

# Partición temporal decidida para el arranque single-node.
ANIOS_TRAIN = [2020, 2021, 2022]
ANIOS_VAL = [2023]
ANIOS_TEST = [2024]
ANIOS_TODOS = ANIOS_TRAIN + ANIOS_VAL + ANIOS_TEST

# --------------------------------------------------------------------------- #
# Definición de horas operativas (target solo aquí; las noches nunca son target)
# --------------------------------------------------------------------------- #
ZENITH_MAX = 85.0          # grados; por encima -> noche/crepúsculo, se excluye
CLEARSKY_MIN = 0.0         # clearsky_ghi debe ser > este valor

# --------------------------------------------------------------------------- #
# Target y reconstrucción
# --------------------------------------------------------------------------- #
COL_GHI = "ghi"
COL_CLEARSKY = "clearsky_ghi"
COL_ZENITH = "solar_zenith_angle"
COL_TARGET = "kt"          # derivada: ghi / clearsky_ghi, recortada a [0, KT_MAX]
KT_MAX = 1.0               # kt se satura en 1 (no se permite superar cielo despejado)

# --------------------------------------------------------------------------- #
# Clasificación de variables por rol (CLAVE ANTI-LEAKAGE)
# --------------------------------------------------------------------------- #
# B) Deterministas / known-future: calculables para t+1 sin rezago.
DETERMINISTAS = [
    "clearsky_ghi", "clearsky_dni", "clearsky_dhi", "solar_zenith_angle",
]

# C) Estáticas por nodo (de la metadata): describen el nodo sin one-hot de id.
ESTATICAS = ["latitude", "longitude", "msnm"]

# D) Observadas: SOLO conocidas hasta t. Deben rezagarse; nunca en t+1 crudas.
OBSERVADAS_RADIACION = ["ghi", "dni", "dhi", "ghi_uv_280_400", "ghi_uv_295_385"]
OBSERVADAS_NUBES = ["cloud_type", "cloud_fill_flag", "fill_flag"]
OBSERVADAS_METEO = [
    "temperature", "dew_point", "relative_humidity", "pressure",
    "precipitable_water", "wind_speed", "wind_direction",
]
OBSERVADAS_AEROSOL = [
    "surface_albedo", "aerosol_optical_depth", "alpha", "asymmetry", "ssa", "ozone",
]
OBSERVADAS = (OBSERVADAS_RADIACION + OBSERVADAS_NUBES
              + OBSERVADAS_METEO + OBSERVADAS_AEROSOL)

# Candidatas a descartar por redundancia/leakage con el target (UV ≈ f(ghi)).
SOSPECHOSAS_REDUNDANTES = ["ghi_uv_280_400", "ghi_uv_295_385"]

# Categóricas que NO deben ir one-hot (misma filosofía que nodo_id).
# cloud_type: 13 niveles -> preferir orden por opacidad o target encoding.
CATEGORICAS_NO_ONEHOT = ["nodo_id", "cloud_type"]

# Rangos físicos plausibles para QC (None = sin límite por ese lado).
RANGOS_FISICOS = {
    "ghi": (0, 1500), "dni": (0, 1200), "dhi": (0, 1200),
    "clearsky_ghi": (0, 1500), "clearsky_dni": (0, 1200), "clearsky_dhi": (0, 1200),
    "solar_zenith_angle": (0, 180), "temperature": (-20, 55), "dew_point": (-40, 40),
    "relative_humidity": (0, 100), "pressure": (800, 1100),
    "precipitable_water": (0, 10), "wind_speed": (0, 60), "wind_direction": (0, 360),
    "surface_albedo": (0, 1), "aerosol_optical_depth": (0, 5), "ozone": (0, 1),
}

os.makedirs(DIR_RESULTADOS, exist_ok=True)
