"""
Que `docs/fuentes_geograficas.md` no se quede desfasado.

Un documento de metodología con URLs y versiones caducadas es peor que no
tenerlo: se cita en la tesis y nadie vuelve a comprobarlo. Estos tests atan las
cifras del documento a lo que dice el código, así que cambiar una edición del
INEGI o una versión de paquete sin actualizar el texto rompe la suite.

    conda run -n rs pytest urbano/tests/test_documentacion.py -q
"""
from __future__ import annotations
import importlib.metadata as md
import os

import pandas as pd
import pytest

from urbano import config as C

DOC = os.path.join(C.RAIZ, "docs", "fuentes_geograficas.md")

pytestmark = pytest.mark.skipif(not os.path.exists(DOC),
                                reason="no está docs/fuentes_geograficas.md")


@pytest.fixture(scope="module")
def texto():
    return open(DOC, encoding="utf-8").read()


# --------------------------------------------------------------------------- #
# Fuentes
# --------------------------------------------------------------------------- #
def test_la_url_del_marco_geoestadistico_es_la_del_codigo(texto):
    assert C.URL_MG in texto
    assert C.ID_PRODUCTO_MG in texto
    assert C.EDICION_MG in texto


def test_la_url_del_catalogo_de_cabeceras_es_la_del_codigo(texto):
    from urbano.data import cabeceras as CAB
    assert CAB.URL_AGEEML_MUNICIPIOS in texto


def test_el_endpoint_del_nsrdb_es_el_del_codigo(texto):
    comun = open(os.path.join(C.RAIZ, "Utils", "descarga_regiones", "_comun.py"),
                 encoding="utf-8").read()
    url = comun.split('URL_BASE = "')[1].split('"')[0]
    assert url in texto


def test_los_datasets_de_era5_son_los_del_codigo(texto):
    copernicus = pytest.importorskip("copernicus.config")
    for p in copernicus.PRODUCTOS.values():
        assert p["dataset"] in texto, p["dataset"]


# --------------------------------------------------------------------------- #
# Cifras
# --------------------------------------------------------------------------- #
def test_las_capas_que_usa_el_pipeline_estan_marcadas(texto):
    """
    El documento distingue las capas que el código LEE de las que solo están
    declaradas. Si mañana se empieza a usar otra, el texto debe decirlo.
    """
    manchas = open(os.path.join(C.RAIZ, "urbano", "data", "manchas.py"),
                   encoding="utf-8").read()
    assert "C.CAPA_LOCALIDADES" in manchas and "C.CAPA_MUNICIPIOS" in manchas
    assert "`28l`** ✅" in texto and "`28mun`** ✅" in texto
    # Las declaradas pero no leídas siguen sin usarse.
    for capa in ("CAPA_LOC_RURAL_PUNTO", "CAPA_AGEB_URBANA"):
        assert f"C.{capa}" not in manchas, (
            f"{capa} ya se usa: actualiza docs/fuentes_geograficas.md")


def test_el_numero_de_nodos_y_el_paso_de_malla(texto):
    n = len(pd.read_csv(C.META_NODOS))
    assert f"{n:,}".replace(",", " ") in texto, f"nodos = {n}"
    assert str(C.PASO_MALLA) in texto


def test_las_43_cabeceras(texto):
    from urbano.data import cabeceras as CAB
    assert len(CAB.tabla()) == 43
    assert "43" in texto


def test_los_tres_crs(texto):
    for crs in (C.CRS_GEO, C.CRS_METRICO, C.CRS_MAPA):
        assert crs.split(":")[1] in texto, crs


# --------------------------------------------------------------------------- #
# Versiones
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("paquete", ["geopandas", "shapely", "pyproj", "pyogrio",
                                     "contextily", "folium"])
def test_las_versiones_documentadas_son_las_instaladas(texto, paquete):
    version = md.version(paquete)
    assert version in texto, f"{paquete} {version} no aparece en el documento"


def test_las_rutas_citadas_existen(texto):
    """Un documento que apunta a archivos que ya no están no sirve de nada."""
    import re
    rutas = set(re.findall(r"`((?:urbano|copernicus|Utils|Data|docs)/[\w./*-]+)`",
                           texto))
    faltan = [r for r in rutas
              if "*" not in r and not os.path.exists(os.path.join(C.RAIZ, r))]
    assert not faltan, f"rutas citadas que no existen: {faltan}"
