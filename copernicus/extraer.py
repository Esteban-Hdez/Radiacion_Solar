"""
De NetCDF de ERA5 a series por nodo, en las mismas unidades que el NSRDB.

    conda run -n rs python -m copernicus.extraer --producto land --anios 2024 --meses 1

Lo que hace, en orden:

1. Abre el mes (uniendo los flujos `instant` y `accum` que el CDS separa).
2. Elige, para cada nodo, la celda más cercana —y anota a qué distancia quedó,
   porque esa distancia es parte del resultado: hasta ~19 km en la malla de
   0.25° y ~7 km en la de 0.1°.
3. Convierte a las unidades del NSRDB para que la comparación sea directa.

## La acumulación de la radiación

`ssrd` viene en J/m² acumulados, y **la ventana de acumulación no es la misma en
los dos productos**:

- **ERA5** (`single`): acumula sobre la hora anterior → `ssrd / 3600` es W/m².
- **ERA5-Land**: acumula **desde las 00 UTC del día**. Hay que diferenciar pasos
  consecutivos, salvo a las 01 UTC, donde el valor ya es la primera hora del
  día. El paso de las 00 UTC contiene el acumulado de las 24 h anteriores, así
  que al diferenciarlo contra las 23 UTC del día previo sale, correctamente, la
  última hora de ese día.

Aplicar la regla de `single` a `land` daría una irradiancia que crece a lo largo
del día: físicamente absurda, pero no evidentemente rota en una tabla.

Consecuencia práctica: la primera hora de cada archivo mensual de `land` no se
puede desacumular sin el último paso del mes anterior. Por eso se guarda también
`ssrd_acum` (el crudo) y `consolidar()` recalcula la irradiancia sobre la serie
completa, dejando un único hueco al principio de todo en vez de uno por mes.
"""
from __future__ import annotations
import argparse
import glob
import os

import numpy as np
import pandas as pd
import xarray as xr

from copernicus import config as C

# Tolerancia de irradiancia negativa admitida como redondeo (W/m²).
TOL_NEGATIVA = 1.0

# Nombres cortos con que ERA5 entrega cada variable.
RENOMBRE = {
    "t2m": "temperature", "d2m": "dew_point", "sp": "pressure",
    "u10": "u10", "v10": "v10", "ssrd": "ssrd_acum",
}


# --------------------------------------------------------------------------- #
# Lectura
# --------------------------------------------------------------------------- #
def abrir_mes(producto: str, anio: int, mes: int) -> xr.Dataset:
    """Une los NetCDF de un mes (`instant` + `accum`) en un solo Dataset."""
    patron = os.path.join(C.dir_nc(producto),
                          f"era5_{producto}_{anio}_{mes:02d}*.nc")
    archivos = sorted(glob.glob(patron))
    if not archivos:
        raise FileNotFoundError(
            f"No hay NetCDF para {producto} {anio}-{mes:02d}. Corre antes "
            f"`python -m copernicus.descarga --producto {producto} "
            f"--anios {anio} --meses {mes}`.")
    partes = [xr.open_dataset(a) for a in archivos]
    ds = xr.merge(partes, compat="override", join="outer")
    # El CDS usa `valid_time` en los productos nuevos y `time` en los viejos.
    if "valid_time" in ds.dims:
        ds = ds.rename({"valid_time": "time"})
    return ds.sortby("time")


def cargar_nodos(ruta: str | None = None) -> pd.DataFrame:
    """Los 43 nodos (uno por cabecera) con su clave municipal."""
    return pd.read_csv(ruta or C.CSV_NODOS,
                       dtype={"cve_mun": str, "cvegeo": str})


# --------------------------------------------------------------------------- #
# Selección de celda
# --------------------------------------------------------------------------- #
def _distancia_km(lat1, lon1, lat2, lon2) -> float:
    """Distancia great-circle, para reportar cuán lejos quedó la celda."""
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(2 * R * np.arcsin(np.sqrt(a)))


def _celda_valida(ds: xr.Dataset, lat: float, lon: float,
                  variable: str = "t2m", radio_max: int = 8):
    """
    Celda más cercana con datos.

    ERA5-Land solo cubre TIERRA: las celdas sobre mar son NaN. Un nodo costero
    puede caer en una, y devolver una serie de NaN sin avisar sería lo peor
    posible. Si la celda más cercana está vacía se busca en anillos crecientes
    la primera con datos, y se devuelve `fallback=True` para que quede
    registrado en la salida.
    """
    lats, lons = ds["latitude"].values, ds["longitude"].values
    i = int(np.abs(lats - lat).argmin())
    j = int(np.abs(lons - lon).argmin())

    def _tiene_datos(ii, jj) -> bool:
        v = ds[variable].isel(latitude=ii, longitude=jj)
        return bool(np.isfinite(v).any())

    if _tiene_datos(i, j):
        return i, j, False
    for r in range(1, radio_max + 1):
        candidatos = []
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if max(abs(di), abs(dj)) != r:
                    continue
                ii, jj = i + di, j + dj
                if 0 <= ii < len(lats) and 0 <= jj < len(lons) and _tiene_datos(ii, jj):
                    candidatos.append(
                        (_distancia_km(lat, lon, lats[ii], lons[jj]), ii, jj))
        if candidatos:
            _, ii, jj = min(candidatos)
            return ii, jj, True
    raise ValueError(
        f"No hay ninguna celda con datos a menos de {radio_max} celdas de "
        f"({lat}, {lon}). ¿Está el punto fuera del recorte descargado?")


# --------------------------------------------------------------------------- #
# Unidades y derivadas
# --------------------------------------------------------------------------- #
def _humedad_relativa(t_c, td_c):
    """
    HR (%) a partir de temperatura y punto de rocío, por Magnus-Tetens.

    NSRDB deriva su `relative_humidity` de T2M + QV2M + PS con la misma familia
    de fórmulas; ERA5 no publica humedad específica junto a estas variables,
    pero sí el punto de rocío, que lleva a lo mismo. Se documenta porque la HR
    NO es una medida en ninguna de las dos fuentes: es una derivada, y parte de
    la diferencia entre fuentes puede venir de la fórmula, no del dato.
    """
    a, b = 17.625, 243.04
    e = np.exp(a * td_c / (b + td_c))
    es = np.exp(a * t_c / (b + t_c))
    return np.clip(100.0 * e / es, 0, 100)


def _viento(u, v):
    """Velocidad (m/s) y dirección meteorológica (grados, de dónde sopla)."""
    return np.hypot(u, v), (270.0 - np.degrees(np.arctan2(v, u))) % 360.0


def desacumular(ssrd: pd.Series, horas: pd.Series, paso: str) -> pd.Series:
    """
    J/m² acumulados -> W/m² horarios. Ver el docstring del módulo.

    `ssrd` y `horas` deben venir ordenados en el tiempo y ser de un solo nodo.
    """
    if paso == "horario":                      # ERA5 single levels
        return ssrd / 3600.0
    if paso != "desde_00utc":
        raise ValueError(f"Paso de acumulación desconocido: {paso}")
    # A las 01 UTC el acumulado YA es la primera hora del día: restarle el paso
    # de las 00 (que trae las 24 h previas) daría un número negativo enorme.
    # Se devuelve Series, igual que la otra rama, para que quien la use no tenga
    # que saber por cuál pasó.
    dif = np.where(horas.to_numpy() == 1, ssrd.to_numpy(), ssrd.diff().to_numpy())
    w = pd.Series(dif / 3600.0, index=ssrd.index)

    # Restar dos acumulados casi iguales deja negativos del orden de 1e-4 W/m²:
    # ruido de coma flotante, no física. Se recortan a cero, pero un negativo
    # GRANDE significaría que la ventana de acumulación es otra, así que ahí sí
    # hay que enterarse en vez de taparlo.
    peor = w.min(skipna=True)
    if pd.notna(peor) and peor < -TOL_NEGATIVA:
        raise ValueError(
            f"Irradiancia de {peor:.3f} W/m² tras desacumular: demasiado "
            f"negativa para ser redondeo. Revisa `paso_acumulacion`.")
    return w.clip(lower=0.0)


# --------------------------------------------------------------------------- #
# Extracción
# --------------------------------------------------------------------------- #
def extraer_mes(producto: str, anio: int, mes: int,
                nodos: pd.DataFrame | None = None) -> pd.DataFrame:
    """Serie horaria de cada nodo para un mes, en unidades del NSRDB."""
    nodos = cargar_nodos() if nodos is None else nodos
    ds = abrir_mes(producto, anio, mes)
    paso = C.PRODUCTOS[producto]["paso_acumulacion"]
    lats, lons = ds["latitude"].values, ds["longitude"].values

    filas = []
    for _, n in nodos.iterrows():
        i, j, fallback = _celda_valida(ds, n["latitude"], n["longitude"])
        punto = ds.isel(latitude=i, longitude=j)
        df = punto[[v for v in RENOMBRE if v in punto]].to_dataframe().reset_index()
        df = df.rename(columns=RENOMBRE)
        df = df[["time"] + [c for c in RENOMBRE.values() if c in df.columns]]
        df = df.sort_values("time").reset_index(drop=True)

        df["temperature"] = df["temperature"] - 273.15       # K -> °C
        df["dew_point"] = df["dew_point"] - 273.15
        df["pressure"] = df["pressure"] / 100.0              # Pa -> mbar
        df["relative_humidity"] = _humedad_relativa(
            df["temperature"], df["dew_point"])
        df["wind_speed"], df["wind_direction"] = _viento(df["u10"], df["v10"])
        df["ghi"] = desacumular(df["ssrd_acum"], df["time"].dt.hour, paso)

        df.insert(0, "nodo_id", int(n["nodo_id"]))
        df.insert(1, "cve_mun", n["cve_mun"])
        df.insert(2, "municipio", n["municipio"])
        df["producto"] = producto
        df["celda_lat"] = float(lats[i])
        df["celda_lon"] = float(lons[j])
        df["dist_celda_km"] = round(
            _distancia_km(n["latitude"], n["longitude"], lats[i], lons[j]), 3)
        df["celda_fallback"] = fallback
        filas.append(df)

    ds.close()
    out = pd.concat(filas, ignore_index=True).rename(columns={"time": "datetime_utc"})
    # El CDS entrega UTC pero sin zona horaria. Se marca explícitamente: la
    # columna se llama `_utc` y debe poder cruzarse con el NSRDB, que sí la
    # trae con zona; si no, el merge falla o —peor— desplaza seis horas.
    out["datetime_utc"] = pd.to_datetime(out["datetime_utc"], utc=True)
    orden = ["nodo_id", "cve_mun", "municipio", "producto", "datetime_utc",
             "temperature", "relative_humidity", "dew_point", "pressure",
             "wind_speed", "wind_direction", "ghi", "ssrd_acum",
             "celda_lat", "celda_lon", "dist_celda_km", "celda_fallback"]
    return out[[c for c in orden if c in out.columns]]


def consolidar(producto: str, guardar: bool = True) -> pd.DataFrame:
    """
    Une todos los meses extraídos y RECALCULA la irradiancia.

    El recálculo importa: desacumular mes a mes deja sin dato la primera hora de
    cada archivo, porque le falta el último paso del mes anterior. Sobre la
    serie completa solo queda un hueco, al principio de todo.
    """
    patron = os.path.join(C.dir_series(producto), f"{producto}_*.parquet")
    partes = [pd.read_parquet(p) for p in sorted(glob.glob(patron))]
    if not partes:
        raise FileNotFoundError(f"No hay series extraídas en {C.dir_series(producto)}")
    df = pd.concat(partes, ignore_index=True)
    df = df.sort_values(["nodo_id", "datetime_utc"]).reset_index(drop=True)

    paso = C.PRODUCTOS[producto]["paso_acumulacion"]
    df["ghi"] = (df.groupby("nodo_id", group_keys=False)
                 .apply(lambda g: pd.Series(
                     desacumular(g["ssrd_acum"], g["datetime_utc"].dt.hour, paso),
                     index=g.index), include_groups=False))
    if guardar:
        os.makedirs(C.dir_series(producto), exist_ok=True)
        ruta = os.path.join(C.dir_series(producto), f"{producto}_completo.parquet")
        df.to_parquet(ruta, index=False)
        print(f"[series] {ruta}  ({len(df):,} filas)")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--producto", choices=list(C.PRODUCTOS), required=True)
    ap.add_argument("--anios", nargs="+", type=int, default=list(C.ANIOS))
    ap.add_argument("--meses", nargs="+", type=int, default=list(C.MESES))
    ap.add_argument("--consolidar", action="store_true")
    a = ap.parse_args()

    os.makedirs(C.dir_series(a.producto), exist_ok=True)
    for anio in a.anios:
        for mes in a.meses:
            df = extraer_mes(a.producto, anio, mes)
            ruta = os.path.join(C.dir_series(a.producto),
                                f"{a.producto}_{anio}_{mes:02d}.parquet")
            df.to_parquet(ruta, index=False)
            print(f"[series] {ruta}  ({len(df):,} filas · "
                  f"{df['nodo_id'].nunique()} nodos)")
    if a.consolidar:
        consolidar(a.producto)
