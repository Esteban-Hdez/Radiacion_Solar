"""
Pruebas de la interfaz de consulta (`urbano.clima.consulta`).

Cubren lo que un usuario puede escribir mal o entender mal: nombres ambiguos,
ámbitos que se mezclan con selecciones incompatibles, y —lo más delicado— la
matemática de reagrupar pesos, que es donde un error pasaría inadvertido porque
el resultado seguiría pareciendo razonable.

    conda run -n rs pytest urbano/tests -q
"""
from __future__ import annotations
import os

import pandas as pd
import pytest

from urbano import config as C
from urbano.clima import consulta as Q

pytestmark = pytest.mark.skipif(
    not os.path.exists(C.CSV_NODOS_CIUDADES),
    reason="faltan los CSV de `python -m urbano.construir`")


@pytest.fixture(scope="module")
def cat():
    return Q.catalogo()


# --------------------------------------------------------------------------- #
# Resolución de nombres
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref", ["280410001", "Ciudad Victoria",
                                 "ciudad victoria", "CIUDAD VICTORIA",
                                 "victoria", "Victoria"])
def test_victoria_se_resuelve_de_varias_formas(cat, ref):
    assert Q.resolver(ref, cat) == "280410001"


def test_el_municipio_desempata_un_nombre_ambiguo(cat):
    # "victoria" aparece también en "Guadalupe Victoria" (Abasolo). Como texto
    # es ambiguo; como nombre de municipio es único, y su cabecera es lo que se
    # quería. Ese desempate es el paso 3 de `resolver`.
    parciales = cat[cat["ciudad"].str.contains("Victoria")]
    assert len(parciales) > 1
    assert Q.resolver("victoria", cat) == "280410001"


def test_un_nombre_ambiguo_de_verdad_lista_los_candidatos(cat):
    with pytest.raises(ValueError, match="ambiguo"):
        Q.resolver("ciudad", cat)


def test_un_nombre_inexistente_manda_al_catalogo(cat):
    with pytest.raises(ValueError, match="catalogo"):
        Q.resolver("Guadalajara", cat)


def test_el_catalogo_tiene_las_63_localidades(cat):
    assert len(cat) == 63
    assert (cat["tipo"] == "cabecera").sum() == 43
    assert (cat["tipo"] == "otra localidad").sum() == 20


# --------------------------------------------------------------------------- #
# Ámbitos y pesos
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ambito,unidades", [
    ("cabeceras", 43), ("otras", 20), ("localidades", 63), ("global", 1)])
def test_cada_ambito_tiene_las_unidades_que_debe(ambito, unidades):
    assert Q.pesos(ambito)["cvegeo"].nunique() == unidades


def test_los_pesos_suman_uno_en_todo_ambito():
    for ambito in Q.AMBITOS:
        s = Q.pesos(ambito).groupby("cvegeo")["peso"].sum()
        assert s.between(1 - 1e-5, 1 + 1e-5).all(), ambito


def test_agrupar_reparte_por_area_urbana():
    """
    El reparto dentro de un conglomerado debe ser proporcional al ÁREA de cada
    localidad, no a partes iguales. Si alguien 'simplificara' promediando los
    promedios, Altamira (25 km²) pesaría igual que Tampico (55 km²).
    """
    ciu = pd.read_csv(C.CSV_CIUDADES, dtype={"cvegeo": str})
    pares = pd.read_csv(C.CSV_NODOS_CIUDADES, dtype={"cvegeo": str})
    m = pares.merge(ciu[["cvegeo", "area_km2"]], on="cvegeo")
    m = m[m["nombre_conglomerado"] == "Tampico"]
    aporte = (m["peso"] * m["area_km2"]).groupby(m["ciudad"]).sum()
    esperado = ciu.set_index("ciudad").loc[aporte.index, "area_km2"]
    # rtol flojo a propósito: `peso` se guarda redondeado a 6 decimales en el
    # CSV versionado, lo que introduce un error relativo de ~1e-6. Exigir más
    # sería probar el redondeo, no el reparto.
    pd.testing.assert_series_equal(
        (aporte / aporte.sum()).sort_index(),
        (esperado / esperado.sum()).sort_index(),
        check_names=False, rtol=1e-5)


def test_el_conglomerado_no_pierde_ni_duplica_nodos():
    # Los 225 nodos asignados siguen ahí, sin repetirse dentro de una unidad.
    for ambito in ("localidades", "conglomerados", "global"):
        w = Q.pesos(ambito)
        assert w["nodo_id"].nunique() == 225, ambito
        assert not w.duplicated(["cvegeo", "nodo_id"]).any(), ambito


def test_global_es_una_sola_unidad_con_todos_los_nodos():
    w = Q.pesos("global")
    assert w["ciudad"].unique().tolist() == ["Tamaulipas urbano"]
    assert len(w) == 225


def test_ciudades_no_se_mezcla_con_ambitos_agrupados():
    with pytest.raises(ValueError, match="no se combina"):
        Q.pesos("conglomerados", ciudades=["victoria"])


def test_un_ambito_inventado_falla_claro():
    with pytest.raises(ValueError, match="desconocido"):
        Q.pesos("municipios")


# --------------------------------------------------------------------------- #
# Rango de fechas
# --------------------------------------------------------------------------- #
def test_el_rango_abre_el_anio_siguiente():
    """
    Las últimas horas del 31 de diciembre LOCAL viven en el archivo del año
    siguiente (local = UTC−6). Sin abrirlo, ese día saldría con 18 h.
    """
    assert Q._anios("2023-01-01", "2023-12-31") == [2023, 2024]
    assert Q._anios("2024-06-01", "2024-06-30") == [2024]
    assert Q._anios(None, None) == list(C.ANIOS_CLIMA)


_HAY_PARQUET = os.path.exists(os.path.join(
    C.RAIZ, "Data", C.REGION, "2024", "Finales", "completo",
    "dataset_tamaulipas_completo_24h_2024.parquet"))
integracion = pytest.mark.skipif(not _HAY_PARQUET,
                                 reason="faltan los parquet anuales")


@integracion
def test_consulta_de_victoria_por_nombre_y_rango():
    d = Q.serie(["temperature"], ciudad="victoria", desde="2024-06-01",
                hasta="2024-06-30", frecuencia="dia")
    assert len(d) == 30
    assert d["ciudad"].unique().tolist() == ["Ciudad Victoria"]
    assert (d["n_horas"] == 24).all()
    assert (d["temperature_min"] <= d["temperature_max"]).all()


@integracion
def test_el_rango_incluye_los_extremos():
    h = Q.serie(["temperature"], ciudad="280410001", desde="2024-06-01",
                hasta="2024-06-03")
    fechas = pd.to_datetime(h["fecha_local"])
    assert fechas.min() == pd.Timestamp("2024-06-01")
    assert fechas.max() == pd.Timestamp("2024-06-03")
    assert len(h) == 3 * 24


@integracion
def test_el_dia_final_de_un_anio_sale_completo():
    d = Q.serie(["temperature"], ciudad="tampico", desde="2023-12-30",
                hasta="2023-12-31", frecuencia="dia")
    assert (d["n_horas"] == 24).all()


def test_un_rango_fuera_de_los_datos_avisa():
    # No necesita los parquet: debe fallar ANTES de intentar leerlos.
    with pytest.raises(ValueError, match="no cae dentro"):
        Q.serie(["temperature"], ciudad="victoria", desde="1999-01-01",
                hasta="1999-12-31")


def test_un_rango_al_reves_avisa():
    with pytest.raises(ValueError, match="al revés"):
        Q.serie(["temperature"], ciudad="victoria", desde="2024-12-31",
                hasta="2024-01-01")
