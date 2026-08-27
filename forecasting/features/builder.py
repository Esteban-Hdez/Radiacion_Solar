"""
Composición de feature-sets a partir de BLOQUES. Cada bloque es una función
`(df) -> DataFrame` de columnas; el builder concatena META + los bloques pedidos.

Así un experimento declara qué bloques usa (p.ej. `("base",)` para fase 3, o
`("base", "volatilidad", "nocturno")` para el experimento 1) y el feature-set queda
identificado y reproducible por esa lista de bloques.
"""
from __future__ import annotations
from functools import partial
import pandas as pd

from forecasting.data.loaders import serie_contigua_nodo
from forecasting.features.base import construir_meta, bloque_base, META_COLS
from forecasting.features.volatilidad import bloque_volatilidad
from forecasting.features.nocturno import bloque_nocturno
from forecasting.features.viento import bloque_viento
from forecasting.features.cielo import bloque_cielo
from forecasting.features.adveccion import agregar_adveccion, agregar_adveccion_upwind
from forecasting.features import nubes as _nubes

# Bloques POR NODO (nombre -> función `(df_1nodo) -> DataFrame`).
BLOQUES = {
    "base": bloque_base,
    "volatilidad": bloque_volatilidad,
    "nocturno": bloque_nocturno,
    "viento": bloque_viento,
    "cielo": bloque_cielo,
}

# Bloques ESPACIALES (multi-nodo): se aplican sobre la matriz ya concatenada, no por
# nodo. Requieren varios nodos (y `viento` para la advección).
BLOQUES_ESPACIALES = {
    "adveccion": agregar_adveccion,
    "adveccion_upwind": agregar_adveccion_upwind,                       # r2 (v3)
    "adveccion_upwind_r23": partial(agregar_adveccion_upwind, radios=(2, 3)),  # r2+r3 (v4)
}


def construir(df: pd.DataFrame, bloques: tuple[str, ...] = ("base",),
              opacidad_nubes: dict | None = None) -> pd.DataFrame:
    """DataFrame indexado por τ con META + las features de los `bloques` POR NODO.

    `df`: serie horaria contigua de un nodo (salida de `cargar_serie_nodo`).
    `opacidad_nubes`: encoding de `cloud_type` ya ajustado en train (para el bloque
    `nubes`); si es None y se pide `nubes`, se ajusta desde este df (single-node).
    Columnas duplicadas entre bloques se conservan una sola vez. Los bloques ESPACIALES
    (p.ej. `adveccion`) no se aplican aquí: son multi-nodo (ver `construir_bloque`).
    """
    partes = [construir_meta(df)]
    opac = None
    for nombre in bloques:
        if nombre in BLOQUES_ESPACIALES:
            raise ValueError(f"Bloque {nombre!r} es ESPACIAL (multi-nodo): usa "
                             "construir_bloque, no construir (single-node).")
        if nombre == "nubes":
            opac = opacidad_nubes if opacidad_nubes is not None else _nubes.ajustar_opacidad(df)
            partes.append(_nubes.bloque_nubes(df, opac))
            continue
        if nombre not in BLOQUES:
            raise ValueError(f"Bloque desconocido: {nombre!r}. Opciones: "
                             f"{list(BLOQUES) + ['nubes']}")
        partes.append(BLOQUES[nombre](df))
    feat = pd.concat(partes, axis=1)
    feat = feat.loc[:, ~feat.columns.duplicated()]
    if opac is not None:
        feat.attrs["opacidad_cloud"] = opac
    return feat


def construir_bloque(df_bloque: pd.DataFrame,
                     bloques: tuple[str, ...] = ("base",),
                     float32: bool = False) -> pd.DataFrame:
    """Features MULTI-NODO: construye por nodo (para que los lags no crucen nodos) y
    concatena. `df_bloque`: salida de `loaders.cargar_bloque` (columnas datetime +
    nodo_id + variables). El resultado lleva `nodo_id` como columna META y conserva el
    índice datetime (con duplicados entre nodos: cada nodo aporta su misma hora).

    `float32`: baja las features a float32 **por nodo, antes de concatenar**. Tiene
    que ser aquí y no al final: el pico de memoria está en la concatenación y en los
    bloques espaciales, así que downcastear el resultado ya no ahorraría nada.
    """
    por_nodo = tuple(b for b in bloques if b not in BLOQUES_ESPACIALES)
    espaciales = tuple(b for b in bloques if b in BLOQUES_ESPACIALES)

    # Encoding de nubes GLOBAL (ajustado en train sobre todos los nodos) -> se pasa a
    # cada nodo para que el score sea consistente y robusto (tipos raros con más datos).
    opac = _nubes.ajustar_opacidad_largo(df_bloque) if "nubes" in por_nodo else None

    partes = []
    for nodo, g in df_bloque.groupby("nodo_id", sort=True):
        d = serie_contigua_nodo(g)
        feat = construir(d, por_nodo, opacidad_nubes=opac)
        feat["nodo_id"] = nodo
        partes.append(a_float32(feat) if float32 else feat)
    feat = pd.concat(partes)

    # Bloques espaciales (advección): sobre la matriz multi-nodo ya concatenada.
    for nombre in espaciales:
        feat = BLOQUES_ESPACIALES[nombre](feat)
    if float32:
        feat = a_float32(feat)         # las features espaciales nacen en float64
    if opac is not None:
        feat.attrs["opacidad_cloud"] = opac
    return feat


def columnas_features(feat: pd.DataFrame) -> list[str]:
    """Columnas que SÍ entran al modelo (excluye las META)."""
    return [c for c in feat.columns if c not in META_COLS]


def a_float32(feat: pd.DataFrame) -> pd.DataFrame:
    """Baja las FEATURES float64 a float32 (in-place sobre las columnas no-META).

    Es lossless de cara al modelo: XGBoost convierte internamente a float32 de todos
    modos, así que el float64 solo estaba costando memoria. Las columnas META se
    dejan intactas (`kt`, `clearsky_ghi_target`, `ghi_true`… se usan para reconstruir
    el GHI y calcular métricas, donde sí queremos la precisión doble).

    Ahorra ~39 % del dataset (458 -> 278 bytes/fila en el feature-set de exp07 v4),
    que es lo que hace viable la región Centro con halo. Ver `docs/fase12_regiones.md`.
    """
    cols = [c for c in columnas_features(feat) if feat[c].dtype == "float64"]
    for c in cols:
        feat[c] = feat[c].astype("float32")
    return feat
