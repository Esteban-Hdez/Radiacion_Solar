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


# --------------------------------------------------------------------------- #
# Alineación de la hora
# --------------------------------------------------------------------------- #
@integracion
def test_alinear_reetiqueta_era5_una_hora_atras():
    """
    `alinear=True` resta una hora a la marca de ERA5 antes del merge: el valor
    que ERA5 rotula 13:00 describe el intervalo 12:00-13:00, que el NSRDB rotula
    12:00. Se comprueba sobre el dato, no sobre el índice: el GHI de ERA5 que
    queda emparejado a una hora dada debe ser el que antes estaba una después.
    """
    crudo = K.cruzar([2024], [6], productos=("land",))
    alineado = K.cruzar([2024], [6], productos=("land",), alinear=True)

    a = crudo.set_index(["nodo_id", "datetime_utc"])["ghi_era5"]
    b = alineado.set_index(["nodo_id", "datetime_utc"])["ghi_era5"]
    # La serie cruda con su marca atrasada una hora tiene que ser, punto por
    # punto, la alineada. Se compara entera y no un valor suelto: casi todas las
    # horas del día son noche y un 0.0 == 0.0 pasaría sin probar nada.
    desplazada = pd.Series(a.to_numpy(), index=pd.MultiIndex.from_arrays(
        [a.index.get_level_values(0),
         a.index.get_level_values(1) - pd.Timedelta(hours=1)]))
    par = pd.concat([b.rename("alineado"),
                     desplazada.rename("crudo_atrasado")], axis=1).dropna()

    assert len(par) > 10_000, "el solape quedó demasiado corto para probar nada"
    assert par["alineado"].equals(par["crudo_atrasado"])
    assert par["alineado"].max() > 500, "sin horas de sol no se prueba el ciclo"


@integracion
def test_alinear_baja_el_rmse_del_ghi_y_deja_el_sesgo_donde_estaba():
    """
    El desfase es de emparejamiento, no de nivel: corregirlo tiene que bajar el
    RMSE con fuerza (~37 % en GHI) y dejar el SESGO casi igual, porque desplazar
    una serie en el tiempo no cambia su media.

    Si al alinear se moviera también el sesgo, el problema sería otro y esta
    corrección lo estaría tapando.
    """
    sin = K.resumen(K.cruzar([2024], [6], productos=("land",)))
    con = K.resumen(K.cruzar([2024], [6], productos=("land",), alinear=True))
    g_sin = sin[sin.variable == "ghi"].iloc[0]
    g_con = con[con.variable == "ghi"].iloc[0]

    assert g_con["rmse"] < g_sin["rmse"] * 0.75
    assert g_con["corr"] > g_sin["corr"]
    assert g_con["sesgo"] == pytest.approx(g_sin["sesgo"], abs=1.0)


@integracion
def test_el_modo_viaja_con_la_tabla():
    """
    Dos tablas de métricas calculadas en modos distintos son indistinguibles a
    simple vista y difieren un 37 % en el GHI: la bandera tiene que ir dentro.
    """
    assert not K.cruzar([2024], [6], productos=("land",))["alineado"].any()
    assert K.cruzar([2024], [6], productos=("land",), alinear=True)["alineado"].all()
    m = K.metricas(K.cruzar([2024], [6], productos=("land",), alinear=True),
                   por=("producto",))
    assert m["alineado"].all()


def test_las_tablas_viejas_sin_bandera_se_leen_como_no_alineadas():
    """
    Una tabla guardada antes de que existiera el parámetro no tiene la columna;
    suponer `False` es lo que aquellas hacían, y suponer `True` las presentaría
    como algo que no son.
    """
    m = K.metricas(_cruce_sintetico(2.0), por=("producto",))
    assert not m["alineado"].any()
