"""
exp04_xgb_cuantilico — XGBoost cuantílico (P10/P50/P90).

En días nublados/variables un pronóstico puntual siempre falla (kt de alta varianza).
Este experimento predice una BANDA de incertidumbre: cuantiles de kt reconstruidos a
GHI. Objetivos:
- P50 como pronóstico puntual (debe seguir superando a persistence).
- Banda [P10,P90] que se ENSANCHE en los episodios (nublado/variable) y cubra ~80 %.

Usa el mismo feature-set retenido en exp03 (base + nocturno). Métricas de intervalo:
pinball, cobertura y anchura (global y por régimen). Ver `eval/cuantil.py`.

Nota: v1 queda infracubierto (~0.50) por el borde kt=1 en cielo despejado (el P90 suave
no alcanza el pico kt=1); la recalibración (conformal) es el siguiente paso (v2).
"""
from forecasting.experiments.base import ExperimentoConfig

CONFIGS = [
    ExperimentoConfig(
        exp_id="exp04_xgb_cuantilico",
        version="v1",
        descripcion="XGBoost cuantílico P10/P50/P90 sobre kt, feature-set base+nocturno. "
                    "P50 puntual + banda de incertidumbre; métricas de intervalo.",
        bloques=("base", "nocturno"),
        modelo="xgboost_cuantilico",
        cuantiles=(0.1, 0.5, 0.9),
    ),
]
