"""Tests de los bloques por región + halo (fase 12)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forecasting.data import regiones as R
from forecasting.experiments.base import ExperimentoConfig
from forecasting.features.builder import a_float32
from forecasting.features.base import META_COLS


def test_asignacion_cubre_todos_los_nodos_una_sola_vez():
    from forecasting.data.loaders import cargar_metadata
    tabla = R.cargar_asignacion()
    meta = cargar_metadata()
    assert len(tabla) == len(meta)
    assert tabla.nodo_id.is_unique
    assert set(tabla.nodo_id) == set(meta.nodo_id)


def test_las_seis_regiones_particionan_el_estado():
    """Las regiones son disjuntas y su unión es el estado entero."""
    conjuntos = [set(R.nodos_region(r)) for r in R.REGIONES]
    union = set().union(*conjuntos)
    assert len(union) == len(R.cargar_asignacion())
    assert sum(len(c) for c in conjuntos) == len(union)   # disjuntas


def test_victoria_cae_en_la_region_centro():
    """El nodo pivote histórico (1736, Ciudad Victoria) está en Centro."""
    assert 1736 in R.nodos_region(R.REGION_VICTORIA)
    assert R.REGION_VICTORIA == "Centro"


def test_halo_contiene_a_la_region_y_la_agranda():
    propios = R.nodos_region("Mante")
    con = R.con_halo(propios, radio=3)
    assert set(propios) <= set(con)
    assert len(con) > len(propios)
    assert R.con_halo(propios, radio=0) == tuple(sorted(propios))


def test_halo_crece_monotonamente_con_el_radio():
    propios = R.nodos_region("Altiplano")
    tam = [len(R.con_halo(propios, radio=r)) for r in (0, 1, 2, 3)]
    assert tam == sorted(tam)
    assert tam[0] == len(propios)


def test_halo_solo_agrega_nodos_cercanos():
    """Ningún nodo del halo está a más de `radio` celdas de la región."""
    from forecasting.data.loaders import cargar_metadata
    radio = 2
    propios = R.nodos_region("Mante")
    con = R.con_halo(propios, radio=radio)
    meta = cargar_metadata().set_index("nodo_id")
    p = meta.loc[list(propios), ["latitude", "longitude"]].to_numpy()
    for n in set(con) - set(propios):
        q = meta.loc[n, ["latitude", "longitude"]].to_numpy(dtype=float)
        celdas = np.abs(p - q) / R.PASO_MALLA
        # Chebyshev: la distancia es el máximo de las dos componentes.
        assert celdas.max(axis=1).min() <= radio + 1e-6


def test_bloque_region_separa_entrenamiento_de_evaluacion():
    entrena, evalua = R.bloque_region("Sur", radio_halo=3)
    assert set(evalua) == set(R.nodos_region("Sur"))
    assert set(evalua) < set(entrena)          # estrictamente contenido


def test_config_con_halo_evalua_solo_la_region():
    cfg = ExperimentoConfig(exp_id="x", version="v1", descripcion="",
                            nodos=(1, 2, 3, 4), nodos_eval=(1, 2))
    assert cfg.con_halo
    assert cfg.lista_eval == (1, 2)
    assert cfg.lista_nodos == (1, 2, 3, 4)


def test_config_sin_halo_evalua_todo():
    cfg = ExperimentoConfig(exp_id="x", version="v1", descripcion="", nodos=(1, 2, 3))
    assert not cfg.con_halo
    assert cfg.lista_eval == (1, 2, 3)


def test_float32_no_toca_las_meta_y_baja_las_features():
    feat = pd.DataFrame({
        "kt": np.array([0.5, 0.6]),                    # META -> se queda en float64
        "clearsky_ghi_target": np.array([800.0, 810.0]),
        "op": [True, True], "ghi_true": [400.0, 480.0],
        "fill_flag": [0.0, 0.0], "nodo_id": [1, 1],
        "kt_lag1": np.array([0.4, 0.5]),               # feature -> float32
        "hour": np.array([10, 11], dtype="int16"),     # no float: intacta
    })
    out = a_float32(feat.copy())
    for c in META_COLS:
        if c in out and feat[c].dtype == "float64":
            assert out[c].dtype == "float64", c
    assert out["kt_lag1"].dtype == "float32"
    assert out["hour"].dtype == "int16"


def test_float32_preserva_los_valores_dentro_de_la_tolerancia():
    feat = pd.DataFrame({"kt": [0.5], "op": [True], "clearsky_ghi_target": [800.0],
                         "ghi_true": [400.0], "fill_flag": [0.0], "nodo_id": [1],
                         "kt_vecinos_mean_r2": [0.123456789]})
    out = a_float32(feat.copy())
    assert out["kt_vecinos_mean_r2"].iloc[0] == pytest.approx(0.123456789, abs=1e-7)


def test_resumen_regiones_cuadra_con_el_total_del_estado():
    tab = R.resumen_regiones(radio_halo=3)
    assert len(tab) == 6
    assert tab.nodos.sum() == len(R.cargar_asignacion())
    assert (tab.total > tab.nodos).all()       # todas ganan halo
