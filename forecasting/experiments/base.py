"""
Runner de experimentos: `ExperimentoConfig` (qué correr) + `Experimento` (cómo).

Diseño (arquitectura limpia):
- La CONFIG es un dataclass serializable: describe por completo el experimento
  (features + modelo + partición). Es la unidad reproducible.
- El RUNNER solo orquesta piezas ya existentes y testeadas del paquete
  (`features`, `models.xgb`, `eval.comparar`, `eval.regimen`). No mete lógica nueva
  de modelado: así es fácil de mantener y testear.
- Los ARTEFACTOS (config, modelo, métricas, predicciones, resumen) van a una carpeta
  por experimento/versión; el DATASET de features se cachea por feature-set.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field, asdict

import pandas as pd

from forecasting import config as C
from forecasting import features as F
from forecasting.data.loaders import cargar_serie_nodo, cargar_bloque
from forecasting.eval import comparar as CMP
from forecasting.eval import cuantil as Q
from forecasting.eval import metrics as M
from forecasting.eval import persistence as P
from forecasting.eval import regimen as REG
from forecasting.models import xgb as MX
from forecasting.models import xgb_cuantilico as QX


@dataclass
class ExperimentoConfig:
    """Descripción reproducible de un experimento."""
    exp_id: str                                  # p.ej. 'exp03_xgb_volatilidad'
    version: str                                 # p.ej. 'v1'
    descripcion: str
    nodo_id: int = 1736                          # single-node por defecto
    nodos: tuple[int, ...] = ()                  # si no vacío -> MULTI-NODO (pooled)
    nodos_eval: tuple[int, ...] = ()             # si no vacío -> métricas SOLO sobre estos
    bloque_id: str = ""                          # nombre del bloque (dataset multi-nodo)
    bloques: tuple[str, ...] = ("base",)         # feature-sets a componer
    modelo: str = "xgboost"
    params: dict = field(default_factory=dict)   # overrides de hiperparámetros
    ponderar_ghi: bool = False
    cuantiles: tuple[float, ...] = ()            # si no vacío -> modelo CUANTÍLICO
    float32: bool = False                        # features a float32 (mitad de RAM)

    @property
    def lista_nodos(self) -> tuple[int, ...]:
        return tuple(self.nodos) if self.nodos else (self.nodo_id,)

    @property
    def multinodo(self) -> bool:
        return len(self.lista_nodos) > 1

    @property
    def lista_eval(self) -> tuple[int, ...]:
        """Nodos sobre los que se REPORTAN métricas. Por defecto, todos los de
        entrenamiento; en los experimentos por región es solo la región (los nodos
        de halo entrenan pero no se evalúan)."""
        return tuple(self.nodos_eval) if self.nodos_eval else self.lista_nodos

    @property
    def con_halo(self) -> bool:
        return bool(self.nodos_eval) and len(self.nodos_eval) < len(self.lista_nodos)

    @property
    def feature_set_id(self) -> str:
        """Identidad del dataset de features = combinación de bloques."""
        return "-".join(self.bloques)

    @property
    def id_dataset(self) -> str:
        """Identidad del nodo/bloque para nombrar el dataset cacheado."""
        if self.multinodo:
            return self.bloque_id or f"bloque{len(self.lista_nodos)}"
        return f"nodo{self.nodo_id}"

    @property
    def dir_salida(self) -> str:
        return os.path.join(C.DIR_EXPERIMENTS, self.exp_id, self.version)

    @property
    def ruta_dataset(self) -> str:
        return os.path.join(C.DIR_DATASETS, self.feature_set_id,
                            f"{self.id_dataset}.parquet")


class Experimento:
    def __init__(self, cfg: ExperimentoConfig):
        self.cfg = cfg

    # -------------------------------------------------------------- #
    # Dataset (cacheado por feature-set)
    # -------------------------------------------------------------- #
    def construir_dataset(self, forzar: bool = False) -> pd.DataFrame:
        """Construye (o carga de caché) la matriz de features del feature-set.

        Single-node lee el parquet committeado de la serie; multi-nodo lee el bloque
        de `Data/*.parquet` y construye features por nodo (sin fuga entre nodos)."""
        ruta = self.cfg.ruta_dataset
        if os.path.exists(ruta) and not forzar:
            return pd.read_parquet(ruta)
        if self.cfg.multinodo:
            bloque = cargar_bloque(list(self.cfg.lista_nodos))
            feat = F.construir_bloque(bloque, bloques=self.cfg.bloques,
                                      float32=self.cfg.float32)
            del bloque                     # liberar cuanto antes: pesa como el dataset
        else:
            df = cargar_serie_nodo(self.cfg.nodo_id)
            feat = F.construir(df, bloques=self.cfg.bloques)
            if self.cfg.float32:
                feat = F.a_float32(feat)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        feat.to_parquet(ruta)
        # El encoding de nubes (ajustado en train) se guarda aparte: parquet no
        # preserva `attrs`. Sirve de artefacto reproducible del feature-set.
        if "opacidad_cloud" in feat.attrs:
            with open(ruta + ".opacidad.json", "w") as f:
                json.dump(feat.attrs["opacidad_cloud"], f, indent=2)
        return feat

    # -------------------------------------------------------------- #
    # Ejecución
    # -------------------------------------------------------------- #
    def run(self, forzar_dataset: bool = False) -> dict:
        cfg = self.cfg
        es_cuantil = bool(cfg.cuantiles)
        os.makedirs(cfg.dir_salida, exist_ok=True)
        feat = self.construir_dataset(forzar=forzar_dataset)
        cols = F.columnas_features(feat)

        # Entrenamiento (puntual o cuantílico) -> función de predicción homogénea.
        if es_cuantil:
            model, cols, splits, alphas = QX.entrenar_cuantilico(
                feat, cfg.cuantiles, cols=cols, params=cfg.params)
            def predecir(split):
                return QX.predecir_cuantiles(model, split, cols, alphas)
        else:
            model, cols, splits = MX.entrenar(
                feat, cols=cols, params=cfg.params, ponderar_ghi=cfg.ponderar_ghi)
            def predecir(split):
                return MX.predecir_ghi(model, split, cols)

        # Referencia de persistence: single-node vía smart_persistence (idéntica pero
        # explícita); multi-nodo vía la columna `ghi_persistence` en-frame (ref=None),
        # que es correcta por nodo y evita el reindex con índices repetidos.
        if cfg.multinodo:
            def ref_split(nombre):
                return None
        else:
            per = P.smart_persistence(cargar_serie_nodo(cfg.nodo_id))
            anios = {"val": C.ANIOS_VAL, "test": C.ANIOS_TEST}
            def ref_split(nombre):
                return per.loc[per.index.year.isin(anios[nombre]), "ghi_pred_A"]

        # --- Métricas puntuales globales (val + test) y por régimen (test) ---
        # Con halo, el modelo se ENTRENA con los nodos extra pero se EVALÚA solo
        # sobre `lista_eval`: así la población de métricas es exactamente la región.
        eval_ids = set(cfg.lista_eval) if cfg.con_halo else None

        globales, pred_test = [], None
        for nombre in ["val", "test"]:
            pred = predecir(splits[nombre])
            if eval_ids is not None:
                pred = pred[pred["nodo_id"].isin(eval_ids)]
            ref = ref_split(nombre)
            globales.append(CMP.comparar(pred, ref, nombre="modelo").assign(split=nombre))
            if nombre == "test":
                pred_test, ref_test = pred, ref
        tab_global = pd.concat(globales, ignore_index=True)
        regimen = REG.metricas_por_regimen(pred_test, ref_test)

        # --- Skill por nodo (multi-nodo): cómo rinde el modelo pooled en cada nodo ---
        por_nodo = self._skill_por_nodo(pred_test) if cfg.multinodo else None

        # --- Métricas de intervalo (solo cuantílico) ---
        intervalo = None
        if es_cuantil:
            intervalo = {"global": Q.metricas_intervalo(pred_test),
                         "regimen": Q.metricas_intervalo_por_regimen(pred_test)}

        try:
            importancias = (pd.Series(model.feature_importances_, index=cols)
                            .sort_values(ascending=False))
        except Exception:                       # multi-cuantil puede no exponerlas
            importancias = pd.Series(dtype=float)

        self._guardar(model, tab_global, regimen, importancias, pred_test, ref_test,
                      n_features=len(cols), best_iter=int(model.best_iteration),
                      intervalo=intervalo, por_nodo=por_nodo)

        return {"config": cfg, "metrics_global": tab_global, "regimen": regimen,
                "intervalo": intervalo, "por_nodo": por_nodo,
                "importancias": importancias, "model": model}

    @staticmethod
    def _skill_por_nodo(pred_test: pd.DataFrame) -> pd.DataFrame:
        """RMSE del modelo y de persistence + skill, por nodo (modelo pooled)."""
        filas = []
        for nodo, g in pred_test.groupby("nodo_id"):
            r_mod = M.rmse(g["ghi_true"], g["ghi_pred"])
            r_ref = M.rmse(g["ghi_true"], g["ghi_persistence"])
            filas.append({"nodo_id": int(nodo), "n": len(g),
                          "RMSE_modelo": r_mod, "RMSE_persistence": r_ref,
                          "R2_modelo": M.r2(g["ghi_true"], g["ghi_pred"]),
                          "skill": M.skill(r_mod, r_ref)})
        return pd.DataFrame(filas).sort_values("nodo_id").reset_index(drop=True)

    # -------------------------------------------------------------- #
    # Persistencia de artefactos
    # -------------------------------------------------------------- #
    def _guardar(self, model, tab_global, regimen, importancias, pred_test, ref_test,
                 n_features, best_iter, intervalo=None, por_nodo=None):
        d = self.cfg.dir_salida
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump({**asdict(self.cfg),
                       "feature_set_id": self.cfg.feature_set_id,
                       "id_dataset": self.cfg.id_dataset, "n_nodos": len(self.cfg.lista_nodos),
                       "n_nodos_eval": len(self.cfg.lista_eval),
                       "n_features": n_features, "best_iteration": best_iter}, f,
                      indent=2, ensure_ascii=False)
        model.save_model(os.path.join(d, "model.json"))
        tab_global.to_csv(os.path.join(d, "metrics_global.csv"), index=False)
        regimen["nubosidad"].to_csv(os.path.join(d, "metrics_regimen_nubosidad.csv"), index=False)
        regimen["rampa"].to_csv(os.path.join(d, "metrics_regimen_rampa.csv"), index=False)
        importancias.rename("gain").to_csv(os.path.join(d, "feature_importance.csv"))
        if intervalo is not None:
            intervalo["global"].to_csv(os.path.join(d, "metrics_intervalo.csv"), index=False)
            intervalo["regimen"].to_csv(os.path.join(d, "metrics_intervalo_regimen.csv"), index=False)
        if por_nodo is not None:
            por_nodo.to_csv(os.path.join(d, "metrics_por_nodo.csv"), index=False)
        # Copia el encoding de nubes (si el feature-set lo usa) al experimento.
        ruta_opac = self.cfg.ruta_dataset + ".opacidad.json"
        if os.path.exists(ruta_opac):
            with open(ruta_opac) as fi, open(os.path.join(d, "opacidad_cloud.json"), "w") as fo:
                fo.write(fi.read())
        pred = pred_test.copy()
        if ref_test is not None:                # single-node: persistence explícita
            pred["ghi_persistence"] = ref_test.reindex(pred.index)
        pred.to_parquet(os.path.join(d, "predictions_test.parquet"))
        self._resumen_md(tab_global, regimen, importancias, n_features, best_iter,
                         intervalo, por_nodo)

    def _resumen_md(self, tab_global, regimen, importancias, n_features, best_iter,
                    intervalo=None, por_nodo=None):
        cfg = self.cfg
        g = tab_global[(tab_global.split == "test") & (tab_global.segmento == "global")].iloc[0]
        alcance = (f"{len(cfg.lista_nodos)} nodos (bloque `{cfg.id_dataset}`)"
                   if cfg.multinodo else f"nodo {cfg.nodo_id}")
        if cfg.con_halo:
            alcance = (f"{len(cfg.lista_eval)} nodos evaluados + "
                       f"{len(cfg.lista_nodos) - len(cfg.lista_eval)} de halo "
                       f"(entrenan, no puntúan) — bloque `{cfg.id_dataset}`")
        lineas = [
            f"# {cfg.exp_id} — {cfg.version}", "",
            cfg.descripcion, "",
            f"- Alcance: {alcance} | feature-set: `{cfg.feature_set_id}` "
            f"({n_features} features) | best_iteration: {best_iter}",
            f"- Bloques: {list(cfg.bloques)} | modelo: {cfg.modelo} "
            f"| cuantiles: {list(cfg.cuantiles) or '—'}", "",
            f"**Test global (P50 si cuantílico):** RMSE {g.RMSE_modelo:.2f} vs "
            f"persistence {g.RMSE_persistence:.2f} W/m² · skill {g.skill:.4f} "
            f"· R² {g.R2_modelo:.3f}", "",
            "## Métricas globales (val + test)", "",
            tab_global.round(3).to_markdown(index=False), "",
            "## Por régimen de nubosidad (test)", "",
            regimen["nubosidad"].round(3).to_markdown(index=False), "",
            "## Por régimen de rampa (test)", "",
            regimen["rampa"].round(3).to_markdown(index=False), "",
        ]
        if intervalo is not None:
            lineas += [
                "## Intervalo de predicción (test)", "",
                intervalo["global"].round(3).to_markdown(index=False), "",
                "### Cobertura y anchura por régimen de nubosidad", "",
                intervalo["regimen"].round(3).to_markdown(index=False), "",
            ]
        if por_nodo is not None:
            resumen_nodo = por_nodo["skill"].describe()[["mean", "min", "max"]]
            lineas += [
                "## Skill por nodo (modelo pooled, test)", "",
                f"skill medio {resumen_nodo['mean']:.4f} · "
                f"min {resumen_nodo['min']:.4f} · max {resumen_nodo['max']:.4f} "
                f"({len(por_nodo)} nodos)", "",
                por_nodo.round(3).to_markdown(index=False), "",
            ]
        if not importancias.empty:
            lineas += ["## Top 15 importancias (gain)", "",
                       importancias.head(15).round(4).to_markdown(), ""]
        with open(os.path.join(cfg.dir_salida, "summary.md"), "w") as f:
            f.write("\n".join(lineas))
