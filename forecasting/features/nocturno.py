"""
Bloque de features de HISTORIA NOCTURNA (experimento 1).

Idea: las primeras horas operativas de la mañana son donde persistence no tiene nada
(arrastra el kt de la tarde anterior) y el XGBoost base solo ve 1 h de meteo. Pero la
meteo SÍ existe de noche (a diferencia de kt/ghi, que no son operativos): humedad,
agua precipitable, presión, nubosidad de la madrugada informan cómo arrancará el día.

Se resumen las variables OBSERVADAS con ventanas móviles largas (trailing 12 h, con
`.shift(1)` para no incluir τ) y con TENDENCIAS (valor reciente menos valor de hace
~12 h). Todo hacia atrás ⇒ sin fuga. Para una hora de mediodía la ventana de 12 h
incluye la mañana; para una hora de la mañana incluye la noche previa — que es el
caso que nos interesa.
"""
from __future__ import annotations
import pandas as pd

VENTANA_NOCHE = 12          # horas trailing (cubre la noche para las horas de la mañana)

# Variables cuya evolución nocturna informa el arranque del día.
# (cloud_type es categórica nominal: NO se promedia como código crudo; su tratamiento
#  correcto —opacidad/target encoding y fracción nublada— va en el bloque `nubes`.)
_MEDIA = ["relative_humidity", "precipitable_water"]
_MINMAX = ["temperature", "relative_humidity"]
_TENDENCIA = ["pressure", "precipitable_water", "temperature"]


def bloque_nocturno(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    w = VENTANA_NOCHE

    for c in _MEDIA:
        if c in df.columns:
            out[f"{c}_media_{w}h"] = df[c].shift(1).rolling(w, min_periods=w // 2).mean()

    for c in _MINMAX:
        if c in df.columns:
            roll = df[c].shift(1).rolling(w, min_periods=w // 2)
            out[f"{c}_min_{w}h"] = roll.min()
            out[f"{c}_max_{w}h"] = roll.max()

    # Tendencias: valor reciente (τ-1) menos el de hace ~12 h. Presión bajando /
    # agua precipitable subiendo suelen anteceder nubosidad.
    for c in _TENDENCIA:
        if c in df.columns:
            out[f"{c}_tend_{w}h"] = df[c].shift(1) - df[c].shift(1 + w)
    return out
