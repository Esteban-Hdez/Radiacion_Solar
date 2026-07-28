"""
Bloque de features de VIENTO en componentes.

La dirección del viento es CIRCULAR (0°=360°): usarla cruda parte mal a los modelos
en ese salto. Se descompone el viento (velocidad VV, dirección DV) en componentes
vectoriales continuas + seno/coseno de la dirección.

Convención meteorológica: DV es la dirección DESDE la que sopla el viento (grados
desde el norte, horario). El vector viento (hacia dónde va) es:
    u = -VV·sin(DV),   v = -VV·cos(DV)
u = componente zonal (E-O), v = componente meridional (N-S).

El viento es OBSERVADO ⇒ se rezaga (`.shift(1)`, último valor conocido en τ-1); nunca
crudo en τ. Estas componentes preparan además las features espaciales de advección
(exp06): el vector viento indica de dónde llega el tiempo.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def bloque_viento(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    if "wind_speed" not in df.columns or "wind_direction" not in df.columns:
        return out
    vv = df["wind_speed"].shift(1)
    dv = np.deg2rad(df["wind_direction"].shift(1))
    out["wind_u_lag1"] = -vv * np.sin(dv)          # componente E-O (zonal)
    out["wind_v_lag1"] = -vv * np.cos(dv)          # componente N-S (meridional)
    out["wind_dir_sin_lag1"] = np.sin(dv)          # dirección continua (sin VV)
    out["wind_dir_cos_lag1"] = np.cos(dv)
    return out
