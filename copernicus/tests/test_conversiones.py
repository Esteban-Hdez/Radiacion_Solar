"""
Pruebas de las conversiones de ERA5.

Ninguna toca la red ni necesita datos descargados: comprueban la ARITMÉTICA
sobre casos construidos a mano, que es donde un error pasaría inadvertido porque
el resultado seguiría pareciendo plausible.

    conda run -n rs pytest copernicus/tests -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from copernicus import config as C
from copernicus import extraer as E


# --------------------------------------------------------------------------- #
# Desacumulación de la radiación: el punto delicado
# --------------------------------------------------------------------------- #
def _dia_sintetico(w_m2: float = 100.0):
    """Un día de ERA5-Land con irradiancia constante, acumulada desde 00 UTC."""
    horas = pd.Series(range(24))
    acum = pd.Series([0.0] + [h * 3600.0 * w_m2 for h in range(1, 24)])
    return acum, horas


def test_single_es_una_simple_division():
    acum, horas = _dia_sintetico()
    r = E.desacumular(acum, horas, "horario")
    np.testing.assert_allclose(r.to_numpy(), acum.to_numpy() / 3600.0)


def test_land_recupera_la_irradiancia_constante():
    """
    Si la acumulación crece 100 W/m² por hora desde las 00 UTC, desacumular
    tiene que devolver 100 en cada hora, no una rampa.
    """
    acum, horas = _dia_sintetico(100.0)
    r = E.desacumular(acum, horas, "desde_00utc").to_numpy()
    assert np.isnan(r[0]), "la hora 00 necesita el paso previo, debe quedar NaN"
    np.testing.assert_allclose(r[1:], 100.0)


def test_la_hora_01_no_se_diferencia():
    """
    A las 01 UTC el acumulado ya es la primera hora del día. Restarle el paso de
    las 00 —que trae las 24 h anteriores— daría un negativo enorme. Este test
    caza justamente ese error.
    """
    horas = pd.Series([0, 1, 2])
    # 00 UTC trae el total del día anterior (grande); 01 y 02, el día en curso.
    acum = pd.Series([20e6, 360000.0, 720000.0])
    r = E.desacumular(acum, horas, "desde_00utc").to_numpy()
    assert r[1] == pytest.approx(100.0)
    assert r[2] == pytest.approx(100.0)
    assert (r[1:] >= 0).all()


def test_aplicar_la_regla_equivocada_se_nota():
    """
    Documenta el modo de fallo: con la regla de `single` sobre datos de `land`,
    la irradiancia sale como una rampa creciente en vez de constante.
    """
    acum, horas = _dia_sintetico(100.0)
    mal = E.desacumular(acum, horas, "horario").to_numpy()
    assert mal[12] == pytest.approx(1200.0)          # absurdo: > constante solar
    assert (np.diff(mal[1:]) > 0).all()              # rampa monótona


def test_un_paso_desconocido_falla():
    acum, horas = _dia_sintetico()
    with pytest.raises(ValueError, match="desconocido"):
        E.desacumular(acum, horas, "cada_6h")


def test_las_dos_ramas_devuelven_lo_mismo_tipo():
    acum, horas = _dia_sintetico()
    for paso in ("horario", "desde_00utc"):
        assert isinstance(E.desacumular(acum, horas, paso), pd.Series)


# --------------------------------------------------------------------------- #
# Viento y humedad
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("u,v,esperado", [
    (0.0, -1.0, 0.0),      # sopla hacia el sur -> viene del NORTE
    (-1.0, 0.0, 90.0),     # sopla hacia el oeste -> viene del ESTE
    (0.0, 1.0, 180.0),     # sopla hacia el norte -> viene del SUR
    (1.0, 0.0, 270.0),     # sopla hacia el este -> viene del OESTE
])
def test_direccion_del_viento_es_de_donde_sopla(u, v, esperado):
    """
    Convención meteorológica, la misma del NSRDB: la dirección es de DÓNDE
    viene el viento, no hacia dónde va. Confundirlas rota el resultado 180°.
    """
    vel, direccion = E._viento(u, v)
    assert vel == pytest.approx(1.0)
    assert direccion == pytest.approx(esperado)


def test_velocidad_del_viento_es_el_modulo():
    vel, _ = E._viento(3.0, 4.0)
    assert vel == pytest.approx(5.0)


def test_humedad_relativa_saturada_es_100():
    assert E._humedad_relativa(25.0, 25.0) == pytest.approx(100.0)


def test_humedad_relativa_baja_con_el_rocio():
    hr = [float(E._humedad_relativa(30.0, td)) for td in (30, 20, 10, 0)]
    assert hr[0] == pytest.approx(100.0)
    assert all(a > b for a, b in zip(hr, hr[1:])), "debe decrecer con el rocío"
    assert all(0 <= h <= 100 for h in hr)


# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
def test_el_area_cubre_los_43_nodos():
    import os
    if not os.path.exists(C.CSV_NODOS):
        pytest.skip("faltan los nodos de urbano/")
    t = E.cargar_nodos()
    N, W, S, Eo = C.AREA
    assert t["latitude"].between(S, N).all()
    assert t["longitude"].between(W, Eo).all()
    # Con margen suficiente para buscar celda de tierra alrededor de la costa.
    assert t["latitude"].min() - S > 0.2 and N - t["latitude"].max() > 0.2


def test_cada_producto_declara_su_acumulacion():
    for nombre, p in C.PRODUCTOS.items():
        assert p["paso_acumulacion"] in ("horario", "desde_00utc"), nombre
        assert p["dataset"].startswith("reanalysis-era5")


def test_las_credenciales_no_estan_en_el_codigo():
    """La clave del CDS vive en `.env`, nunca en un archivo versionado."""
    import glob
    import re
    for f in glob.glob("copernicus/**/*.py", recursive=True):
        texto = open(f, encoding="utf-8").read()
        uuids = re.findall(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                           r"[0-9a-f]{4}-[0-9a-f]{12}\b", texto)
        assert not uuids, f"posible credencial en {f}: {uuids}"


def test_el_ruido_negativo_se_recorta():
    """
    Restar acumulados casi iguales deja negativos de ~1e-4 W/m². Es redondeo,
    no física: se recorta a cero.
    """
    horas = pd.Series([1, 2, 3])
    acum = pd.Series([360000.0, 720000.0, 720000.0 - 2.0])   # −0.00055 W/m²
    r = E.desacumular(acum, horas, "desde_00utc")
    assert (r >= 0).all()
    assert r.iloc[2] == 0.0


def test_un_negativo_grande_es_un_error_y_se_avisa():
    """
    Un negativo grande NO es redondeo: significa que la ventana de acumulación
    supuesta es la equivocada. Ahí hay que enterarse, no recortar en silencio.
    """
    horas = pd.Series([1, 2, 3])
    acum = pd.Series([360000.0, 720000.0, 0.0])              # −200 W/m²
    with pytest.raises(ValueError, match="demasiado"):
        E.desacumular(acum, horas, "desde_00utc")
