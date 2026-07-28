"""
Paquete de features. API pública:

- `construir(df, bloques)` / `columnas_features(feat)`: composición versionada de
  feature-sets a partir de bloques (base, volatilidad, nocturno).
- `construir_features(df)`: atajo retro-compatible = feature-set BASE (fase 3).

Ver `builder.py` y los módulos de cada bloque.
"""
from __future__ import annotations
import pandas as pd

from forecasting.features.builder import (construir, construir_bloque,
                                          columnas_features, BLOQUES)
from forecasting.features.base import META_COLS

# Alias interno usado por código previo (fase 3).
_META = META_COLS


def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    """Feature-set BASE (retro-compatibilidad con el experimento fase 3)."""
    return construir(df, bloques=("base",))


__all__ = ["construir", "construir_bloque", "columnas_features",
           "construir_features", "BLOQUES", "META_COLS"]
