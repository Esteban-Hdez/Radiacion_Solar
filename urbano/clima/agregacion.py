"""
Series climáticas POR CIUDAD a partir de los nodos NSRDB.

Cadena de agregación, en el orden en que ocurre:

    nodo-hora  --(media ponderada por `peso`)-->  ciudad-hora
    ciudad-hora --(media / mínimo / máximo)-->    ciudad-día

Tres decisiones que cambian el resultado y por eso están explícitas:

1. **Ponderación.** El `peso` de `nodos_ciudades.csv` es la fracción del área
   urbana que cae en la celda de cada nodo, y suma 1 por ciudad. Así, el nodo que
   cubre el centro de Reynosa pesa más que el que apenas roza un borde. Si un
   nodo tiene NaN en una hora, los pesos se renormalizan sobre los presentes: la
   media de esa hora sigue siendo una media legítima de lo disponible.

   Con `ponderar=False` se obtiene el **promedio simple**: todos los nodos de la
   ciudad cuentan igual. Es el mismo cálculo con pesos uniformes, así que hereda
   la renormalización y la media circular; solo cambia el vector de pesos. Más
   fácil de explicar en un informe, pero representa peor a la ciudad.

2. **Huso horario.** El dataset está en **UTC**. El mínimo y el máximo DIARIOS
   dependen de dónde se corta el día: cortarlo en UTC parte la noche por la
   mitad y mezcla la madrugada de un día con la del siguiente. Por eso el día se
   define en **hora local** (`America/Monterrey`, y `America/Matamoros` para los
   municipios de la franja fronteriza, que sí siguen el horario de verano de
   EE. UU.). La columna UTC se conserva por si hace falta.

3. **Dirección del viento.** Es circular: promediar 350° y 10° aritméticamente
   da 180°, el rumbo opuesto. Se promedia como vector unitario ponderado. Su
   mínimo y máximo diarios NO se reportan, porque en una variable circular no
   significan nada.
"""
from __future__ import annotations
import os

import numpy as np
import pandas as pd

from urbano import config as C
from urbano.clima import variables as V

# --------------------------------------------------------------------------- #
# Husos horarios
# --------------------------------------------------------------------------- #
TZ_INTERIOR = "America/Monterrey"
TZ_FRONTERA = "America/Matamoros"
# Los 10 municipios de la franja fronteriza de Tamaulipas que MANTIENEN el
# horario estacional (Ley de los Husos Horarios, DOF 2022-10-28): el resto del
# estado dejó de aplicar el horario de verano ese año, ellos no. Claves INEGI
# verificadas contra la capa 28mun del Marco Geoestadístico.
MUN_FRONTERA = {
    "007",  # Camargo
    "014",  # Guerrero
    "015",  # Gustavo Díaz Ordaz
    "022",  # Matamoros
    "024",  # Mier
    "025",  # Miguel Alemán
    "027",  # Nuevo Laredo
    "032",  # Reynosa
    "033",  # Río Bravo
    "040",  # Valle Hermoso
}


def tz_de_municipio(cve_mun: str) -> str:
    """Huso horario del municipio (la franja fronteriza va aparte)."""
    return TZ_FRONTERA if str(cve_mun).zfill(3) in MUN_FRONTERA else TZ_INTERIOR


# --------------------------------------------------------------------------- #
# Selección de ciudades y nodos
# --------------------------------------------------------------------------- #
def cargar_pesos(cvegeos: list[str] | None = None,
                 top: int | None = None) -> pd.DataFrame:
    """
    Tabla nodo↔ciudad con pesos, filtrada.

    `top=12` toma las 12 ciudades de mayor área urbana; `cvegeos` selecciona a
    mano. Sin ninguno de los dos, devuelve las 63.
    """
    if not os.path.exists(C.CSV_NODOS_CIUDADES):
        raise FileNotFoundError(
            f"Falta {C.CSV_NODOS_CIUDADES}. Corre primero: "
            "`python -m urbano.construir`")
    p = pd.read_csv(C.CSV_NODOS_CIUDADES, dtype={"cvegeo": str, "cve_mun": str})
    if top is not None:
        orden = (pd.read_csv(C.CSV_CIUDADES, dtype={"cvegeo": str})
                 .sort_values("area_km2", ascending=False).head(top)["cvegeo"])
        cvegeos = list(orden)
    if cvegeos is not None:
        p = p[p["cvegeo"].isin([str(c) for c in cvegeos])]
        if p.empty:
            raise ValueError(f"Ninguna ciudad coincide con {cvegeos}")
    return p.reset_index(drop=True)


def pesos_uniformes(pesos: pd.DataFrame) -> pd.DataFrame:
    """
    Reemplaza los pesos por 1/n_nodos dentro de cada ciudad: promedio SIMPLE.

    Se implementa como un caso particular de la media ponderada, no como una
    rama aparte, para que el promedio simple herede exactamente el mismo
    tratamiento de los NaN (renormalizar sobre los nodos presentes) y la misma
    media circular del viento. La única diferencia entre los dos modos queda
    siendo el vector de pesos.

    Ojo con lo que significa: el promedio simple le da el mismo peso al nodo que
    cubre el centro de Reynosa que al que apenas roza un borde de la mancha. Es
    más fácil de explicar, pero representa peor a la ciudad.
    """
    p = pesos.copy()
    p["peso"] = 1.0 / p.groupby("cvegeo")["nodo_id"].transform("nunique")
    return p


# --------------------------------------------------------------------------- #
# Nodo-hora -> ciudad-hora
# --------------------------------------------------------------------------- #
def _media_ponderada(df: pd.DataFrame, variables: list[str],
                     llaves: list[str]) -> pd.DataFrame:
    """
    Media ponderada con renormalización ante NaN.

    Para cada variable se acumulan `Σ peso·x` y `Σ peso` SOLO sobre las filas con
    dato; el cociente es la media de lo observado. Si se dividiera entre el peso
    total, una hora con un nodo faltante quedaría sesgada hacia abajo.
    """
    salida = {}
    peso = df["peso"].to_numpy()
    for v in variables:
        x = df[v].to_numpy(dtype="float64")
        ok = ~np.isnan(x)
        aux = pd.DataFrame({
            "num": np.where(ok, peso * np.nan_to_num(x), 0.0),
            "den": np.where(ok, peso, 0.0),
        })
        for k in llaves:
            aux[k] = df[k].to_numpy()
        g = aux.groupby(llaves, sort=True)[["num", "den"]].sum()
        salida[v] = (g["num"] / g["den"].replace(0, np.nan))
    return pd.DataFrame(salida).reset_index()


def _direccion_ponderada(df: pd.DataFrame, llaves: list[str]) -> pd.DataFrame:
    """Media circular ponderada de `wind_direction`, en grados 0–360."""
    ang = np.radians(df["wind_direction"].to_numpy(dtype="float64"))
    peso = df["peso"].to_numpy()
    ok = ~np.isnan(ang)
    aux = pd.DataFrame({
        "sx": np.where(ok, peso * np.nan_to_num(np.sin(ang)), 0.0),
        "cy": np.where(ok, peso * np.nan_to_num(np.cos(ang)), 0.0),
        "den": np.where(ok, peso, 0.0),
    })
    for k in llaves:
        aux[k] = df[k].to_numpy()
    g = aux.groupby(llaves, sort=True)[["sx", "cy", "den"]].sum()
    ang_m = np.degrees(np.arctan2(g["sx"] / g["den"], g["cy"] / g["den"])) % 360
    return ang_m.where(g["den"] > 0).rename("wind_direction").reset_index()


def serie_horaria(variables=V.POR_OMISION, cvegeos=None, top: int | None = None,
                  anios=(2020, 2021, 2022, 2023, 2024),
                  pesos: pd.DataFrame | None = None,
                  ponderar: bool = True) -> pd.DataFrame:
    """
    Serie horaria por ciudad: una fila por (ciudad, hora).

    Devuelve `datetime_utc`, `hora_local`, `fecha_local` y una columna por
    variable. Es el insumo tanto del CSV horario como del resumen diario.

    `ponderar=False` calcula el PROMEDIO SIMPLE: todos los nodos de la ciudad
    cuentan igual (ver `pesos_uniformes`). Útil para contrastar, y para reportar
    "el promedio de los N nodos de la ciudad" sin tener que explicar la
    ponderación. En las ciudades de un solo nodo ambos modos coinciden.
    """
    variables = V.validar(variables)
    pesos = cargar_pesos(cvegeos, top) if pesos is None else pesos
    if not ponderar:
        pesos = pesos_uniformes(pesos)
    nodos = sorted(pesos["nodo_id"].unique())
    circular = [v for v in variables if v in V.CIRCULARES]
    continuas = [v for v in variables if v not in V.CIRCULARES]

    columnas = ["nodo_id", "datetime"] + list(variables)
    partes = []
    for anio in anios:
        ruta = os.path.join(C.RAIZ, "Data", C.REGION, str(anio), "Finales",
                            "completo",
                            f"dataset_tamaulipas_completo_24h_{anio}.parquet")
        if not os.path.exists(ruta):
            raise FileNotFoundError(
                f"Falta el parquet de {anio}: {ruta}. Los datasets pesados no "
                "se versionan; regénéralos con Utils/descarga_regiones/.")
        partes.append(pd.read_parquet(
            ruta, columns=columnas, filters=[("nodo_id", "in", nodos)]))
    largo = pd.concat(partes, ignore_index=True)
    largo["datetime"] = pd.to_datetime(largo["datetime"], utc=True)

    # Un nodo puede alimentar a dos ciudades vecinas: el merge lo replica, que es
    # justo lo que se quiere (cada ciudad promedia con SUS pesos).
    largo = largo.merge(pesos[["nodo_id", "cvegeo", "ciudad", "cve_mun", "peso"]],
                        on="nodo_id", how="inner")

    llaves = ["cvegeo", "datetime"]
    h = _media_ponderada(largo, continuas, llaves)
    if circular:
        h = h.merge(_direccion_ponderada(largo, llaves), on=llaves, how="left")

    meta = pesos.drop_duplicates("cvegeo")[
        ["cvegeo", "ciudad", "municipio", "cve_mun", "calidad", "n_nodos_ciudad"]]
    h = h.merge(meta, on="cvegeo", how="left")

    # Hora local, por ciudad (la franja fronteriza tiene su propio huso).
    h = h.rename(columns={"datetime": "datetime_utc"})
    locales = []
    for cve_mun, sub in h.groupby("cve_mun", sort=False):
        tz = tz_de_municipio(cve_mun)
        loc = sub["datetime_utc"].dt.tz_convert(tz)
        locales.append(pd.DataFrame(
            {"hora_local": loc.dt.tz_localize(None),
             "fecha_local": loc.dt.tz_localize(None).dt.date,
             "tz": tz}, index=sub.index))
    h = h.join(pd.concat(locales))

    # `cve_mun` viaja hasta la salida: es la clave con la que se cruza cualquier
    # otra fuente municipal (INEGI, CONAPO, catastro), y el nombre del municipio
    # no sirve para eso —se escribe de varias formas y se repite entre estados—.
    orden = (["cvegeo", "ciudad", "municipio", "cve_mun", "calidad",
              "n_nodos_ciudad", "datetime_utc", "hora_local", "fecha_local",
              "tz"] + variables)
    return h[orden].sort_values(["ciudad", "datetime_utc"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Ciudad-hora -> ciudad-día
# --------------------------------------------------------------------------- #
def resumen_diario(horaria: pd.DataFrame, variables=None) -> pd.DataFrame:
    """
    Media, mínimo y máximo diarios por ciudad, sobre la serie horaria.

    El día es el día LOCAL (ver docstring del módulo). Se añade `n_horas` para
    poder descartar días incompletos —los del cambio de horario de verano traen
    23 o 25 horas, y el primero y el último del periodo pueden venir truncados.
    """
    variables = [c for c in (variables or [])] or [
        c for c in horaria.columns if c in V.CATALOGO]
    circular = [v for v in variables if v in V.CIRCULARES]
    continuas = [v for v in variables if v not in V.CIRCULARES]

    llaves = ["cvegeo", "ciudad", "municipio", "cve_mun", "calidad",
              "fecha_local"]
    g = horaria.groupby(llaves, sort=True)

    agg = {v: ["mean", "min", "max"] for v in continuas}
    d = g.agg(agg)
    d.columns = [f"{v}_{ {'mean': 'media', 'min': 'min', 'max': 'max'}[s] }"
                 for v, s in d.columns]
    d["n_horas"] = g.size()

    # La media circular del día; su mín/máx se omiten a propósito.
    for v in circular:
        ang = np.radians(horaria[v].to_numpy(dtype="float64"))
        aux = horaria[llaves].copy()
        aux["sx"], aux["cy"] = np.sin(ang), np.cos(ang)
        m = aux.groupby(llaves, sort=True)[["sx", "cy"]].mean()
        d[f"{v}_media"] = np.degrees(np.arctan2(m["sx"], m["cy"])) % 360

    return d.reset_index()
