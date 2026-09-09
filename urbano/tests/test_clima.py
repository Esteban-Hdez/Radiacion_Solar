"""
Pruebas de la agregación climática por ciudad.

Las tres primeras no tocan disco: comprueban la ARITMÉTICA de la agregación
sobre datos sintéticos donde la respuesta correcta se conoce a mano. Las últimas
son de integración y se saltan solas si faltan los parquet anuales.

    conda run -n rs pytest urbano/tests -q
"""
from __future__ import annotations
import os

import numpy as np
import pandas as pd
import pytest

from urbano import config as C
from urbano.clima import agregacion as G
from urbano.clima import variables as V

LLAVES = ["cvegeo", "datetime"]


def _largo(valores, pesos, var="temperature"):
    t = pd.Timestamp("2020-06-01 12:00", tz="UTC")
    return pd.DataFrame({
        "cvegeo": ["X"] * len(valores),
        "datetime": [t] * len(valores),
        "peso": pesos,
        var: valores,
    })


def test_la_media_ponderada_usa_los_pesos():
    df = _largo([10.0, 20.0], [0.75, 0.25])
    r = G._media_ponderada(df, ["temperature"], LLAVES)
    assert r["temperature"].iloc[0] == pytest.approx(12.5)


def test_los_nan_renormalizan_en_vez_de_sesgar():
    # Con un nodo sin dato, la media debe ser la del nodo que SÍ tiene dato,
    # no `0.75*10 = 7.5` (que sería dividir entre el peso total).
    df = _largo([10.0, np.nan], [0.75, 0.25])
    r = G._media_ponderada(df, ["temperature"], LLAVES)
    assert r["temperature"].iloc[0] == pytest.approx(10.0)


def test_hora_sin_ningun_dato_queda_nan():
    df = _largo([np.nan, np.nan], [0.75, 0.25])
    r = G._media_ponderada(df, ["temperature"], LLAVES)
    assert np.isnan(r["temperature"].iloc[0])


def test_la_direccion_del_viento_se_promedia_en_circulo():
    # 350° y 10° son ambos "casi norte": la media correcta es 0°, no 180°.
    df = _largo([350.0, 10.0], [0.5, 0.5], var="wind_direction")
    r = G._direccion_ponderada(df, LLAVES)
    assert r["wind_direction"].iloc[0] % 360 == pytest.approx(0.0, abs=1e-6)
    # Y la media aritmética ingenua daría justo lo contrario.
    assert np.mean([350.0, 10.0]) == pytest.approx(180.0)


def test_el_promedio_simple_ignora_los_pesos():
    pesos = pd.DataFrame({
        "cvegeo": ["X", "X", "X", "Y"],
        "nodo_id": [1, 2, 3, 4],
        "peso": [0.90, 0.07, 0.03, 1.0],
    })
    u = G.pesos_uniformes(pesos)
    assert u.loc[u["cvegeo"] == "X", "peso"].tolist() == [1 / 3, 1 / 3, 1 / 3]
    # Sigue sumando 1 por ciudad, así que el resto del pipeline no cambia.
    assert u.groupby("cvegeo")["peso"].sum().round(12).eq(1.0).all()
    # Una ciudad de un solo nodo es idéntica en los dos modos.
    assert u.loc[u["cvegeo"] == "Y", "peso"].iloc[0] == 1.0


def test_el_promedio_simple_da_la_media_aritmetica():
    df = _largo([10.0, 20.0], [1 / 2, 1 / 2])
    r = G._media_ponderada(df, ["temperature"], LLAVES)
    assert r["temperature"].iloc[0] == pytest.approx(15.0)


def test_el_promedio_simple_hereda_la_renormalizacion():
    # El caso que motiva implementarlo con pesos uniformes en vez de una rama
    # aparte: los NaN se tratan igual que en el modo ponderado.
    df = _largo([10.0, np.nan, 30.0], [1 / 3, 1 / 3, 1 / 3])
    r = G._media_ponderada(df, ["temperature"], LLAVES)
    assert r["temperature"].iloc[0] == pytest.approx(20.0)


def test_la_frontera_tiene_su_propio_huso():
    assert G.tz_de_municipio("032") == G.TZ_FRONTERA      # Reynosa
    assert G.tz_de_municipio("22") == G.TZ_FRONTERA       # Matamoros, sin cero
    assert G.tz_de_municipio("041") == G.TZ_INTERIOR      # Victoria
    assert G.tz_de_municipio("038") == G.TZ_INTERIOR      # Tampico


def test_las_categoricas_se_rechazan():
    with pytest.raises(ValueError, match="categóricas"):
        V.validar(["temperature", "cloud_type"])
    with pytest.raises(ValueError, match="desconocidas"):
        V.validar(["temperatura"])


# --------------------------------------------------------------------------- #
# Integración
# --------------------------------------------------------------------------- #
_HAY_PARQUET = os.path.exists(os.path.join(
    C.RAIZ, "Data", C.REGION, "2024", "Finales", "completo",
    "dataset_tamaulipas_completo_24h_2024.parquet"))
integracion = pytest.mark.skipif(
    not (_HAY_PARQUET and os.path.exists(C.CSV_NODOS_CIUDADES)),
    reason="faltan los parquet anuales o los pesos nodo↔ciudad")


@pytest.fixture(scope="module")
def horaria():
    return G.serie_horaria(["temperature", "relative_humidity", "wind_direction"],
                           top=3, anios=[2024])


@integracion
def test_la_serie_horaria_esta_completa(horaria):
    # 3 ciudades × 366 días de 2024 × 24 h.
    assert len(horaria) == 3 * 366 * 24
    assert horaria["temperature"].notna().all()


@integracion
def test_los_rangos_fisicos_son_plausibles(horaria):
    assert horaria["temperature"].between(-15, 55).all()
    # La HR se sale de 100 por hasta 1.4e-14: es el error de redondeo de la
    # media ponderada cuando todos los nodos valen exactamente 100, no un dato
    # malo. Se tolera en vez de recortar, para no maquillar la serie.
    assert horaria["relative_humidity"].between(0, 100 + 1e-9).all()
    assert horaria["wind_direction"].between(0, 360).all()


@integracion
def test_el_dia_local_agrupa_24_horas(horaria):
    d = G.resumen_diario(horaria)
    completos = d[d["n_horas"] == 24]
    # Todo el interior del periodo tiene días de 24 h; solo los bordes y el
    # cambio de horario de verano se salen.
    assert len(completos) / len(d) > 0.95
    assert (d["temperature_min"] <= d["temperature_media"]).all()
    assert (d["temperature_media"] <= d["temperature_max"]).all()


@integracion
def test_ponderado_y_simple_difieren_pero_poco():
    var = ["temperature"]
    # San Fernando: 5 nodos con uno que aporta el 64 % del peso. Es donde más se
    # separan los dos modos (0.61 °C), más que en Reynosa: con 25 nodos los
    # pesos de Reynosa ya son casi uniformes y el ponderado se parece al simple.
    pond = G.serie_horaria(var, cvegeos=["280350001"], anios=[2024])
    simple = G.serie_horaria(var, cvegeos=["280350001"], anios=[2024],
                             ponderar=False)
    d = (pond["temperature"] - simple["temperature"]).abs()
    assert d.max() > 0, "los dos modos no deberían dar exactamente lo mismo"
    assert d.mean() < 1.0, "tampoco deberían separarse más de 1 °C en promedio"


@integracion
def test_una_ciudad_de_un_nodo_es_igual_en_los_dos_modos():
    # San Nicolás (280360001) tiene un solo nodo: ahí no hay nada que ponderar.
    var = ["temperature"]
    pond = G.serie_horaria(var, cvegeos=["280360001"], anios=[2024])
    simple = G.serie_horaria(var, cvegeos=["280360001"], anios=[2024],
                             ponderar=False)
    pd.testing.assert_series_equal(pond["temperature"], simple["temperature"])


@integracion
def test_el_dia_local_no_es_el_dia_utc(horaria):
    # Si alguien "simplificara" quitando la conversión de huso, esto lo caza.
    utc = horaria["datetime_utc"].dt.tz_convert("UTC").dt.date
    assert (pd.Series(utc.to_numpy()) != horaria["fecha_local"]).any()
