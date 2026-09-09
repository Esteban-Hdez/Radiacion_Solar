"""
Pruebas de la consulta y el mapa por NODO suelto.

El caso del nodo individual es el más fácil de romper sin que se note: los
números salen plausibles aunque el nodo sea el equivocado. Por eso lo que se
prueba aquí es sobre todo la IDENTIDAD —que el nodo del que salen los datos y el
que se rotula en el mapa sean el mismo— y no solo que el pipeline corra.

    conda run -n rs pytest urbano/tests/test_nodo.py -q
"""
from __future__ import annotations
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from urbano import config as C
from urbano.clima import consulta as Q
from urbano.data import manchas as M
from urbano.mapas import nodo as N
from urbano.nodos import asignacion as A

pytestmark = pytest.mark.skipif(
    not os.path.exists(C.CSV_NODOS_CIUDADES),
    reason="faltan los CSV de `python -m urbano.construir`")


@pytest.fixture(scope="module")
def geo():
    urb = M.manchas_urbanas()
    nodos = A.cargar_nodos()
    return urb, nodos, A.asignar(urb, nodos)


# --------------------------------------------------------------------------- #
# La identificación de los 12 nodos señalados
# --------------------------------------------------------------------------- #
def test_los_nodos_de_interes_son_uno_por_ciudad(geo):
    sel = N.nodos_interes()
    assert len(sel) == 12
    assert sel["cvegeo"].is_unique
    assert sel["nodo_id"].is_unique


def test_cada_nodo_de_interes_pertenece_a_su_ciudad(geo):
    _, _, pares = geo
    for _, r in N.nodos_interes().iterrows():
        fila = pares[(pares["nodo_id"] == r["nodo_id"])
                     & (pares["cvegeo"] == r["cvegeo"])]
        assert len(fila) == 1, f"nodo {r['nodo_id']} no asignado a {r['ciudad']}"


def test_las_coordenadas_guardadas_coinciden_con_la_malla(geo):
    meta = pd.read_csv(C.META_NODOS).set_index("nodo_id")
    for _, r in N.nodos_interes().iterrows():
        m = meta.loc[r["nodo_id"]]
        assert r["latitude"] == pytest.approx(m["latitude"])
        assert r["longitude"] == pytest.approx(m["longitude"])


def test_los_nodos_de_interes_caen_dentro_de_su_celda_de_ciudad(geo):
    """
    Se identificaron proyectando círculos dibujados a mano sobre el mapa. Esta
    prueba comprueba lo esencial de esa identificación: que el nodo esté a menos
    de media celda del área urbana que dice representar.
    """
    urb, nodos, _ = geo
    n = nodos.set_index("nodo_id")
    u = urb.set_index("cvegeo")
    for _, r in N.nodos_interes().iterrows():
        d = n.loc[r["nodo_id"], "geometry"].distance(u.loc[r["cvegeo"], "geometry"])
        assert d < 2200, f"nodo {r['nodo_id']} a {d/1000:.1f} km de {r['ciudad']}"


# --------------------------------------------------------------------------- #
# Consulta por nodo
# --------------------------------------------------------------------------- #
def test_pesos_de_un_nodo_suelto():
    w = Q.pesos_nodo(1737)
    assert len(w) == 1
    assert w["peso"].iloc[0] == 1.0
    assert w["calidad"].iloc[0] == "nodo"
    # El municipio sale de la geometría, no de la tabla de ciudades.
    assert w["municipio"].iloc[0] == "Victoria"


def test_pesos_de_varios_nodos():
    w = Q.pesos_nodo([1737, 3978])
    assert len(w) == 2
    assert set(w["nodo_id"]) == {1737, 3978}
    # Reynosa es frontera; Victoria, interior. Los husos deben salir distintos.
    from urbano.clima import agregacion as G
    husos = {int(r.nodo_id): G.tz_de_municipio(r.cve_mun) for r in w.itertuples()}
    assert husos[3978] == G.TZ_FRONTERA
    assert husos[1737] == G.TZ_INTERIOR


def test_un_nodo_inexistente_avisa():
    with pytest.raises(ValueError, match="no existen"):
        Q.pesos_nodo([999999])


def test_nodos_repetidos_avisan():
    with pytest.raises(ValueError, match="repetidos"):
        Q.pesos_nodo([1737, 1737])


def test_nodo_y_ciudad_son_excluyentes():
    with pytest.raises(ValueError, match="excluyentes"):
        Q.serie(["temperature"], nodo=1737, ciudad="victoria")


def test_ponderar_no_aplica_a_un_nodo():
    with pytest.raises(ValueError, match="no significa nada"):
        Q.serie(["temperature"], nodo=1737, ponderar=False)


def test_catalogo_de_nodos_de_una_ciudad():
    t = Q.catalogo_nodos("victoria")
    assert len(t) == 12
    assert (t["ciudad"] == "Ciudad Victoria").all()
    # Ordenado por peso descendente: el primero es el que más ciudad cubre.
    assert t["peso"].is_monotonic_decreasing
    assert 1737 in set(t["nodo_id"])


# --------------------------------------------------------------------------- #
# Integración: los datos del nodo son los del nodo
# --------------------------------------------------------------------------- #
_HAY_PARQUET = os.path.exists(os.path.join(
    C.RAIZ, "Data", C.REGION, "2024", "Finales", "completo",
    "dataset_tamaulipas_completo_24h_2024.parquet"))
integracion = pytest.mark.skipif(not _HAY_PARQUET,
                                 reason="faltan los parquet anuales")


@integracion
def test_la_serie_de_un_nodo_es_el_dato_crudo():
    """
    Con un solo nodo no hay promedio que valga: la serie de la consulta tiene
    que ser, hora por hora, exactamente la columna del parquet.
    """
    h = Q.serie(["temperature"], nodo=1737, desde="2024-06-01", hasta="2024-06-07")
    crudo = pd.read_parquet(
        os.path.join(C.RAIZ, "Data", C.REGION, "2024", "Finales", "completo",
                     "dataset_tamaulipas_completo_24h_2024.parquet"),
        columns=["nodo_id", "datetime", "temperature"],
        filters=[("nodo_id", "in", [1737])])
    crudo["datetime"] = pd.to_datetime(crudo["datetime"], utc=True)
    j = h.merge(crudo, left_on="datetime_utc", right_on="datetime",
                suffixes=("_q", "_raw"))
    assert len(j) == len(h) == 7 * 24
    np.testing.assert_allclose(j["temperature_q"], j["temperature_raw"],
                               rtol=0, atol=1e-6)


@integracion
def test_media_min_max_diarios_de_un_nodo():
    d = Q.serie(["temperature"], nodo=1737, desde="2024-06-01",
                hasta="2024-06-30", frecuencia="dia")
    assert len(d) == 30
    assert (d["n_horas"] == 24).all()
    assert (d["temperature_min"] <= d["temperature_media"]).all()
    assert (d["temperature_media"] <= d["temperature_max"]).all()


@integracion
def test_varias_variables_y_varios_nodos():
    ids = N.nodos_interes()["nodo_id"].tolist()
    d = Q.serie(["temperature", "relative_humidity", "ghi"], nodo=ids,
                desde="2024-06-01", hasta="2024-06-30", frecuencia="dia")
    assert d["ciudad"].nunique() == 12
    assert len(d) == 12 * 30
    for v in ("temperature", "relative_humidity", "ghi"):
        for s in ("media", "min", "max"):
            assert f"{v}_{s}" in d.columns


@integracion
def test_el_nodo_difiere_del_promedio_de_su_ciudad():
    """Si coincidieran, `nodo=` no estaría haciendo nada distinto."""
    n = Q.serie(["temperature"], nodo=1737, desde="2024-06-01", hasta="2024-06-30")
    c = Q.serie(["temperature"], ciudad="victoria", desde="2024-06-01",
                hasta="2024-06-30")
    assert (n["temperature"].to_numpy() != c["temperature"].to_numpy()).any()


# --------------------------------------------------------------------------- #
# Mapa
# --------------------------------------------------------------------------- #
def test_el_mapa_rotula_el_nodo_resaltado(geo, tmp_path):
    """
    El renglón de datos de la lámina tiene que describir al nodo MARCADO, no a
    una fila cualquiera de la ciudad. Es el fallo que tuvo la primera versión:
    el mapa marcaba el nodo correcto pero lo rotulaba con el id de otro.
    """
    urb, nodos, pares = geo
    capt = {}
    _sp, _cl = plt.subplots, plt.close
    plt.subplots = lambda *a, **k: capt.setdefault("r", _sp(*a, **k))
    plt.close = lambda *a, **k: None
    try:
        N.panel_nodos(ruta=str(tmp_path / "p.png"), base=False,
                      urb=urb, nodos=nodos, pares=pares)
    finally:
        plt.subplots, plt.close = _sp, _cl

    axes = np.atleast_1d(capt["r"][1]).ravel()
    sel = N.nodos_interes().set_index("cvegeo")
    orden = [c for c in A.resumen(pares, urb)["cvegeo"] if c in sel.index]
    for ax, cve in zip(axes, orden):
        textos = [t.get_text() for t in ax.texts if "nodo " in t.get_text()]
        assert textos, f"la lámina de {cve} no rotula el nodo"
        rotulado = int(textos[0].split("nodo ")[1].split(" ")[0])
        assert rotulado == int(sel.loc[cve, "nodo_id"])


def test_un_nodo_sin_ciudad_no_tiene_mapa_de_ciudad(geo):
    _, _, pares = geo
    sin_ciudad = 4383 if 4383 not in set(pares["nodo_id"]) else 0
    with pytest.raises(ValueError, match="no toca ninguna mancha"):
        N.ciudad_del_nodo(sin_ciudad, pares)


# --------------------------------------------------------------------------- #
# Los 43 nodos señalados sobre el catálogo de cabeceras
# --------------------------------------------------------------------------- #
def test_hay_un_nodo_por_cada_cabecera(geo):
    sel = N.nodos_interes_municipios()
    assert len(sel) == 43
    assert sel["cve_mun"].is_unique
    assert sel["cvegeo"].is_unique


def test_cada_nodo_de_los_43_pertenece_a_su_cabecera(geo):
    urb, _, pares = geo
    cabeceras = set(urb.loc[urb["es_cabecera"], "cvegeo"])
    for _, r in N.nodos_interes_municipios().iterrows():
        assert r["cvegeo"] in cabeceras, f"{r['ciudad']} no es cabecera"
        fila = pares[(pares["nodo_id"] == r["nodo_id"])
                     & (pares["cvegeo"] == r["cvegeo"])]
        assert len(fila) == 1, f"nodo {r['nodo_id']} no asignado a {r['ciudad']}"


def test_gomez_farias_apunta_a_la_cabecera_y_no_a_loma_alta(geo):
    """
    Las páginas que se marcaron a mano eran anteriores a corregir la cabecera,
    así que su círculo rojo caía sobre Loma Alta (nodo 554). El nodo bueno —el
    784, en la cabecera de verdad— vino del recorte marcado en verde.
    """
    sel = N.nodos_interes_municipios().set_index("cve_mun")
    assert sel.loc["011", "cvegeo"] == "280110036"
    assert sel.loc["011", "ciudad"] == "Gómez Farías"
    assert int(sel.loc["011", "nodo_id"]) == 784
    assert int(sel.loc["011", "nodo_id"]) != 554


def test_los_43_coinciden_con_los_12_donde_se_solapan(geo):
    """
    Dos detecciones independientes (el panel de las 12 ciudades y el catálogo de
    las 43 cabeceras) sobre imágenes distintas: donde coinciden, deben dar el
    mismo nodo. Es la mejor prueba de que el método de identificación funciona.
    """
    doce = N.nodos_interes().set_index("cvegeo")["nodo_id"]
    cuarenta = N.nodos_interes_municipios().set_index("cvegeo")["nodo_id"]
    comunes = doce.index.intersection(cuarenta.index)
    assert len(comunes) == 11, "Miramar no es cabecera; deben solaparse 11"
    pd.testing.assert_series_equal(doce[comunes].sort_index(),
                                   cuarenta[comunes].sort_index(),
                                   check_names=False)


def test_los_csv_de_nodos_llevan_la_clave_municipal():
    for t in (N.nodos_interes(), N.nodos_interes_municipios()):
        assert "cve_mun" in t.columns
        assert t["cve_mun"].astype(str).str.len().eq(3).all()


@integracion
def test_las_series_llevan_la_clave_municipal():
    h = Q.serie(["temperature"], nodo=784, desde="2024-06-01", hasta="2024-06-02")
    d = Q.serie(["temperature"], nodo=784, desde="2024-06-01", hasta="2024-06-02",
                frecuencia="dia")
    for t in (h, d):
        assert "cve_mun" in t.columns
        assert (t["cve_mun"] == "011").all()
