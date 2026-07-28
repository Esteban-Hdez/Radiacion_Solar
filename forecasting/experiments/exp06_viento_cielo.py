"""
exp06_viento_cielo — features de viento (componentes) + estado de cielo (difusa),
sobre el bloque 12×12 (144 nodos) de Cd. Victoria.

Sobre el mejor multi-nodo (exp05 v2, base+nocturno, 144 nodos) añade:
- `viento`: descompone el viento en componentes u/v + sin/cos de la dirección
  (arregla la circularidad de la dirección cruda; prepara la advección de exp07).
- `cielo`: fracción difusa `kd=dhi/ghi` (+ tendencia) y depresión del punto de rocío
  `T−Td` — precursores baratos de nubosidad, pensados para los EPISODIOS.

Comparar contra exp05 v2 (mismos 144 nodos, sin estos bloques) AÍSLA el efecto de las
features nuevas; mirar sobre todo las métricas por régimen de rampa.
"""
from forecasting.experiments.base import ExperimentoConfig
from forecasting.experiments.exp05_multinodo_victoria import NODOS_12x12

CONFIGS = [
    ExperimentoConfig(
        exp_id="exp06_viento_cielo",
        version="v1",
        descripcion="XGBoost pooled 144 nodos (Cd. Victoria) con base+nocturno+viento+"
                    "cielo. Viento en componentes u/v y precursores de nubosidad "
                    "(difusa kd, depresión punto de rocío) para mejorar rampas.",
        nodos=NODOS_12x12,
        bloque_id="victoria12x12",
        bloques=("base", "nocturno", "viento", "cielo"),
    ),
]
