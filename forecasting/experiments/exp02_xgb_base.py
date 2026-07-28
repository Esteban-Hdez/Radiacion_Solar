"""
exp02_xgb_base — XGBoost con feature-set BASE (reproduce la Fase 3).

Sirve de REFERENCIA dentro del framework de experimentos: mismos 35 features y
mismos hiperparámetros por defecto. Cualquier experimento nuevo se compara contra
este (además de contra smart persistence).
"""
from forecasting.experiments.base import ExperimentoConfig

CONFIGS = [
    ExperimentoConfig(
        exp_id="exp02_xgb_base",
        version="v1",
        descripcion="XGBoost t+1 con feature-set base (lags kt 1/2/3/24 + kt_last_op "
                    "+ deterministas known-future + estáticas + observadas lag1). "
                    "Reproduce la Fase 3; referencia para el resto de experimentos.",
        bloques=("base",),
    ),
]
