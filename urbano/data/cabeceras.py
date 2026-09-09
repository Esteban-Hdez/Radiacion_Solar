"""
Qué localidad es la CABECERA de cada municipio, según el INEGI.

Por qué existe este módulo: el Marco Geoestadístico **no** trae ese dato. La
convención es que la localidad `0001` de un municipio es su cabecera, y durante
un tiempo el proyecto la dio por buena. Es falsa en Tamaulipas para **Gómez
Farías** (011): su `0001` es *Loma Alta (Loma Alta de Gómez Farías)* —la
localidad más poblada— pero la cabecera es *Gómez Farías*, la `0036`. Es el
único caso de los 43, y basta uno para que el panel de cabeceras mienta.

El dato bueno está en el **Catálogo Único de Claves de Áreas Geoestadísticas**
(AGEEML), en su tabla de municipios: columnas `CVE_CAB` y `NOM_CAB`. De ahí se
extrae una tabla de 43 filas que SÍ se versiona, para que el pipeline no dependa
de la red ni de que el INEGI conserve la URL.

    conda run -n rs python -m urbano.data.cabeceras          # usa lo versionado
    conda run -n rs python -m urbano.data.cabeceras --bajar  # re-descarga
"""
from __future__ import annotations
import io
import os
import zipfile

import pandas as pd
import requests

from urbano import config as C

URL_AGEEML_MUNICIPIOS = (
    "https://www.inegi.org.mx/contenidos/app/ageeml/catun_municipio.zip")
ZIP_CACHE = os.path.join(C.DIR_CACHE, "ageeml_catun_municipio.zip")
CSV = os.path.join(C.RAIZ, "Data", C.REGION, "cabeceras_inegi.csv")


def descargar(forzar: bool = False) -> str:
    """Baja el catálogo de municipios del AGEEML a `cache/` (~0.5 MB)."""
    os.makedirs(C.DIR_CACHE, exist_ok=True)
    if os.path.exists(ZIP_CACHE) and not forzar:
        return ZIP_CACHE
    r = requests.get(URL_AGEEML_MUNICIPIOS, timeout=180,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    if len(r.content) < 100_000:
        raise RuntimeError(
            f"La descarga trajo solo {len(r.content)} bytes. Revisa "
            f"{URL_AGEEML_MUNICIPIOS} o baja el ZIP a mano a {ZIP_CACHE}.")
    with open(ZIP_CACHE, "wb") as f:
        f.write(r.content)
    return ZIP_CACHE


def _del_catalogo() -> pd.DataFrame:
    """Extrae las 43 filas de Tamaulipas del ZIP del AGEEML."""
    with zipfile.ZipFile(descargar()) as z:
        # El ZIP trae el mismo contenido en varios formatos; el CSV en UTF-8 es
        # el único que se lee sin adivinar codificación.
        nombre = next(i.filename for i in z.infolist()
                      if i.filename.endswith("_utf8.csv"))
        cat = pd.read_csv(io.BytesIO(z.read(nombre)), dtype=str)
    t = cat[cat["CVE_ENT"] == C.CVE_ENT]
    if len(t) != 43:
        raise RuntimeError(
            f"El catálogo trae {len(t)} municipios para la entidad "
            f"{C.CVE_ENT}; se esperaban 43.")
    return (t[["CVE_MUN", "NOM_MUN", "CVE_CAB", "NOM_CAB"]]
            .rename(columns={"CVE_MUN": "cve_mun", "NOM_MUN": "municipio",
                             "CVE_CAB": "cve_loc_cabecera",
                             "NOM_CAB": "nombre_cabecera"})
            .sort_values("cve_mun").reset_index(drop=True))


def tabla(refrescar: bool = False) -> pd.DataFrame:
    """
    Las 43 cabeceras: `cve_mun`, `municipio`, `cve_loc_cabecera`, `nombre_cabecera`.

    Lee el CSV versionado; solo toca la red si no existe o si se pide
    `refrescar`. Así el pipeline funciona sin conexión y el dato queda fijado en
    el repo, que es lo que se quiere de una tabla de 43 filas que casi nunca
    cambia.
    """
    if os.path.exists(CSV) and not refrescar:
        return pd.read_csv(CSV, dtype=str)
    t = _del_catalogo()
    os.makedirs(os.path.dirname(CSV), exist_ok=True)
    t.to_csv(CSV, index=False)
    return t


def mapa_cabeceras(refrescar: bool = False) -> dict[str, str]:
    """`{cve_mun: cve_loc de su cabecera}`."""
    t = tabla(refrescar)
    return dict(zip(t["cve_mun"], t["cve_loc_cabecera"]))


if __name__ == "__main__":
    import sys
    t = tabla(refrescar="--bajar" in sys.argv)
    print(f"{CSV}  ({len(t)} municipios)")
    excepciones = t[t["cve_loc_cabecera"] != "0001"]
    print(f"\nCabeceras que NO son la localidad 0001: {len(excepciones)}")
    print(excepciones.to_string(index=False) if len(excepciones) else "(ninguna)")
