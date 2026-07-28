"""
Framework de experimentos VERSIONADOS del pronóstico.

Cada experimento se declara como `ExperimentoConfig` (id + versión + bloques de
features + hiperparámetros) y se ejecuta con `Experimento(cfg).run()`, que escribe
todos los artefactos en una carpeta propia:

    Results/<region>/forecast/experiments/<exp_id>/<version>/

y cachea el dataset de features (por feature-set) en:

    Results/<region>/forecast/experiments/datasets/<feature_set_id>/

Así los experimentos no se mezclan y cualquier versión se reproduce corriendo su
config. Ver `base.py` (runner), `registro.py` (catálogo) y `exp*.py`.
"""
from forecasting.experiments.base import ExperimentoConfig, Experimento
from forecasting.experiments.registro import REGISTRO, obtener, listar

__all__ = ["ExperimentoConfig", "Experimento", "REGISTRO", "obtener", "listar"]
