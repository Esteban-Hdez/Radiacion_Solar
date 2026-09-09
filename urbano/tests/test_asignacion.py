"""
Pruebas del análisis urbano.

No verifican "que el código corra": verifican las INVARIANTES de las que
dependerá el reporte de métricas por ciudad. Si alguna cae, cualquier promedio
por ciudad calculado con estos CSV queda mal.

    conda run -n rs pytest urbano/tests -q
"""
from __future__ import annotations
import os

import pandas as pd
import pytest

from urbano import config as C
from urbano.data import manchas as M
from urbano.nodos import asignacion as A

pytestmark = pytest.mark.skipif(
    not os.path.exists(C.capa(C.CAPA_LOCALIDADES)),
    reason="falta el Marco Geoestadístico en caché "
           "(corre `python -m urbano.data.descarga_mgn`)")


@pytest.fixture(scope="module")
def datos():
    urb = M.manchas_urbanas()
    nodos = A.cargar_nodos()
    pares = A.asignar(urb, nodos)
    return urb, nodos, pares, A.resumen(pares, urb)


def test_las_43_cabeceras_estan(datos):
    urb, *_ = datos
    assert urb["es_cabecera"].sum() == 43
    assert urb.loc[urb["es_cabecera"], "cve_mun"].nunique() == 43


def test_ninguna_ciudad_se_queda_sin_nodo(datos):
    urb, _, pares, _ = datos
    # La razón de ser de la cascada de métodos: con la malla de 4 km, un
    # point-in-polygon puro dejaría sin nodo a la mayoría de las cabeceras.
    assert set(urb["cvegeo"]) == set(pares["cvegeo"])


def test_los_pesos_de_cada_ciudad_suman_uno(datos):
    *_, pares, _ = datos
    suma = pares.groupby("cvegeo")["peso"].sum()
    assert suma.between(1 - 1e-9, 1 + 1e-9).all()


def test_no_hay_pares_duplicados(datos):
    *_, pares, _ = datos
    assert not pares.duplicated(["nodo_id", "cvegeo"]).any()


def test_los_nodos_asignados_existen_en_la_malla(datos):
    _, nodos, pares, _ = datos
    assert set(pares["nodo_id"]) <= set(nodos["nodo_id"])


def test_la_calidad_es_coherente_con_los_nodos_dentro(datos):
    *_, res = datos
    alta = res[res["calidad"] == "alta"]
    baja = res[res["calidad"] == "baja"]
    assert (alta["n_nodos_dentro"] >= C.MIN_NODOS_ALTA).all()
    assert (baja["n_nodos_dentro"] == 0).all()


def test_las_ciudades_grandes_tienen_cobertura_alta(datos):
    *_, res = datos
    # Reynosa, Nuevo Laredo, Matamoros y Victoria son las únicas manchas que
    # superan holgadamente el área de una celda; si alguna deja de salir "alta",
    # algo se rompió en la geometría o en la malla.
    grandes = res[res["area_km2"] > 60]
    assert (grandes["calidad"] == "alta").all()


def test_la_celda_del_nodo_mide_lo_que_debe(datos):
    _, nodos, *_ = datos
    celdas = A.celdas_nodos(nodos.head(50))
    km2 = celdas.geometry.area / 1e6
    # 0.04° a ~22-27 °N: entre 17 y 19 km².
    assert km2.between(16.5, 19.5).all()


def test_los_csv_publicados_coinciden_con_el_calculo(datos):
    urb, _, pares, _ = datos
    if not os.path.exists(C.CSV_NODOS_CIUDADES):
        pytest.skip("aún no se ha corrido `python -m urbano.construir`")
    guardado = pd.read_csv(C.CSV_NODOS_CIUDADES)
    assert len(guardado) == len(pares)
    assert set(guardado["cvegeo"].astype(str).str.zfill(9)) == set(urb["cvegeo"])


def test_cada_localidad_esta_dentro_de_su_municipio(datos):
    """
    La localidad declara un `cve_mun`; su polígono debe caer ahí.

    Se comprueba por ÁREA, no por el centroide: el centroide de un polígono
    cóncavo puede caer fuera del propio polígono (le pasa a Estación Santa
    Engracia), y un test basado en él daría un falso positivo.
    """
    urb, *_ = datos
    mun = M.municipios().set_index("CVE_MUN")["geometry"]
    for _, r in urb.iterrows():
        dentro = r.geometry.intersection(mun.loc[r["cve_mun"]]).area / r.geometry.area
        assert dentro > 0.9999, (
            f"{r['ciudad']} declara el municipio {r['municipio']} pero solo el "
            f"{dentro:.1%} de su polígono cae ahí")


def test_las_manchas_no_se_solapan(datos):
    """
    Dos localidades pueden COMPARTIR frontera (Miramar y Altamira lo hacen,
    igual que Tampico y Cd. Madero) pero no traslaparse: si lo hicieran, el
    área urbana total estaría contando dos veces la zona compartida.
    """
    urb, *_ = datos
    suma = urb["area_km2"].sum()
    union = urb.geometry.union_all().area / 1e6
    assert suma == pytest.approx(union, rel=1e-9)


def test_miramar_y_altamira_son_dos_localidades_del_mismo_municipio(datos):
    """
    Caso que genera confusión al leer el panel de las 12 ciudades: aparecen dos
    láminas, "Miramar" y "Altamira", que NO son dos municipios. Son dos
    localidades urbanas del municipio de Altamira (clave 003); Altamira es la
    cabecera y Miramar —de hecho la más grande de las dos— no lo es.
    """
    urb, *_ = datos
    m = urb[urb["ciudad"] == "Miramar"].iloc[0]
    a = urb[(urb["ciudad"] == "Altamira") & urb["es_cabecera"]].iloc[0]
    assert m["cve_mun"] == a["cve_mun"] == "003"
    assert m["municipio"] == a["municipio"] == "Altamira"
    assert not m["es_cabecera"] and a["es_cabecera"]
    assert m["area_km2"] > a["area_km2"]
    # Conurbadas: comparten frontera, por eso caen en el mismo conglomerado.
    assert m["nombre_conglomerado"] == a["nombre_conglomerado"] == "Tampico"


def test_la_cabecera_sale_del_catalogo_y_no_de_la_clave_0001(datos):
    """
    La convención "la localidad 0001 es la cabecera" es FALSA en Gómez Farías
    (011): su 0001 es Loma Alta —la localidad más poblada— y la cabecera es
    Gómez Farías, la 0036. Confirmado con el Catálogo Único del INEGI (AGEEML,
    columnas CVE_CAB/NOM_CAB) y con el Gobierno de Tamaulipas.

    Es el único caso de los 43, y basta uno para que el catálogo de cabeceras
    muestre el pueblo equivocado.
    """
    from urbano.data import cabeceras as CAB

    urb, *_ = datos
    gf = urb[urb["cve_mun"] == "011"].set_index("cve_loc")
    assert gf.loc["0036", "es_cabecera"], "Gómez Farías (0036) debe ser cabecera"
    assert not gf.loc["0001", "es_cabecera"], "Loma Alta (0001) NO es cabecera"

    # Y la fuente es el catálogo, no la clave.
    mapa = CAB.mapa_cabeceras()
    assert mapa["011"] == "0036"
    for _, r in urb[urb["es_cabecera"]].iterrows():
        assert r["cve_loc"] == mapa[r["cve_mun"]]


def test_el_catalogo_de_cabeceras_cubre_los_43_municipios():
    from urbano.data import cabeceras as CAB

    t = CAB.tabla()
    assert len(t) == 43
    assert t["cve_mun"].is_unique
    assert t["cve_loc_cabecera"].notna().all()
