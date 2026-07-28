"""
exp07_adveccion — features ESPACIALES de advección sobre el bloque 12×12 (144 nodos).

Es el lever físico para las RAMPAS: usa el kt de los nodos VECINOS en τ-1 y el vector
viento para estimar hacia dónde y con qué signo cambiará el kt (ecuación de advección
∂kt/∂t ≈ -(u·∂kt/∂x + v·∂kt/∂y)). Añade al mejor feature-set (exp06:
base+nocturno+viento+cielo) el bloque `adveccion`.

Comparar contra exp06 (mismos 144 nodos, sin advección) AÍSLA el efecto espacial;
mirar especialmente el régimen de rampa fuerte, donde se espera el salto.
"""
from forecasting.experiments.base import ExperimentoConfig
from forecasting.experiments.exp05_multinodo_victoria import NODOS_12x12

CONFIGS = [
    ExperimentoConfig(
        exp_id="exp07_adveccion",
        version="v1",
        descripcion="XGBoost pooled 144 nodos (Cd. Victoria) con base+nocturno+viento+"
                    "cielo+adveccion. Features espaciales: kt de vecinos, gradientes y "
                    "término de advección -(u·gx+v·gy) para predecir rampas.",
        nodos=NODOS_12x12,
        bloque_id="victoria12x12",
        bloques=("base", "nocturno", "viento", "cielo", "adveccion"),
    ),
    ExperimentoConfig(
        exp_id="exp07_adveccion",
        version="v2",
        descripcion="Como v1 pero con `cloud_type` tratada correctamente: bloque `nubes` "
                    "(opacity/target encoding ajustado en train + fracción nublada) y sin "
                    "el promedio crudo de cloud_type en nocturno. Mide el efecto de la "
                    "codificación de la nube.",
        nodos=NODOS_12x12,
        bloque_id="victoria12x12",
        bloques=("base", "nocturno", "viento", "cielo", "nubes", "adveccion"),
    ),
    ExperimentoConfig(
        exp_id="exp07_adveccion",
        version="v3",
        descripcion="Advección REFINADA sobre v2: bloque `adveccion_upwind` (muestreo "
                    "upwind semi-Lagrangiano kt_upwind con lag advectivo distancia/"
                    "velocidad, vecindario radio 2, y cloud_type espacial de vecinos).",
        nodos=NODOS_12x12,
        bloque_id="victoria12x12",
        bloques=("base", "nocturno", "viento", "cielo", "nubes",
                 "adveccion", "adveccion_upwind"),
    ),
    ExperimentoConfig(
        exp_id="exp07_adveccion",
        version="v4",
        descripcion="Como v3 pero con vecindario radio 3 (7×7, ~26 km) además del radio "
                    "2, vía `adveccion_upwind_r23`. Mide si un vecindario más amplio "
                    "aporta sobre r2 o ya satura.",
        nodos=NODOS_12x12,
        bloque_id="victoria12x12",
        bloques=("base", "nocturno", "viento", "cielo", "nubes",
                 "adveccion", "adveccion_upwind_r23"),
    ),
]
