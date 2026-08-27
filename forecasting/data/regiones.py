"""
Bloques de nodos por REGIÓN administrativa de Tamaulipas (+ halo).

Motivación: el estado entero (4384 nodos) no cabe en RAM —el pico medido escala a
~0.060 GB/nodo, o sea ~263 GB—, así que hay que entrenar por bloques. Las 6 regiones
oficiales del estado dan una partición con significado y de tamaño manejable.

Pero cortar por una frontera administrativa ROMPE los vecindarios espaciales, que
son la segunda feature más importante del modelo (`kt_vecinos_mean_r2`). Sin halo,
el 42 % de los nodos del estado pierde su vecindario r2 completo. Por eso:

    entrenar sobre  región + HALO  ·  evaluar solo sobre  la región

El halo son los nodos de fuera de la región a <= `radio` celdas de ella: aportan
contexto espacial a los nodos del borde pero no entran en las métricas, así que la
población de evaluación sigue siendo exactamente la región.

La asignación nodo->región vive en `Data/Tamaulipas/regiones_tamaulipas.csv`, que
genera `Utils/asignar_regiones.py` (polígonos OSM/INEGI). Ver `docs/fase12_regiones.md`.
"""
from __future__ import annotations
import functools
import os

import numpy as np
import pandas as pd

from forecasting import config as C
from forecasting.data.loaders import cargar_metadata

RUTA_REGIONES = os.path.join(C.RAIZ, "Data", "Tamaulipas", "regiones_tamaulipas.csv")

# Las 6 regiones oficiales, de mayor a menor número de nodos.
REGIONES = ("Centro", "Fronteriza", "Valle de San Fernando", "Sur", "Altiplano", "Mante")

# Nodo pivote histórico del proyecto (Ciudad Victoria) -> región Centro.
REGION_VICTORIA = "Centro"

PASO_MALLA = 0.04  # grados; la rejilla real de NSRDB v4


@functools.lru_cache(maxsize=1)
def cargar_asignacion() -> pd.DataFrame:
    """Tabla nodo_id -> region (4384 filas)."""
    if not os.path.exists(RUTA_REGIONES):
        raise FileNotFoundError(
            f"No existe {RUTA_REGIONES}. Genéralo con: "
            "conda run -n rs python Utils/asignar_regiones.py")
    return pd.read_csv(RUTA_REGIONES)


def nodos_region(region: str) -> tuple[int, ...]:
    """Ids de los nodos de una región, ordenados."""
    tabla = cargar_asignacion()
    if region not in set(tabla.region):
        raise KeyError(f"Región {region!r} desconocida. Opciones: {sorted(set(tabla.region))}")
    return tuple(sorted(tabla.loc[tabla.region == region, "nodo_id"].astype(int)))


def _malla(meta: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Índices (ilat, ilon) de cada nodo en la rejilla y el array id-por-celda."""
    ilat = ((meta.latitude - meta.latitude.min()) / PASO_MALLA).round().astype(int)
    ilon = ((meta.longitude - meta.longitude.min()) / PASO_MALLA).round().astype(int)
    celdas = np.full((ilat.max() + 1, ilon.max() + 1), -1, dtype=int)
    celdas[ilat.to_numpy(), ilon.to_numpy()] = meta.nodo_id.to_numpy()
    return ilat.to_numpy(), ilon.to_numpy(), celdas


def con_halo(nodos: tuple[int, ...], radio: int = 3) -> tuple[int, ...]:
    """`nodos` + los nodos del estado a <= `radio` celdas de ellos (vecindad de
    Chebyshev, es decir la ventana cuadrada que usan las features de advección).

    Devuelve la unión ordenada; con `radio=0` devuelve `nodos` tal cual.
    """
    if radio <= 0:
        return tuple(sorted(nodos))
    meta = cargar_metadata()
    ilat, ilon, celdas = _malla(meta)
    pos = {int(n): k for k, n in enumerate(meta.nodo_id)}

    dentro = np.zeros(celdas.shape, dtype=bool)
    faltan = [n for n in nodos if n not in pos]
    if faltan:
        raise KeyError(f"Nodos fuera de la metadata: {faltan[:5]}")
    idx = [pos[int(n)] for n in nodos]
    dentro[ilat[idx], ilon[idx]] = True

    # Dilatación de Chebyshev: `radio` pasos en las 8 direcciones.
    ancho = dentro.copy()
    for _ in range(radio):
        vecinos = np.zeros_like(ancho)
        for dlat in (-1, 0, 1):
            for dlon in (-1, 0, 1):
                vecinos |= np.roll(np.roll(ancho, dlat, axis=0), dlon, axis=1)
        ancho = vecinos
    ids = celdas[ancho & (celdas >= 0)]
    return tuple(sorted(int(i) for i in ids))


def bloque_region(region: str, radio_halo: int = 3) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(nodos_entrenamiento, nodos_evaluacion) para una región.

    `nodos_entrenamiento` = región + halo; `nodos_evaluacion` = la región a secas.
    """
    propios = nodos_region(region)
    return con_halo(propios, radio_halo), propios


def resumen_regiones(radio_halo: int = 3) -> pd.DataFrame:
    """Tamaño de cada región con y sin halo, y el coste estimado de RAM/tiempo.

    Las constantes vienen de la curva medida en esta máquina (144/300/500/1000
    nodos, R² 0.9995): pico ~0.060 GB/nodo, ~0.21 s/nodo. Ver `docs/fase12_regiones.md`.
    """
    filas = []
    for r in REGIONES:
        propios = nodos_region(r)
        total = con_halo(propios, radio_halo)
        filas.append({"region": r, "nodos": len(propios),
                      "halo": len(total) - len(propios), "total": len(total),
                      "RAM_GB_est": round(len(total) * 0.0598 + 0.8),
                      "minutos_est": round(len(total) * 0.2095 / 60, 1)})
    return pd.DataFrame(filas)
