"""
exp09 — pronóstico por REGIÓN administrativa de Tamaulipas (bloques con halo).

El estado entero no cabe en RAM (~263 GB proyectados para 4384 nodos), así que hay
que trabajar por bloques. Este experimento usa las 6 regiones oficiales del estado
como partición: tienen significado administrativo (útil para reportar a terceros) y
un tamaño manejable.

Diseño (ver `docs/fase12_regiones.md`):

- **Entrena** sobre `región + halo de 3 celdas` (~13 km), para que los nodos del
  borde conserven su vecindario espacial: sin halo, el 42 % de los nodos del estado
  pierde el vecindario r2 completo, y `kt_vecinos_mean_r2` es la 2ª feature del
  modelo.
- **Evalúa** solo sobre los nodos de la región. Así la población de métricas es
  exactamente la región y las cifras son comparables entre regiones.
- `float32=True`: sin él, Centro con halo pica en ~114 GB de los ~119 disponibles.

Feature-set idéntico al de exp07 v4 (el mejor hasta ahora, skill 0.127) para que la
única variable que cambia sea el bloque de nodos.

Una versión por región, de mayor a menor: **v1 Centro** (la de Ciudad Victoria y el
nodo pivote histórico 1736), v2 Fronteriza, v3 Valle de San Fernando, v4 Sur,
v5 Altiplano, v6 Mante.

Ojo al comparar versiones entre sí: cada una evalúa una POBLACIÓN DISTINTA de nodos,
así que sus skills no son directamente comparables (el `RMSE_persistence` de cada
región refleja lo difícil que es esa región, no lo bueno que es el modelo). Para
comparar de verdad hace falta o bien nodos comunes, o bien la matriz de transferencia
entrenando en una región y evaluando en otra.
"""
from __future__ import annotations

from forecasting.data.regiones import REGIONES, REGION_VICTORIA, bloque_region
from forecasting.experiments.base import ExperimentoConfig

# Mismo feature-set que exp07 v4.
BLOQUES = ("base", "nocturno", "viento", "cielo", "nubes", "adveccion",
           "adveccion_upwind_r23")

RADIO_HALO = 3

# Notas por región: lo que hace peculiar a cada una (va a la descripción del experimento).
_NOTAS = {
    "Centro": "la de Ciudad Victoria (nodo pivote histórico 1736) y la mayor del estado",
    "Fronteriza": ("franja del Río Bravo; la más rota de origen — el 53 % de sus "
                   "vecinos caen en Texas o el Golfo, fuera de la malla descargada"),
    "Valle de San Fernando": "llanura costera del noreste, la de menor relieve",
    "Sur": "zona conurbada de Tampico y la llanura costera del sur",
    "Altiplano": ("la única físicamente peculiar: 1539 m de media frente a 70–327 m "
                  "del resto (Sierra Madre Oriental)"),
    "Mante": ("la más pequeña y alargada; sin halo perdería el 59 % de sus "
              "vecindarios r2"),
}

_ID_BLOQUE = {
    "Centro": "region_centro", "Fronteriza": "region_fronteriza",
    "Valle de San Fernando": "region_valle_san_fernando", "Sur": "region_sur",
    "Altiplano": "region_altiplano", "Mante": "region_mante",
}


def _config(region: str, version: str) -> ExperimentoConfig:
    entrena, evalua = bloque_region(region, RADIO_HALO)
    return ExperimentoConfig(
        exp_id="exp09_regiones",
        version=version,
        descripcion=(
            f"Región **{region}** — {_NOTAS[region]}. Entrena sobre la región + halo "
            f"de {RADIO_HALO} celdas (~13 km) y evalúa solo sobre la región, para no "
            "degradar los vecindarios espaciales en el borde. Feature-set de exp07 "
            "v4; float32 para que quepa en RAM."),
        nodos=entrena,
        nodos_eval=evalua,
        bloque_id=f"{_ID_BLOQUE[region]}_halo{RADIO_HALO}",
        bloques=BLOQUES,
        float32=True,
    )


# REGIONES ya viene ordenado de mayor a menor número de nodos, y Centro es la primera.
assert REGIONES[0] == REGION_VICTORIA
CONFIGS = [_config(r, f"v{i}") for i, r in enumerate(REGIONES, start=1)]
