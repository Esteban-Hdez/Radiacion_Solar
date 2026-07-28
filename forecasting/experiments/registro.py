"""
Catálogo de experimentos disponibles, con VERSIONES. Cada módulo `expNN_*.py` expone
`CONFIGS` (lista de `ExperimentoConfig`, una por versión). Aquí se aplanan a un
registro `(exp_id, version) -> config`.

    from forecasting.experiments import obtener, Experimento
    Experimento(obtener("exp03_xgb_volatilidad")).run()          # última versión
    Experimento(obtener("exp03_xgb_volatilidad", "v1")).run()    # versión concreta
"""
from __future__ import annotations

from forecasting.experiments.base import ExperimentoConfig
from forecasting.experiments.exp02_xgb_base import CONFIGS as C02
from forecasting.experiments.exp03_xgb_volatilidad import CONFIGS as C03
from forecasting.experiments.exp04_xgb_cuantilico import CONFIGS as C04
from forecasting.experiments.exp05_multinodo_victoria import CONFIGS as C05
from forecasting.experiments.exp06_viento_cielo import CONFIGS as C06
from forecasting.experiments.exp07_adveccion import CONFIGS as C07

# (exp_id, version) -> config
REGISTRO: dict[tuple[str, str], ExperimentoConfig] = {
    (c.exp_id, c.version): c for c in [*C02, *C03, *C04, *C05, *C06, *C07]
}


def _versiones(exp_id: str) -> list[str]:
    return [v for (e, v) in REGISTRO if e == exp_id]


def obtener(exp_id: str, version: str | None = None) -> ExperimentoConfig:
    """Config de un experimento. Sin `version`, devuelve la última (orden alfabético
    de versión, p.ej. v2 > v1)."""
    vers = _versiones(exp_id)
    if not vers:
        raise KeyError(f"Experimento {exp_id!r} no registrado. Opciones: {listar()}")
    version = version or sorted(vers)[-1]
    if (exp_id, version) not in REGISTRO:
        raise KeyError(f"{exp_id!r} no tiene versión {version!r}. Versiones: {sorted(vers)}")
    return REGISTRO[(exp_id, version)]


def listar() -> list[str]:
    """Lista 'exp_id:version' de todo lo registrado."""
    return [f"{e}:{v}" for (e, v) in REGISTRO]
