"""
Temperatura MÍNIMA diaria por municipio: NSRDB vs ERA5-Land vs ERA5-single.

    conda run -n rs python -m copernicus.minimas
    conda run -n rs python -m copernicus.minimas --municipios Camargo Mier --alinear

Una fila por (municipio, día) y tres columnas de temperatura, sobre el MISMO
punto: el nodo NSRDB elegido para cada cabecera municipal
(`nodos_interes_municipios.csv`) y la celda ERA5 más cercana a esa coordenada.
Por omisión, los seis municipios de la frontera del Río Bravo, 2020–2025.

## El día es LOCAL, no UTC

Una mínima diaria calculada sobre el día UTC no es la mínima del día: en
Tamaulipas el corte de las 00 UTC cae a las 18 o 19 de la tarde anterior, así
que partiría la madrugada —justo donde está el mínimo— en dos días distintos.
Se agrega por día local.

Y para estos seis municipios eso importa el doble: **los seis están en la franja
fronteriza**, que conservó el horario de verano cuando el resto del estado lo
dejó en 2022 (DOF 2022-10-28). Su reloj es `America/Matamoros`, no
`America/Monterrey`, y en verano van una hora por delante del interior. El huso
se resuelve por municipio con `urbano.clima.agregacion.tz_de_municipio`.

## Los días incompletos se descartan — pero no todos duran 24 horas

Las series empiezan y terminan en horas UTC redondas, así que el primer y el
último día local se quedan a medias (6 h y 18 h). Un mínimo sobre medio día es
un número plausible y equivocado, así que esos se descartan.

El criterio NO es "tener 24 horas": como estos municipios conservan el horario
de verano, dos días al año duran **23 h** (marzo) y **25 h** (noviembre). Exigir
24 tiraría esos doce días del periodo —días completos, con todo su dato— y
encima sin avisar. Cada día se compara contra las horas que de verdad tiene en
su zona (`horas_esperadas`), y `n_horas` deja constancia de las que había.

## El desfase de una hora entre fuentes

El NSRDB etiqueta el inicio del intervalo horario y ERA5 el final (ver
`copernicus/comparar.py`). En la mínima DIARIA el efecto es pequeño —un mínimo
es robusto a desplazar la serie un paso—: medido en Camargo 2024, el RMSE baja
de 1.575 a 1.509 °C, un 4 %. Nada que ver con el 37 % del GHI horario.

Por eso `--alinear` es opcional y no el valor por omisión: en las variables
instantáneas el desajuste real es de media hora y restar una es una
aproximación, no una corrección exacta. El modo usado se imprime al generar la
tabla ("horas alineadas: SÍ/NO"), pero no viaja dentro del CSV: si guardas las
dos versiones, distínguelas por el nombre del archivo.
"""
from __future__ import annotations
import argparse
import os

import numpy as np
import pandas as pd

from copernicus import config as C

# Los seis municipios de la frontera del Río Bravo, por clave INEGI.
MUNICIPIOS_OMISION = ("Camargo", "Guerrero", "Mier", "Miguel Alemán",
                      "Nuevo Laredo", "Río Bravo")
ANIOS_OMISION = (2020, 2021, 2022, 2023, 2024, 2025)

FUENTES = {"nsrdb": None, "era5_land": "land", "era5_single": "single"}


def _horas_del_dia(fecha, tz: str) -> int:
    """
    Cuántas horas dura ese día en esa zona: 23, 24 o 25.

    No todos los días tienen 24 horas. La franja fronteriza conserva el horario
    de verano, así que dos días al año duran 23 h (marzo) y 25 h (noviembre).
    Exigir 24 descartaría esos doce días del periodo —días completos, con todo
    su dato— y encima en silencio.
    """
    import datetime as _dt
    # Las dos medianoches LOCALES, cada una localizada por separado. Sumar
    # `Timedelta(days=1)` a la primera no sirve: eso son 24 horas absolutas, así
    # que la resta daría siempre 24 y el día de cambio pasaría desapercibido.
    ini = pd.Timestamp(fecha, tz=tz)
    fin = pd.Timestamp(fecha + _dt.timedelta(days=1), tz=tz)
    return int((fin - ini).total_seconds() // 3600)


def _norm(s: str) -> str:
    """Minúsculas sin acentos: 'Miguel Alemán' y 'miguel aleman' son lo mismo."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def nodos_de(municipios=MUNICIPIOS_OMISION) -> pd.DataFrame:
    """
    El nodo NSRDB elegido para cada municipio pedido, con su coordenada.

    Sale de `nodos_interes_municipios.csv`, que es el mismo catálogo del que
    salen las láminas de `Results/.../nodos_de_interes/`: así la extracción usa
    exactamente el punto que ya está documentado en esas figuras.
    """
    n = pd.read_csv(C.CSV_NODOS, dtype={"cve_mun": str, "cvegeo": str})
    if municipios is None:
        return n
    objetivo = {_norm(m) for m in municipios}
    sel = n[n["municipio"].map(_norm).isin(objetivo)]
    faltan = objetivo - set(sel["municipio"].map(_norm))
    if faltan:
        raise ValueError(
            f"No encontré {sorted(faltan)} en {os.path.basename(C.CSV_NODOS)}. "
            f"Hay {len(n)} municipios; revisa la escritura exacta.")
    return sel.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Carga horaria
# --------------------------------------------------------------------------- #
def _nsrdb_horario(nodos: list[int], anios) -> pd.DataFrame:
    """
    Temperatura horaria del NSRDB para esos nodos, leída de los parquets del año.

    Se leen los parquets directamente y no por `urbano.clima.consulta`: aquel
    limita a `ANIOS_CLIMA` (2020–2024) y aquí hace falta 2025, que ya está
    descargado y consolidado.
    """
    partes = []
    for anio in anios:
        ruta = os.path.join(C.RAIZ, "Data", C.REGION, str(anio), "Finales",
                            "completo",
                            f"dataset_tamaulipas_completo_24h_{anio}.parquet")
        if not os.path.exists(ruta):
            raise FileNotFoundError(
                f"Falta el NSRDB de {anio}: {ruta}\nDescárgalo con "
                f"`python -m Utils.descarga_regiones --regiones tamaulipas "
                f"--anios {anio} --metadatos todos`.")
        partes.append(pd.read_parquet(
            ruta, columns=["nodo_id", "datetime", "temperature"],
            filters=[("nodo_id", "in", nodos)]))
    d = pd.concat(partes, ignore_index=True)
    # El parquet trae la marca sin zona, pero es UTC (verificado contra el
    # ángulo cenital solar). Declararlo explícitamente evita que el merge con
    # ERA5 —que sí trae zona— falle o, peor, desplace seis horas.
    d["datetime_utc"] = pd.to_datetime(d["datetime"], utc=True)
    return d[["nodo_id", "datetime_utc", "temperature"]]


def _era5_horario(producto: str, nodos: list[int]) -> pd.DataFrame:
    ruta = os.path.join(C.dir_series(producto), f"{producto}_completo.parquet")
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            f"Falta {ruta}. Corre antes:\n  python -m copernicus.extraer "
            f"--producto {producto} --anios 2020 2021 2022 2023 2024 2025 "
            f"--consolidar")
    d = pd.read_parquet(ruta, columns=["nodo_id", "datetime_utc", "temperature"])
    d = d[d["nodo_id"].isin(nodos)].copy()
    d["datetime_utc"] = pd.to_datetime(d["datetime_utc"], utc=True)
    return d


def horarias(municipios=MUNICIPIOS_OMISION, anios=ANIOS_OMISION,
             alinear: bool = False) -> pd.DataFrame:
    """Serie horaria de las tres fuentes en formato ancho, antes de agregar."""
    nod = nodos_de(municipios)
    ids = nod["nodo_id"].tolist()

    d = _nsrdb_horario(ids, anios).rename(columns={"temperature": "nsrdb"})
    for nombre, producto in FUENTES.items():
        if producto is None:
            continue
        e = _era5_horario(producto, ids).rename(columns={"temperature": nombre})
        if alinear:
            # Reetiquetado: el valor que ERA5 rotula 13:00 describe el intervalo
            # que el NSRDB rotula 12:00. Ver el docstring del módulo.
            e["datetime_utc"] -= pd.Timedelta(hours=1)
        d = d.merge(e, on=["nodo_id", "datetime_utc"], how="inner")

    d = d.merge(nod[["nodo_id", "cve_mun", "municipio", "latitude", "longitude",
                     "msnm"]], on="nodo_id", how="left")
    # Recorte al periodo pedido, en años UTC: ERA5 llega hasta 2025-12-31 23 UTC
    # y el NSRDB también, así que el merge interno ya los cuadra.
    return d.sort_values(["cve_mun", "datetime_utc"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Mínimas diarias
# --------------------------------------------------------------------------- #
def minimas_diarias(municipios=MUNICIPIOS_OMISION, anios=ANIOS_OMISION,
                    alinear: bool = False, solo_completos: bool = True,
                    horario: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Una fila por (municipio, día local) con las tres mínimas.

    Columnas: `cve_mun`, `municipio`, `nodo_id`, `latitude`, `longitude`,
    `msnm`, `tz`, `fecha_local`, `n_horas`, `horas_esperadas`, `completo`,
    `nsrdb`, `era5_land`, `era5_single`.
    """
    from urbano.clima.agregacion import tz_de_municipio

    d = horarias(municipios, anios, alinear) if horario is None else horario.copy()
    cols = [c for c in ("nsrdb", "era5_land", "era5_single") if c in d]

    # El día local se calcula POR MUNICIPIO: los seis de la frontera van en
    # America/Matamoros y el resto del estado en America/Monterrey, y en verano
    # no son el mismo día a la misma hora UTC.
    trozos = []
    for cve, g in d.groupby("cve_mun"):
        tz = tz_de_municipio(cve)
        g = g.copy()
        g["fecha_local"] = g["datetime_utc"].dt.tz_convert(tz).dt.date
        g["tz"] = tz
        trozos.append(g)
    d = pd.concat(trozos, ignore_index=True)

    llaves = ["cve_mun", "municipio", "nodo_id", "latitude", "longitude",
              "msnm", "tz", "fecha_local"]
    out = d.groupby(llaves, as_index=False).agg(
        n_horas=("datetime_utc", "size"),
        **{c: (c, "min") for c in cols})

    # Se compara contra las horas que ESE día tiene en ESA zona, no contra 24:
    # los días de cambio de horario duran 23 o 25 (ver `_horas_del_dia`).
    out["horas_esperadas"] = [
        _horas_del_dia(f, tz) for f, tz in zip(out["fecha_local"], out["tz"])]
    out["completo"] = out["n_horas"] == out["horas_esperadas"]
    if solo_completos:
        # Un mínimo sobre medio día es plausible y falso: los días de los
        # extremos se quedan a 18 y 6 horas por el desfase UTC→local.
        out = out[out["completo"]]

    return out.sort_values(["cve_mun", "fecha_local"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Métricas
# --------------------------------------------------------------------------- #
def metricas(m: pd.DataFrame, por="municipio") -> pd.DataFrame:
    """Sesgo, MAE, RMSE y correlación de cada ERA5 contra el NSRDB."""
    filas = []
    grupos = [("todos", m)] if por is None else list(m.groupby(por))
    for clave, g in grupos:
        for c in ("era5_land", "era5_single"):
            if c not in g:
                continue
            par = g[["nsrdb", c]].dropna()
            if len(par) < 2:
                continue
            dif = par[c] - par["nsrdb"]
            filas.append({
                (por or "grupo"): clave, "fuente": c, "n": len(par),
                "sesgo": round(float(dif.mean()), 3),
                "mae": round(float(dif.abs().mean()), 3),
                "rmse": round(float(np.sqrt((dif ** 2).mean())), 3),
                "corr": round(float(par[c].corr(par["nsrdb"])), 4),
            })
    return pd.DataFrame(filas)


def contraste_smn(m: pd.DataFrame) -> pd.DataFrame:
    """
    Las tres fuentes contra la mínima MEDIDA por las estaciones del SMN.

    Las tres columnas de la tabla son estimación: el NSRDB interpola MERRA-2 y
    ERA5 es reanálisis. Ninguna es un termómetro. Esta función cruza con la red
    convencional del SMN, que sí lo es — pero en estos seis municipios la red
    está casi vacía, así que el resultado es indicativo y nunca una validación.

    Devuelve una tabla vacía si no hay ningún día en común.
    """
    from smn import catalogo as CAT
    from smn import cobertura as K

    est = CAT.asignar()
    est = est[est["cve_mun_geo"].isin(m["cve_mun"].astype(str).str.zfill(3))]
    if est.empty:
        return pd.DataFrame()

    diario = K.cargar_diario()
    diario = diario[diario["clave"].isin(est["clave"])][
        ["clave", "fecha", "tmin_c"]]
    est_mun = est.set_index("clave")["cve_mun_geo"]
    diario["cve_mun"] = diario["clave"].map(est_mun)

    m = m.copy()
    m["cve_mun"] = m["cve_mun"].astype(str).str.zfill(3)
    m["fecha_local"] = pd.to_datetime(m["fecha_local"])
    j = m.merge(diario, left_on=["cve_mun", "fecha_local"],
                right_on=["cve_mun", "fecha"], how="inner")
    if j.empty:
        return pd.DataFrame()

    filas = []
    for (cve, clave), g in j.groupby(["cve_mun", "clave"]):
        for c in ("nsrdb", "era5_land", "era5_single"):
            dif = g[c] - g["tmin_c"]
            filas.append({
                "cve_mun": cve, "estacion": clave,
                "municipio": g["municipio"].iloc[0], "fuente": c, "n": len(g),
                "sesgo": round(float(dif.mean()), 2),
                "mae": round(float(dif.abs().mean()), 2),
                "rmse": round(float(np.sqrt((dif ** 2).mean())), 2),
                "corr": round(float(g[c].corr(g["tmin_c"])), 3),
            })
    return pd.DataFrame(filas)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--municipios", nargs="+", default=list(MUNICIPIOS_OMISION))
    ap.add_argument("--anios", nargs="+", type=int, default=list(ANIOS_OMISION))
    ap.add_argument("--alinear", action="store_true",
                    help="reetiqueta ERA5 una hora atrás antes de agregar")
    ap.add_argument("--con-parciales", action="store_true",
                    help="conserva los días incompletos de los extremos")
    ap.add_argument("--salida", default=os.path.join(
        C.RAIZ, "Results", "comparacion", "tmin_diaria_frontera.csv"))
    a = ap.parse_args()

    pd.set_option("display.width", 220)
    m = minimas_diarias(a.municipios, a.anios, alinear=a.alinear,
                        solo_completos=not a.con_parciales)

    print(f"\n{len(m):,} días · {m['municipio'].nunique()} municipios · "
          f"{m['fecha_local'].min()} a {m['fecha_local'].max()}")
    print(f"horas alineadas: {'SÍ' if a.alinear else 'NO'}  ·  "
          f"huso: {', '.join(sorted(m['tz'].unique()))}\n")

    print("Días por municipio:")
    print(m.groupby(["cve_mun", "municipio"])
          .agg(dias=("fecha_local", "size"),
               desde=("fecha_local", "min"), hasta=("fecha_local", "max"),
               tmin_nsrdb=("nsrdb", "mean"), tmin_land=("era5_land", "mean"),
               tmin_single=("era5_single", "mean")).round(2).to_string())

    print("\nERA5 respecto al NSRDB (mínima diaria, °C):")
    print(metricas(m).to_string(index=False))
    print("\nGlobal:")
    print(metricas(m, por=None).to_string(index=False))

    try:
        cs = contraste_smn(m)
    except Exception as e:                      # el SMN es opcional para esto
        cs = pd.DataFrame()
        print(f"\n[smn] no se pudo contrastar ({type(e).__name__}: {str(e)[:80]})")
    if len(cs):
        print("\nContraste contra la mínima MEDIDA por el SMN (indicativo):")
        print(cs.to_string(index=False))
        print("  ⚠ Las tres fuentes son estimación, no medición. En estos "
              "municipios la red del SMN\n    está casi vacía, así que esto "
              "orienta pero no valida.")

    os.makedirs(os.path.dirname(os.path.abspath(a.salida)), exist_ok=True)
    m.to_csv(a.salida, index=False)
    print(f"\n[csv] {a.salida}  ({len(m):,} filas)")
