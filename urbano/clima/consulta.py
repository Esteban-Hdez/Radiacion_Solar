"""
Interfaz de consulta: pedir series climáticas por nombre, clave o ámbito.

Es la capa que hace usable todo lo anterior. Resuelve tres cosas que en
`agregacion.py` había que hacer a mano:

1. **Identificar la unidad** por clave INEGI *o* por nombre ("280410001",
   "Ciudad Victoria" o simplemente "victoria" resuelven a lo mismo).
2. **Acotar el periodo** con `desde` / `hasta`, cargando solo los años que hagan
   falta.
3. **Cambiar de ÁMBITO** sin rehacer los pesos: la misma consulta se puede pedir
   por localidad, por conglomerado urbano o para todo el estado urbano junto.

## Los ámbitos

| ámbito | unidades | qué es |
|---|---|---|
| `cabeceras` | 43 | las cabeceras municipales |
| `otras` | 20 | localidades urbanas que no son cabecera |
| `localidades` | 63 | todas las localidades urbanas |
| `conglomerados` | 57 | manchas conurbadas agrupadas (Tampico+Madero+Miramar+Altamira = 1) |
| `global` | 1 | todo lo urbano del estado como una sola serie |

Y por debajo de todos ellos está el **nodo suelto**: `serie(..., nodo=1737)` da
la serie cruda de un punto de la malla, sin promediar nada. Es lo que hay que
usar cuando la pregunta es "¿qué dice ESTE punto?" en vez de "¿qué dice esta
ciudad?".

Agrupar NO es promediar los promedios. El `peso` de `nodos_ciudades.csv` está
normalizado *dentro de cada localidad*, así que sumarlo entre localidades daría
más importancia a un pueblo de 1 km² que a Reynosa. Para agrupar se vuelve al
peso ABSOLUTO —`peso × área_urbana`, o sea km² de ciudad que el nodo cubre— se
suma por nodo, y se renormaliza sobre el grupo. Así el conglomerado de Tampico
queda dominado por Tampico y Ciudad Madero, como debe ser.
"""
from __future__ import annotations
import os
import unicodedata

import numpy as np
import pandas as pd

from urbano import config as C
from urbano.clima import agregacion as G
from urbano.clima import variables as V

AMBITOS = ("cabeceras", "otras", "localidades", "conglomerados", "global")


# --------------------------------------------------------------------------- #
# Catálogo y resolución de nombres
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    """Minúsculas sin acentos, para comparar nombres escritos de cualquier forma."""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def catalogo() -> pd.DataFrame:
    """
    Todas las unidades consultables, con su clave, nombre y cobertura.

    Es la tabla que hay que mirar para saber qué se puede pedir y con qué
    nombre. Se ordena por área descendente.
    """
    ciu = pd.read_csv(C.CSV_CIUDADES, dtype={"cvegeo": str, "cve_mun": str})
    res = pd.read_csv(C.CSV_RESUMEN, dtype={"cvegeo": str, "cve_mun": str})
    cat = ciu.merge(res[["cvegeo", "n_nodos", "n_nodos_dentro", "calidad"]],
                    on="cvegeo", how="left")
    cat["tipo"] = cat["es_cabecera"].map({True: "cabecera", False: "otra localidad"})
    cols = ["cvegeo", "ciudad", "municipio", "cve_mun", "tipo", "area_km2",
            "n_nodos", "n_nodos_dentro", "calidad", "nombre_conglomerado"]
    return cat[cols].sort_values("area_km2", ascending=False).reset_index(drop=True)


def resolver(ref: str, cat: pd.DataFrame | None = None) -> str:
    """
    Traduce una referencia libre a la clave `cvegeo` de una localidad.

    Orden de resolución, del más específico al más laxo:
      1. clave `cvegeo` exacta            -> "280410001"
      2. nombre exacto de la localidad    -> "Ciudad Victoria"
      3. nombre exacto del MUNICIPIO      -> "Victoria" (devuelve su cabecera)
      4. coincidencia parcial única       -> "matamoros"

    El paso 3 existe porque casi siempre uno piensa en el municipio: "victoria"
    a secas es ambiguo por texto (existe también "Guadalupe Victoria", en
    Abasolo), pero como nombre de municipio es único y su cabecera es la que se
    quería. Si queda ambigüedad, el error lista los candidatos en vez de elegir
    por su cuenta.
    """
    cat = catalogo() if cat is None else cat
    r = _norm(ref)

    exacta = cat[cat["cvegeo"] == str(ref).strip()]
    if len(exacta):
        return exacta["cvegeo"].iloc[0]

    n_ciudad = cat["ciudad"].map(_norm)
    if (n_ciudad == r).any():
        return cat.loc[n_ciudad == r, "cvegeo"].iloc[0]

    cab = cat[cat["tipo"] == "cabecera"]
    n_mun = cab["municipio"].map(_norm)
    if (n_mun == r).any():
        return cab.loc[n_mun == r, "cvegeo"].iloc[0]

    parcial = cat[n_ciudad.str.contains(r, regex=False)
                  | cat["municipio"].map(_norm).str.contains(r, regex=False)]
    if len(parcial) == 1:
        return parcial["cvegeo"].iloc[0]
    if len(parcial) > 1:
        opciones = "; ".join(f"{x.cvegeo} {x.ciudad} ({x.municipio})"
                             for x in parcial.itertuples())
        raise ValueError(f"'{ref}' es ambiguo. Candidatos: {opciones}")
    raise ValueError(
        f"No encuentro '{ref}'. Consulta `consulta.catalogo()` para ver las "
        f"{len(cat)} localidades disponibles.")


# --------------------------------------------------------------------------- #
# Pesos por ámbito
# --------------------------------------------------------------------------- #
def _reagrupar(pares: pd.DataFrame, areas: pd.Series, grupo: pd.Series,
               nombre: pd.Series) -> pd.DataFrame:
    """
    Recalcula los pesos para una agrupación de localidades (ver docstring arriba).

    `grupo` y `nombre` van indexados por `cvegeo`.
    """
    p = pares.copy()
    p["grupo"] = p["cvegeo"].map(grupo)
    p["nombre"] = p["cvegeo"].map(nombre)
    # Peso ABSOLUTO: km² de mancha urbana que ese nodo cubre de esa localidad.
    p["km2"] = p["peso"] * p["cvegeo"].map(areas)

    g = (p.groupby(["grupo", "nombre", "nodo_id"], as_index=False)
          .agg(km2=("km2", "sum"),
               dentro=("metodo", lambda s: (s == "dentro").any())))
    g["peso"] = g["km2"] / g.groupby("grupo")["km2"].transform("sum")

    # Metadatos del grupo: municipio de la localidad MAYOR (define el huso
    # horario) y calidad recalculada sobre los nodos interiores del grupo.
    mayor = (p.assign(area=p["cvegeo"].map(areas))
             .sort_values("area", ascending=False)
             .drop_duplicates("grupo")
             .set_index("grupo")[["municipio", "cve_mun"]])
    n_dentro = g[g["dentro"]].groupby("grupo")["nodo_id"].nunique()
    n_total = g.groupby("grupo")["nodo_id"].nunique()

    def _calidad(gr):
        k = int(n_dentro.get(gr, 0))
        return ("alta" if k >= C.MIN_NODOS_ALTA
                else "media" if k >= C.MIN_NODOS_MEDIA else "baja")

    g["municipio"] = g["grupo"].map(mayor["municipio"])
    g["cve_mun"] = g["grupo"].map(mayor["cve_mun"])
    g["calidad"] = g["grupo"].map(_calidad)
    g["n_nodos_ciudad"] = g["grupo"].map(n_total)
    return g.rename(columns={"grupo": "cvegeo", "nombre": "ciudad"})[
        ["nodo_id", "cvegeo", "ciudad", "municipio", "cve_mun", "peso",
         "calidad", "n_nodos_ciudad"]]


def _municipio_de_nodos(ids: list[int]) -> pd.DataFrame:
    """
    Municipio en el que cae cada nodo, por intersección espacial.

    Hace falta para el huso horario, y se resuelve con la geometría en vez de
    con `nodos_ciudades.csv` para que funcione con CUALQUIERA de los 4384 nodos,
    no solo con los 225 que tocan una mancha urbana. Un nodo mar adentro no cae
    en ningún municipio: se le asigna el huso del interior.
    """
    import geopandas as gpd
    from urbano.data import manchas as M
    from urbano.nodos import asignacion as A

    nodos = A.cargar_nodos()
    nodos = nodos[nodos["nodo_id"].isin(ids)]
    faltan = sorted(set(ids) - set(nodos["nodo_id"]))
    if faltan:
        raise ValueError(f"Estos nodos no existen en la malla: {faltan}")

    mun = M.municipios().rename(columns={"CVE_MUN": "cve_mun"})
    j = gpd.sjoin(nodos[["nodo_id", "geometry"]],
                  mun[["cve_mun", "municipio", "geometry"]],
                  how="left", predicate="within")
    j = j.drop_duplicates("nodo_id")[["nodo_id", "cve_mun", "municipio"]]
    j["cve_mun"] = j["cve_mun"].fillna("041")          # fuera del estado / mar
    j["municipio"] = j["municipio"].fillna("(fuera de Tamaulipas)")
    return j


def pesos_nodo(nodos) -> pd.DataFrame:
    """
    Tabla de pesos para nodos SUELTOS: cada nodo es su propia unidad, peso 1.

    Se devuelve con la misma forma que `pesos()` para que el resto del pipeline
    no tenga que saber que esto es un caso especial. `calidad` vale "nodo": no
    hay agregación espacial, así que la bandera de cobertura de ciudad no aplica
    —y ponerle "alta" sería mentir.
    """
    ids = [int(n) for n in ([nodos] if isinstance(nodos, (int, np.integer))
                            else nodos)]
    if not ids:
        raise ValueError("`nodo` no puede ir vacío.")
    if len(set(ids)) != len(ids):
        raise ValueError(f"Hay nodos repetidos en {ids}.")

    muni = _municipio_de_nodos(ids).set_index("nodo_id")
    return pd.DataFrame({
        "nodo_id": ids,
        "cvegeo": [f"nodo-{i}" for i in ids],
        "ciudad": [f"nodo {i}" for i in ids],
        "municipio": [muni.loc[i, "municipio"] for i in ids],
        "cve_mun": [muni.loc[i, "cve_mun"] for i in ids],
        "peso": 1.0,
        "calidad": "nodo",
        "n_nodos_ciudad": 1,
    })


def catalogo_nodos(ciudad=None) -> pd.DataFrame:
    """
    Los nodos asignados a ciudades, con lo necesario para elegir uno.

    Sin argumento devuelve los 225; con `ciudad` (referencia libre) solo los de
    esa localidad, ordenados por peso descendente — el primero es el que más
    ciudad cubre.
    """
    pares = pd.read_csv(C.CSV_NODOS_CIUDADES,
                        dtype={"cvegeo": str, "cve_mun": str})
    meta = pd.read_csv(C.META_NODOS)[["nodo_id", "latitude", "longitude", "msnm"]]
    t = pares.merge(meta, on="nodo_id", how="left")
    if ciudad is not None:
        t = t[t["cvegeo"] == resolver(ciudad)]
    cols = ["nodo_id", "cvegeo", "ciudad", "municipio", "latitude", "longitude",
            "msnm", "metodo", "peso", "calidad"]
    return t[cols].sort_values(["cvegeo", "peso"],
                              ascending=[True, False]).reset_index(drop=True)


def nodos_interes() -> pd.DataFrame:
    """Los 12 nodos señalados a mano sobre el panel (uno por ciudad grande)."""
    ruta = os.path.join(C.DIR_SALIDA_DATOS, "nodos_interes.csv")
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"Falta {ruta}.")
    return pd.read_csv(ruta, dtype={"cvegeo": str, "cve_mun": str})


def pesos(ambito: str = "localidades", ciudades=None) -> pd.DataFrame:
    """
    Tabla nodo↔unidad con los pesos del ámbito pedido.

    `ciudades` (lista de referencias libres) acota a esas localidades; es
    incompatible con los ámbitos agrupados, que definen ellos mismos sus
    unidades.
    """
    if ambito not in AMBITOS:
        raise ValueError(f"Ámbito '{ambito}' desconocido. Opciones: {AMBITOS}")
    pares = pd.read_csv(C.CSV_NODOS_CIUDADES,
                        dtype={"cvegeo": str, "cve_mun": str})
    ciu = pd.read_csv(C.CSV_CIUDADES, dtype={"cvegeo": str, "cve_mun": str})
    areas = ciu.set_index("cvegeo")["area_km2"]

    if ciudades is not None:
        if ambito in ("conglomerados", "global"):
            raise ValueError(
                f"`ciudades` no se combina con el ámbito '{ambito}', que define "
                "sus propias unidades. Usa ambito='localidades'.")
        cat = catalogo()
        claves = [resolver(c, cat) for c in
                  ([ciudades] if isinstance(ciudades, str) else ciudades)]
        return pares[pares["cvegeo"].isin(claves)].reset_index(drop=True)

    if ambito == "cabeceras":
        return pares[pares["es_cabecera"]].reset_index(drop=True)
    if ambito == "otras":
        return pares[~pares["es_cabecera"]].reset_index(drop=True)
    if ambito == "localidades":
        return pares
    if ambito == "conglomerados":
        return _reagrupar(pares, areas,
                          ciu.set_index("cvegeo")["conglomerado"].astype(str),
                          ciu.set_index("cvegeo")["nombre_conglomerado"])
    # global
    idx = ciu.set_index("cvegeo")
    return _reagrupar(pares, areas,
                      pd.Series("TAM", index=idx.index),
                      pd.Series("Tamaulipas urbano", index=idx.index))


# --------------------------------------------------------------------------- #
# Consulta
# --------------------------------------------------------------------------- #
def _anios(desde, hasta, disponibles=C.ANIOS_CLIMA) -> list[int]:
    """
    Años que hay que abrir para cubrir [desde, hasta] en hora LOCAL.

    Se añade el año siguiente al del final: las últimas horas del 31 de
    diciembre local caen en el archivo del año siguiente (local = UTC−6), y sin
    él ese día saldría truncado.
    """
    if desde is None and hasta is None:
        return list(disponibles)
    a = pd.Timestamp(desde).year if desde is not None else min(disponibles)
    b = pd.Timestamp(hasta).year if hasta is not None else max(disponibles)
    anios = [x for x in disponibles if a <= x <= b + 1]
    if not anios:
        # Sin esto se seguiría hasta un `pd.concat([])` con un
        # "No objects to concatenate" que no dice nada del problema real.
        raise ValueError(
            f"El rango {desde} → {hasta} no cae dentro de los años "
            f"disponibles {tuple(disponibles)}.")
    return anios


def serie(variables=V.POR_OMISION, ciudad=None, ambito: str = "localidades",
          desde=None, hasta=None, frecuencia: str = "hora",
          ponderar: bool = True, nodo=None) -> pd.DataFrame:
    """
    La consulta principal.

    Parameters
    ----------
    variables : lista de nombres del catálogo (`urbano.clima.variables`).
    nodo : id de nodo NSRDB, o lista de ids. Devuelve la serie CRUDA de ese
        punto de la malla, sin promediar nada. Manda sobre `ciudad` y `ambito`.
    ciudad : referencia libre (clave, nombre de localidad o de municipio), o
        lista de ellas. Manda sobre `ambito`.
    ambito : uno de AMBITOS. Se ignora si se pasa `nodo` o `ciudad`.
    desde, hasta : fechas inclusivas, en hora LOCAL. Cualquier cosa que entienda
        `pd.Timestamp` ("2024-06-01", date, Timestamp). `None` = sin límite.
    frecuencia : "hora" para la serie horaria, "dia" para media/mín/máx diarios.
    ponderar : False para el promedio simple entre nodos. No aplica con `nodo`
        (un solo nodo no se promedia con nada).

    Examples
    --------
    >>> serie(["temperature"], ciudad="victoria", desde="2024-06-01",
    ...       hasta="2024-06-30", frecuencia="dia")
    >>> serie(["temperature"], nodo=1737, frecuencia="dia")
    >>> serie(["ghi"], ambito="conglomerados", desde="2024-01-01")
    >>> serie(["temperature", "relative_humidity"], ambito="global")
    """
    if frecuencia not in ("hora", "dia"):
        raise ValueError("`frecuencia` debe ser 'hora' o 'dia'")
    # Se compara con las fechas completas, no con el año: 2024-12-31 → 2024-01-01
    # está al revés aunque ambos extremos caigan en el mismo año.
    if desde is not None and hasta is not None:
        if pd.Timestamp(desde) > pd.Timestamp(hasta):
            raise ValueError(
                f"El rango está al revés: desde={desde} > hasta={hasta}")
    variables = V.validar(variables)
    if nodo is not None:
        if ciudad is not None:
            raise ValueError(
                "`nodo` y `ciudad` son excluyentes: uno pide un punto de la "
                "malla y el otro un promedio de ciudad. Elige uno.")
        if not ponderar:
            raise ValueError(
                "`ponderar=False` no significa nada con `nodo`: un solo nodo no "
                "se promedia con ningún otro.")
        w = pesos_nodo(nodo)
    else:
        w = pesos(ambito, ciudades=ciudad)
    h = G.serie_horaria(variables, anios=_anios(desde, hasta), pesos=w,
                        ponderar=ponderar)

    if desde is not None:
        h = h[pd.to_datetime(h["fecha_local"]) >= pd.Timestamp(desde)]
    if hasta is not None:
        h = h[pd.to_datetime(h["fecha_local"]) <= pd.Timestamp(hasta)]
    h = h.reset_index(drop=True)
    if h.empty:
        raise ValueError(
            f"El rango {desde} → {hasta} no dejó ninguna hora. Los años "
            f"disponibles son {tuple(C.ANIOS_CLIMA)}.")

    return h if frecuencia == "hora" else G.resumen_diario(h, variables)


if __name__ == "__main__":
    cat = catalogo()
    print(f"{len(cat)} localidades urbanas consultables\n")
    print(cat.head(15).to_string(index=False))
    print("\nResolución de nombres:")
    for ref in ["280410001", "Ciudad Victoria", "victoria", "matamoros",
                "san nicolas"]:
        print(f"  {ref!r:>18} -> {resolver(ref, cat)}")
    print("\nUnidades por ámbito:")
    for a in AMBITOS:
        print(f"  {a:15s} {pesos(a)['cvegeo'].nunique():3d} unidades")
