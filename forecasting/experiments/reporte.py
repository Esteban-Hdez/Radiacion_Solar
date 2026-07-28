"""
Carga y presentación de un experimento ya ejecutado, para los notebooks.

`ReporteExperimento` lee los artefactos de `Results/.../experiments/<id>/<version>/`
y expone las tablas (global, régimen, intervalo, importancias) y un
`VisualizadorForecast` listo, de modo que cada notebook de experimento sea fino y
consistente. Si el experimento no se ha corrido aún, `de(..., ejecutar=True)` lo
ejecuta primero.
"""
from __future__ import annotations
import json
import os

import pandas as pd

from forecasting.experiments import Experimento, obtener
from forecasting.viz import VisualizadorForecast


class ReporteExperimento:
    def __init__(self, dir_salida: str, etiqueta: str = "XGBoost"):
        self.dir = dir_salida
        self.etiqueta = etiqueta
        with open(os.path.join(dir_salida, "config.json")) as f:
            self.config = json.load(f)
        self.metrics_global = pd.read_csv(self._p("metrics_global.csv"))
        self.regimen_nubosidad = pd.read_csv(self._p("metrics_regimen_nubosidad.csv"))
        self.regimen_rampa = pd.read_csv(self._p("metrics_regimen_rampa.csv"))
        self.importancias = pd.read_csv(self._p("feature_importance.csv"), index_col=0)
        self.predicciones = pd.read_parquet(self._p("predictions_test.parquet"))
        self.intervalo = (pd.read_csv(self._p("metrics_intervalo.csv"))
                          if os.path.exists(self._p("metrics_intervalo.csv")) else None)
        self.intervalo_regimen = (pd.read_csv(self._p("metrics_intervalo_regimen.csv"))
                                  if os.path.exists(self._p("metrics_intervalo_regimen.csv"))
                                  else None)
        self.por_nodo = (pd.read_csv(self._p("metrics_por_nodo.csv"))
                         if os.path.exists(self._p("metrics_por_nodo.csv")) else None)

    def _p(self, nombre: str) -> str:
        return os.path.join(self.dir, nombre)

    @classmethod
    def de(cls, exp_id: str, version: str | None = None,
           ejecutar: bool = False) -> "ReporteExperimento":
        cfg = obtener(exp_id, version)
        if ejecutar or not os.path.exists(os.path.join(cfg.dir_salida, "config.json")):
            Experimento(cfg).run()
        return cls(cfg.dir_salida, etiqueta=exp_id)

    @property
    def es_cuantilico(self) -> bool:
        return bool(self.config.get("cuantiles"))

    @property
    def es_multinodo(self) -> bool:
        return self.por_nodo is not None

    def resumen(self) -> None:
        g = self.metrics_global
        t = g[(g.split == "test") & (g.segmento == "global")].iloc[0]
        print(f"{self.config['exp_id']} {self.config['version']} | "
              f"feature-set {self.config['feature_set_id']} "
              f"({self.config['n_features']} feats) | best_iter {self.config['best_iteration']}")
        print(f"Test global: RMSE {t.RMSE_modelo:.2f} vs persist {t.RMSE_persistence:.2f} "
              f"| skill {t.skill:.4f} | R² {t.R2_modelo:.3f}")

    def visualizador(self, nodo: int | None = None) -> VisualizadorForecast:
        """Visualizador de las predicciones de test. En multi-nodo filtra a UN nodo
        (por defecto 1736 si está, si no el primero) para que las series no mezclen
        nodos en el mismo instante."""
        pred = self.predicciones
        if "nodo_id" in pred.columns and pred["nodo_id"].nunique() > 1:
            if nodo is None:
                nodos = pred["nodo_id"].unique()
                nodo = 1736 if 1736 in nodos else int(sorted(nodos)[0])
            pred = pred[pred["nodo_id"] == nodo]
        return VisualizadorForecast.desde_predicciones_guardadas(
            pred, etiqueta_modelo=self.etiqueta)

    def plot_importancias(self, n: int = 15, ax=None):
        import matplotlib.pyplot as plt
        if ax is None:
            _, ax = plt.subplots(figsize=(8, 6))
        self.importancias["gain"].head(n)[::-1].plot.barh(ax=ax)
        ax.set_title(f"Top {n} importancias (gain) — {self.config['exp_id']}")
        return ax
