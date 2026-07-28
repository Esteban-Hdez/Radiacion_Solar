"""
exp03_xgb_volatilidad — Experimento 1 del roadmap de episodios.

Hipótesis: añadir señal de régimen inestable (volatilidad/rampas) e historia nocturna
mejora los episodios nublados/variables, donde persistence y el XGBoost base fallan.

Bloques probados:
- `volatilidad`: lags largos de kt (4-6 h, 48 h), rampas (Δkt) y std/rango de kt en
  3/6 h.
- `nocturno`: agregados y tendencias de meteo en ventana trailing de 12 h (cubre la
  noche para las horas de la mañana).

Versiones:
- v1: base + volatilidad + nocturno (intento completo).
- v2: base + nocturno (tras la ablación de v1: `volatilidad` SOBREAJUSTA y empeora;
  `nocturno` es el único bloque que aporta —marginalmente— skill y mejora rampas
  fuertes). v2 es la configuración retenida.

Se evalúa mirando especialmente las métricas POR RÉGIMEN (nubosidad y rampa).
"""
from forecasting.experiments.base import ExperimentoConfig

CONFIGS = [
    ExperimentoConfig(
        exp_id="exp03_xgb_volatilidad",
        version="v1",
        descripcion="base + volatilidad + nocturno (intento completo del experimento 1).",
        bloques=("base", "volatilidad", "nocturno"),
    ),
    ExperimentoConfig(
        exp_id="exp03_xgb_volatilidad",
        version="v2",
        descripcion="base + nocturno (config retenida: volatilidad sobreajustaba; "
                    "nocturno aporta skill marginal y mejora rampas fuertes).",
        bloques=("base", "nocturno"),
    ),
]
