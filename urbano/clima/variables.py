"""
Catálogo de las variables del dataset NSRDB: unidad, ALTURA de referencia y
cómo hay que promediarlas.

## La pregunta de la altura

Nuestro producto es **NSRDB GOES aggregated PSM v4**. Las variables
meteorológicas no las mide el satélite: vienen de la reanálisis **MERRA-2**,
interpoladas a la celda de 4 km. En el catálogo oficial de NREL
(`nsrdb/config/nsrdb_vars.csv`) cada variable declara el dataset MERRA-2 del que
sale:

    air_temperature   -> T2M   (temperatura del aire a 2 m)
    specific_humidity -> QV2M  (humedad específica a 2 m)
    surface_pressure  -> PS    (presión en superficie)

y en `nsrdb/data_model/merra.py` el viento se arma con
`height = '10M' if '_10m' in name else '2M'`, o sea que la columna `wind_speed`
sin sufijo es la de **U2M/V2M**.

Conclusión: **`temperature` es a 2 m**, no a nivel de superficie ni a 10 m.
`relative_humidity` y `dew_point` son DERIVADAS de T2M + QV2M + PS, así que
también son efectivamente de 2 m. `pressure` es presión en superficie (no a 2 m),
corregida por elevación. El viento es de 2 m — importante, porque la convención
meteorológica habitual (OMM) es 10 m: **estos valores no son comparables sin más
con los de una estación estándar**.

## Cómo se promedia cada una

- `continua`: media aritmética ponderada. La mayoría.
- `circular`: `wind_direction` está en grados 0–360. Promediar 350° y 10°
  aritméticamente da 180° (el sur), que es exactamente lo contrario del norte
  correcto. Se promedia como vector unitario.
- `categorica`: `cloud_type` es un código, no una cantidad; promediarlo no
  significa nada. Se excluye de las agregaciones por omisión.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Variable:
    nombre: str
    unidad: str
    tipo: str          # continua | circular | categorica
    altura: str        # "2 m", "superficie", "columna", "—"
    descripcion: str


_V = [
    # --- irradiancia (plano horizontal, superficie) -------------------------
    Variable("ghi", "W/m²", "continua", "superficie",
             "Irradiancia global horizontal"),
    Variable("dni", "W/m²", "continua", "superficie",
             "Irradiancia directa normal"),
    Variable("dhi", "W/m²", "continua", "superficie",
             "Irradiancia difusa horizontal"),
    Variable("clearsky_ghi", "W/m²", "continua", "superficie",
             "GHI de cielo despejado (modelo)"),
    Variable("clearsky_dni", "W/m²", "continua", "superficie",
             "DNI de cielo despejado (modelo)"),
    Variable("clearsky_dhi", "W/m²", "continua", "superficie",
             "DHI de cielo despejado (modelo)"),
    Variable("ghi_uv_280_400", "W/m²", "continua", "superficie",
             "Irradiancia UV 280–400 nm"),
    Variable("ghi_uv_295_385", "W/m²", "continua", "superficie",
             "Irradiancia UV 295–385 nm"),

    # --- meteorología MERRA-2 ------------------------------------------------
    Variable("temperature", "°C", "continua", "2 m",
             "Temperatura del aire a 2 m (MERRA-2 T2M, corregida por elevación)"),
    Variable("dew_point", "°C", "continua", "2 m",
             "Punto de rocío, derivado de T2M/QV2M/PS"),
    Variable("relative_humidity", "%", "continua", "2 m",
             "Humedad relativa, derivada de T2M/QV2M/PS"),
    Variable("pressure", "mbar", "continua", "superficie",
             "Presión en superficie (MERRA-2 PS, corregida por elevación)"),
    Variable("precipitable_water", "cm", "continua", "columna",
             "Agua precipitable en la columna"),
    Variable("wind_speed", "m/s", "continua", "2 m",
             "Velocidad del viento a 2 m (MERRA-2 U2M/V2M) — NO a 10 m"),
    Variable("wind_direction", "grados", "circular", "2 m",
             "Dirección del viento a 2 m (de dónde sopla, 0–360)"),

    # --- geometría solar y superficie ---------------------------------------
    Variable("solar_zenith_angle", "grados", "continua", "—",
             "Ángulo cenital solar"),
    Variable("surface_albedo", "—", "continua", "superficie",
             "Albedo de superficie (0–1)"),

    # --- atmósfera -----------------------------------------------------------
    Variable("aerosol_optical_depth", "—", "continua", "columna",
             "Profundidad óptica de aerosol"),
    Variable("alpha", "—", "continua", "columna", "Exponente de Ångström"),
    Variable("asymmetry", "—", "continua", "columna",
             "Factor de asimetría del aerosol"),
    Variable("ssa", "—", "continua", "columna",
             "Albedo de dispersión simple"),
    Variable("ozone", "atm-cm", "continua", "columna", "Columna de ozono"),

    # --- calidad del dato / categóricas -------------------------------------
    Variable("cloud_type", "código", "categorica", "—",
             "Tipo de nube (0–12, −15 sin dato); ver REFERENCIA_NSRDB.md"),
    Variable("fill_flag", "%", "continua", "—",
             "% de sub-muestras rellenadas al agregar la celda-hora"),
    Variable("cloud_fill_flag", "código", "categorica", "—",
             "Bandera de relleno de nubes"),
]

CATALOGO: dict[str, Variable] = {v.nombre: v for v in _V}

CONTINUAS = tuple(v.nombre for v in _V if v.tipo == "continua")
CIRCULARES = tuple(v.nombre for v in _V if v.tipo == "circular")
CATEGORICAS = tuple(v.nombre for v in _V if v.tipo == "categorica")

# Conjunto por omisión de las agregaciones: las variables que de verdad se leen
# como "clima de la ciudad". El resto sigue disponible pidiéndolo por nombre.
POR_OMISION = ("temperature", "relative_humidity", "dew_point", "wind_speed",
               "wind_direction", "pressure", "precipitable_water",
               "ghi", "dni", "dhi")


def validar(variables) -> list[str]:
    """Normaliza una lista de variables y rechaza las que no existen."""
    vs = list(variables)
    desconocidas = [v for v in vs if v not in CATALOGO]
    if desconocidas:
        raise ValueError(
            f"Variables desconocidas: {desconocidas}. "
            f"Disponibles: {sorted(CATALOGO)}")
    categoricas = [v for v in vs if CATALOGO[v].tipo == "categorica"]
    if categoricas:
        raise ValueError(
            f"{categoricas} son categóricas (códigos, no cantidades): "
            "promediarlas no significa nada. Agrégalas aparte si las necesitas.")
    return vs


def tabla() -> "pd.DataFrame":  # noqa: F821
    """El catálogo como DataFrame, para mostrarlo en el notebook."""
    import pandas as pd
    return pd.DataFrame([
        {"variable": v.nombre, "unidad": v.unidad, "altura": v.altura,
         "tipo": v.tipo, "descripcion": v.descripcion} for v in _V])


if __name__ == "__main__":
    print(tabla().to_string(index=False))
