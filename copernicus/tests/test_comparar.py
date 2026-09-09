"""
Pruebas del cruce NSRDB vs ERA5.

    conda run -n rs pytest copernicus/tests -q
"""
from __future__ import annotations
import glob
import os

import numpy as np
import pandas as pd
import pytest

from copernicus import comparar as K
from copernicus import config as C


# --------------------------------------------------------------------------- #
# Diferencia circular
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("a,b,esperado", [
    (350, 10, -20), (10, 350, 20), (0, 0, 0), (271, 90, -179), (89, 270, -181 + 360),
])
def test_diferencia_circular_toma_el_camino_corto(a, b, esperado):
    """
    350° − 10° son 20 grados de diferencia, no 340. Restar ángulos como números
    infla el error de la dirección del viento sin que se note.
    """
    assert K._dif_circular(a, b) == pytest.approx(esperado)


def test_rumbos_opuestos_dan_180_con_cualquier_signo():
    """
    A 180° exactos el signo es arbitrario: +180 y −180 son el mismo ángulo. Lo
    que importa es la magnitud, y que no se cuele un 0.
    """
    for a, b in ((90, 270), (270, 90), (0, 180)):
        assert abs(K._dif_circular(a, b)) == pytest.approx(180.0)


def test_la_resta_ingenua_se_equivocaria():
    """Documenta el error que evita `_dif_circular`."""
    assert 350 - 10 == 340                       # lo que daría restar sin más
    assert K._dif_circular(350, 10) == -20.0


# --------------------------------------------------------------------------- #
# Variables que no son comparables
# --------------------------------------------------------------------------- #
def test_el_viento_esta_marcado_como_no_comparable():
    """
    ERA5 da viento a 10 m y NSRDB a 2 m. La diferencia saldrá siempre positiva
    y no es error del modelo: la salida tiene que decirlo.
    """
    assert "wind_speed" in K.NO_COMPARABLES
    assert "wind_direction" in K.NO_COMPARABLES
    assert "10 m" in K.NO_COMPARABLES["wind_speed"]


def test_la_temperatura_si_es_comparable():
    """Ambas fuentes la dan a 2 m: es la comparación limpia del conjunto."""
    assert "temperature" not in K.NO_COMPARABLES
    assert "ghi" not in K.NO_COMPARABLES


# --------------------------------------------------------------------------- #
# Métricas
# --------------------------------------------------------------------------- #
def _cruce_sintetico(desfase=2.0):
    n = 48
    t = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    base = np.linspace(10, 30, n)
    d = {"producto": "land", "nodo_id": 1, "datetime_utc": t}
    for v in K.VARIABLES:
        d[f"{v}_nsrdb"] = base
        d[f"{v}_era5"] = base + desfase
    return pd.DataFrame(d)


def test_metricas_recuperan_un_sesgo_conocido():
    m = K.metricas(_cruce_sintetico(2.0), por=("producto", "nodo_id"))
    t = m[m.variable == "temperature"].iloc[0]
    assert t["sesgo"] == pytest.approx(2.0)
    assert t["mae"] == pytest.approx(2.0)
    assert t["rmse"] == pytest.approx(2.0)
    assert t["corr"] == pytest.approx(1.0)
    assert t["n"] == 48


def test_la_direccion_del_viento_no_lleva_correlacion():
    """La correlación lineal de un ángulo no significa nada; se deja en NaN."""
    m = K.metricas(_cruce_sintetico(), por=("producto", "nodo_id"))
    assert np.isnan(m[m.variable == "wind_direction"].iloc[0]["corr"])


def test_las_metricas_ignoran_los_nan():
    df = _cruce_sintetico(2.0)
    df.loc[:9, "temperature_era5"] = np.nan
    t = K.metricas(df, por=("producto",))
    fila = t[t.variable == "temperature"].iloc[0]
    assert fila["n"] == 38
    assert fila["sesgo"] == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# Integración con lo descargado
# --------------------------------------------------------------------------- #
_HAY_SERIES = bool(glob.glob(os.path.join(C.dir_series("land"), "land_*.parquet")))
integracion = pytest.mark.skipif(
    not _HAY_SERIES, reason="no hay series de ERA5 extraídas")


@integracion
def test_el_cruce_alinea_las_zonas_horarias():
    """
    ERA5 llega en UTC sin zona y NSRDB con ella. Sin normalizar, el merge falla
    —o, si alguien lo 'arregla' quitando la zona, desplaza seis horas y todo
    parece funcionar—.
    """
    j = K.cruzar([2024], [1], productos=("land",))
    assert len(j) > 0
    assert str(j["datetime_utc"].dt.tz) == "UTC"
    # El ciclo diario debe seguir cuadrando: el pico de GHI del NSRDB y el de
    # ERA5 caen en la misma hora UTC.
    ciclo = j.groupby(j["datetime_utc"].dt.hour)[["ghi_era5", "ghi_nsrdb"]].mean()
    assert ciclo["ghi_era5"].idxmax() == ciclo["ghi_nsrdb"].idxmax()


@integracion
def test_era5_land_se_parece_mas_al_nsrdb_que_single():
    """
    Con 9 km contra 31 km, la malla fina debería acercarse más al NSRDB (4 km)
    en las variables ligadas al terreno. Si esto se invierte, sospecha del
    emparejamiento de celdas.
    """
    j = K.cruzar([2024], [1])
    r = K.resumen(j).set_index(["variable", "producto"])["rmse"]
    for v in ("temperature", "pressure"):
        assert r[(v, "land")] < r[(v, "single")], v
