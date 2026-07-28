"""
exp05_multinodo_victoria — prueba de concepto MULTI-NODO (pooled).

Entrena UN solo XGBoost con un bloque de 25 nodos (malla 5×5) centrado en Cd. Victoria
(nodo 1736). El nodo se describe al modelo con lat/lon/msnm (nunca con el id), así que
un único modelo generaliza a todo el bloque. Objetivo de la POC:
- ver si agrupar nodos (más datos + más diversidad de regímenes, incluye sierra con
  msnm 230-1482 m) ayuda vs el single-node;
- medir capacidad de la laptop (tiempos/memoria);
- dejar el andamiaje listo para escalar a más nodos y features espaciales (exp06).

Feature-set = base + nocturno (el retenido en exp03). Evaluación pooled + skill por
nodo. Las features se construyen POR NODO (los lags no cruzan nodos).
"""
from forecasting.data.loaders import nodos_cercanos
from forecasting.experiments.base import ExperimentoConfig

PIVOTE = 1736   # Cd. Victoria

# Bloque 5×5 (25 nodos) centrado en el pivote. Malla ~0.04° (~4 km).
NODOS_5x5 = (
    1628, 1629, 1630, 1631, 1632,
    1681, 1682, 1683, 1684, 1685,
    1734, 1735, 1736, 1737, 1738,
    1786, 1787, 1788, 1789, 1790,
    1832, 1833, 1834, 1835, 1836,
)
# Bloque 12×12 (144 nodos): los 144 nodos más cercanos al pivote.
NODOS_12x12 = nodos_cercanos(PIVOTE, 144)

CONFIGS = [
    ExperimentoConfig(
        exp_id="exp05_multinodo_victoria",
        version="v1",
        descripcion="XGBoost pooled sobre bloque 5×5 (25 nodos) centrado en Cd. Victoria. "
                    "Feature-set base+nocturno; el nodo se describe con lat/lon/msnm.",
        nodos=NODOS_5x5,
        bloque_id="victoria5x5",
        bloques=("base", "nocturno"),
    ),
    ExperimentoConfig(
        exp_id="exp05_multinodo_victoria",
        version="v2",
        descripcion="Igual que v1 pero bloque 12×12 (144 nodos). Mide el efecto de "
                    "ESCALAR el número de nodos con las mismas features.",
        nodos=NODOS_12x12,
        bloque_id="victoria12x12",
        bloques=("base", "nocturno"),
    ),
]
