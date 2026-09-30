"""
Series de tiempo comparadas: NSRDB frente a ERA5, en los mismos 43 nodos.

    from copernicus.graficas import comparar_series
    comparar_series("ghi", lugares="victoria", desde="2024-06-01", hasta="2024-06-07")

Todo es opcional menos la variable. Los filtros son de tiempo (`desde`/`hasta`,
`horas`, `meses`), de lugar (`lugares`, uno o varios) y de fuente (`fuentes`);
los textos (`titulo`, `subtitulo`, `etiqueta_x`, `etiqueta_y`, `nota`) se
autogeneran si no se pasan y se quitan pasando `""`.

## Color = FUENTE, faceta = LUGAR

Es la decisión de diseño que gobierna el módulo. Comparar fuentes es el objetivo,
así que la fuente tiene que ser reconocible de un vistazo y ser SIEMPRE del mismo
color: NSRDB azul, ERA5-Land naranja, ERA5-single verde-agua. Si el color se
repartiera entre lugares, añadir un municipio repintaría los demás y dos gráficas
del mismo cuaderno ya no se podrían leer juntas.

De ahí que varios lugares vayan a paneles separados (small multiples) en vez de a
más colores sobre los mismos ejes: tres fuentes × cinco municipios en un solo eje
son quince líneas superpuestas, ilegibles. `facetas=False` fuerza el eje único
cuando de verdad se quieren encimadas.

## Los periodos NO coinciden

El NSRDB de este repo llega a **2024** y ERA5 se descargó hasta **2025**. Pedir
2025 no es un error: se dibuja ERA5 y se anota en el pie que el NSRDB no cubre
ese tramo. Callarlo haría leer "el NSRDB cayó a cero" donde solo falta el dato.

## Lo que no es comparable aunque se pueda graficar

`wind_speed` y `wind_direction` están a 10 m en ERA5 y a 2 m en el NSRDB, y la
`relative_humidity` la derivan las dos con fórmulas distintas. Se grafican igual
—es información— pero el pie de la figura lo dice, porque la diferencia que se ve
ahí no es error del reanálisis.

## La dirección del viento no se promedia sumando

Promediar 350° y 10° da 180°, exactamente el sur cuando la respuesta es el norte.
Al agregar a día o mes, `wind_direction` se promedia como vector unitario.
"""
from __future__ import annotations
import os
import warnings

import numpy as np
import pandas as pd

from copernicus import config as C
from copernicus.comparar import NO_COMPARABLES

# --------------------------------------------------------------------------- #
# Fuentes y color
# --------------------------------------------------------------------------- #
# El nombre visible de cada fuente y el producto de `config.PRODUCTOS` del que
# sale. NSRDB no es un producto de ERA5: se lee por `urbano.clima`.
FUENTES = {
    "NSRDB": None,
    "ERA5-Land": "land",
    "ERA5-single": "single",
}

# Slots 1-3 de la paleta categórica de referencia, en orden fijo. Los tres
# primeros son los únicos que validan todos los pares entre sí (CVD ΔE 9.2 en
# claro / 9.4 en oscuro), que es lo que hace falta aquí: las tres líneas se
# cruzan constantemente, así que cualquier par puede quedar adyacente.
COLOR = {
    "NSRDB": "#2a78d6",        # azul
    "ERA5-Land": "#eb6834",    # naranja
    "ERA5-single": "#1baf7a",  # verde-agua
}

# El NSRDB es la referencia contra la que se mide: va más grueso y por encima.
ANCHO = {"NSRDB": 2.2, "ERA5-Land": 1.6, "ERA5-single": 1.6}
ORDEN_Z = {"NSRDB": 3, "ERA5-Land": 2, "ERA5-single": 2}

FRECUENCIAS = {"hora": None, "dia": "D", "mes": "MS"}
AGREGACIONES = ("media", "max", "min", "suma")


# --------------------------------------------------------------------------- #
# Lugares
# --------------------------------------------------------------------------- #
def catalogo_lugares() -> pd.DataFrame:
    """Los 43 nodos disponibles, con su municipio y su id."""
    n = pd.read_csv(C.CSV_NODOS, dtype={"cve_mun": str, "cvegeo": str})
    return n[["nodo_id", "cve_mun", "municipio", "latitude", "longitude",
              "msnm"]].sort_values("municipio").reset_index(drop=True)


def _norm(s: str) -> str:
    """Minúsculas sin acentos: 'Güémez', 'guemez' y 'GUEMEZ' son lo mismo."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def resolver_lugares(lugares=None) -> pd.DataFrame:
    """
    Traduce lo que se pida a filas del catálogo de nodos.

    Acepta un `nodo_id` (int), un nombre de municipio (str, parcial y sin
    acentos vale), o una lista mezclando ambos. `None` devuelve los 43.

    Se resuelve contra el catálogo en vez de aceptar el texto tal cual porque un
    nombre mal escrito debe fallar aquí, con la lista de candidatos delante, y no
    quince líneas después con una gráfica vacía.
    """
    cat = catalogo_lugares()
    if lugares is None:
        return cat
    if isinstance(lugares, (str, int, np.integer)):
        lugares = [lugares]

    filas, faltan = [], []
    for ref in lugares:
        if isinstance(ref, (int, np.integer)) or str(ref).isdigit():
            m = cat[cat["nodo_id"] == int(ref)]
        else:
            objetivo = _norm(ref)
            m = cat[cat["municipio"].map(_norm) == objetivo]
            if m.empty:                       # coincidencia parcial única
                m = cat[cat["municipio"].map(_norm).str.contains(objetivo,
                                                                regex=False)]
                if len(m) > 1:
                    raise ValueError(
                        f"'{ref}' es ambiguo: {sorted(m['municipio'])}. "
                        "Escríbelo completo o usa el nodo_id.")
        if m.empty:
            faltan.append(ref)
        else:
            filas.append(m)
    if faltan:
        raise ValueError(
            f"No encontré {faltan}. Los municipios disponibles están en "
            f"`catalogo_lugares()`; hay {len(cat)}.")
    return (pd.concat(filas).drop_duplicates("nodo_id")
            .reset_index(drop=True))


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #
def _cargar_era5(producto: str, nodos: list[int], variable: str) -> pd.DataFrame:
    """Una columna del parquet consolidado de un producto, para unos nodos."""
    ruta = os.path.join(C.dir_series(producto), f"{producto}_completo.parquet")
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            f"Falta {ruta}. Corre antes:\n"
            f"  python -m copernicus.extraer --producto {producto} "
            f"--anios 2020 2021 2022 2023 2024 2025 --consolidar")
    # Se leen solo las columnas necesarias: el consolidado son 2.3 M filas y
    # 17 columnas, y de aquí sale una sola variable.
    d = pd.read_parquet(ruta, columns=["nodo_id", "municipio", "datetime_utc",
                                       variable])
    return d[d["nodo_id"].isin(nodos)]


def _recorte_nsrdb(desde, hasta):
    """
    El rango pedido, recortado a los años que el NSRDB sí tiene.

    Devuelve `(desde, hasta, aviso)`, o `None` si no hay solapamiento. Existe
    porque ERA5 llega a 2025 y el NSRDB de este repo termina en 2024: pedir un
    tramo de 2025 es legítimo —se quiere ver ERA5— y debe dibujar lo que haya en
    vez de reventar con "el rango no cae dentro de los años disponibles".
    """
    from urbano import config as UC
    a0, a1 = min(UC.ANIOS_CLIMA), max(UC.ANIOS_CLIMA)
    lo = pd.Timestamp(desde) if desde is not None else pd.Timestamp(f"{a0}-01-01")
    hi = pd.Timestamp(hasta) if hasta is not None else pd.Timestamp(f"{a1}-12-31")
    lo_ok, hi_ok = max(lo, pd.Timestamp(f"{a0}-01-01")), min(hi, pd.Timestamp(f"{a1}-12-31"))
    if lo_ok > hi_ok:
        return None
    aviso = (f"El NSRDB solo cubre {a0}–{a1}: se recortó a "
             f"{lo_ok:%Y-%m-%d}..{hi_ok:%Y-%m-%d}." if (lo_ok, hi_ok) != (lo, hi)
             else "")
    return lo_ok.strftime("%Y-%m-%d"), hi_ok.strftime("%Y-%m-%d"), aviso


def _cargar_nsrdb(nodos: list[int], variable: str,
                  desde=None, hasta=None) -> pd.DataFrame:
    """La misma variable del NSRDB, por `urbano.clima`."""
    from urbano.clima import consulta as Q
    h = Q.serie([variable], nodo=nodos, desde=desde, hasta=hasta)
    h = h.rename(columns={"hora_local": "datetime_local"})
    h["nodo_id"] = h["ciudad"].str.removeprefix("nodo ").astype(int)
    return h[["nodo_id", "municipio", "datetime_utc", "datetime_local", variable]]


def cargar(variable: str = "ghi", lugares=None, desde=None, hasta=None,
           fuentes=tuple(FUENTES)) -> pd.DataFrame:
    """
    Tabla larga `(fuente, nodo_id, municipio, datetime_utc, valor)`.

    Es la entrada de `comparar_series`, y se expone aparte para poder pedirla una
    vez y reutilizarla: cargar el NSRDB de seis años tarda, y dibujar cinco
    variantes de la misma gráfica no debería pagarlo cinco veces
    (`comparar_series(..., datos=d)`).

    `desde`/`hasta` son inclusivos y se interpretan en hora LOCAL, como en
    `urbano.clima.consulta.serie`, para que un rango escrito a mano signifique lo
    que uno espera. La columna `datetime_local` viene del NSRDB y se propaga a
    ERA5 por el mismo nodo.
    """
    from urbano.clima import variables as V
    if variable not in V.CATALOGO:
        raise ValueError(f"Variable desconocida: '{variable}'. "
                         f"Disponibles: {sorted(V.CATALOGO)}")
    fuentes = [fuentes] if isinstance(fuentes, str) else list(fuentes)
    desconocidas = [f for f in fuentes if f not in FUENTES]
    if desconocidas:
        raise ValueError(f"Fuentes desconocidas: {desconocidas}. "
                         f"Disponibles: {list(FUENTES)}")

    if desde is not None and hasta is not None and \
            pd.Timestamp(desde) > pd.Timestamp(hasta):
        raise ValueError(f"El rango está al revés: desde={desde} > hasta={hasta}")

    nodos_df = resolver_lugares(lugares)
    nodos = nodos_df["nodo_id"].tolist()
    partes = []

    recorte = _recorte_nsrdb(desde, hasta)
    if recorte is None:
        # Todo el tramo pedido cae fuera del NSRDB (típicamente 2025). No es un
        # error: se sigue con ERA5 y se avisa, en vez de devolver nada.
        if "NSRDB" in fuentes:
            warnings.warn(
                "El rango pedido está fuera de los años del NSRDB; la gráfica "
                "solo llevará ERA5.")
            fuentes = [f for f in fuentes if f != "NSRDB"]
    else:
        n_desde, n_hasta, aviso = recorte
        if aviso:
            warnings.warn(aviso)
        try:
            n = _cargar_nsrdb(nodos, variable, n_desde, n_hasta)
            if "NSRDB" in fuentes:
                partes.append(n.assign(fuente="NSRDB")
                              .rename(columns={variable: "valor"}))
        except Exception as e:
            if "NSRDB" in fuentes:
                raise
            warnings.warn(f"No se pudo leer el NSRDB ({type(e).__name__}): "
                          f"{str(e)[:120]}")

    for f in fuentes:
        producto = FUENTES[f]
        if producto is None:
            continue
        e = _cargar_era5(producto, nodos, variable)
        e = e.assign(fuente=f).rename(columns={variable: "valor"})
        partes.append(e)

    if not partes:
        raise ValueError("No quedó ninguna fuente que cargar.")
    d = pd.concat(partes, ignore_index=True)
    d["datetime_utc"] = pd.to_datetime(d["datetime_utc"], utc=True)

    # La hora local se calcula aquí para TODAS las fuentes por igual, en vez de
    # heredarla del NSRDB: ERA5 llega a 2025, donde el NSRDB no tiene filas, y un
    # merge dejaría esas horas sin reloj local —y el filtro por fecha las
    # tiraría—.
    #
    # La conversión es POR MUNICIPIO, no con una zona única: los 10 municipios
    # de la franja fronteriza mantuvieron el horario estacional cuando el resto
    # del estado lo dejó (DOF 2022-10-28), así que Reynosa y Victoria no van a
    # la misma hora local en verano. Con una zona sola, el NSRDB de un nodo
    # fronterizo perdía la última hora del rango y la gráfica anunciaba un hueco
    # que no existía.
    from urbano.clima.agregacion import tz_de_municipio
    cve = dict(zip(nodos_df["nodo_id"], nodos_df["cve_mun"]))
    d["datetime_local"] = pd.NaT
    for nodo, sub in d.groupby("nodo_id"):
        tz = tz_de_municipio(cve[nodo])
        d.loc[sub.index, "datetime_local"] = (
            sub["datetime_utc"].dt.tz_convert(tz).dt.tz_localize(None))
    d["datetime_local"] = pd.to_datetime(d["datetime_local"])

    # El recorte se repite aquí porque ERA5 no pasó por el filtro de `serie()`,
    # y porque ERA5 llega a 2025 mientras el NSRDB termina en 2024: sin esto,
    # pedir "2024" dibujaría ERA5 hasta diciembre de 2025.
    if desde is not None:
        d = d[d["datetime_local"] >= pd.Timestamp(desde)]
    if hasta is not None:
        # `hasta` es inclusivo y suele escribirse como día suelto ("2024-06-30"),
        # que como Timestamp son las 00:00: se extiende al final de ese día.
        fin = pd.Timestamp(hasta)
        if fin == fin.normalize():
            fin += pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        d = d[d["datetime_local"] <= fin]

    d["variable"] = variable
    return d.sort_values(["fuente", "nodo_id", "datetime_utc"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Filtros y agregación
# --------------------------------------------------------------------------- #
def _media_circular(x) -> float:
    """Media de ángulos como vector unitario. Ver el docstring del módulo."""
    r = np.radians(np.asarray(x, dtype=float))
    r = r[np.isfinite(r)]
    if r.size == 0:
        return np.nan
    return float(np.degrees(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360)


def _filtrar(d: pd.DataFrame, horas=None, meses=None,
             tz: str = "local") -> pd.DataFrame:
    """Aplica los filtros de hora y mes sobre el reloj elegido."""
    col = "datetime_local" if tz == "local" else "datetime_utc"
    if horas is not None:
        h = d[col].dt.hour
        if isinstance(horas, tuple) and len(horas) == 2:
            d = d[h.between(horas[0], horas[1])]
        else:
            d = d[h.isin(list(np.atleast_1d(horas)))]
    if meses is not None:
        d = d[d[col].dt.month.isin(list(np.atleast_1d(meses)))]
    return d


def _agregar(d: pd.DataFrame, frecuencia: str, agregacion: str,
             variable: str, tz: str) -> pd.DataFrame:
    """Agrega a día o mes. En `hora` no toca nada."""
    from urbano.clima import variables as V
    if frecuencia not in FRECUENCIAS:
        raise ValueError(f"`frecuencia` debe ser una de {list(FRECUENCIAS)}")
    regla = FRECUENCIAS[frecuencia]
    if regla is None:
        return d
    if agregacion not in AGREGACIONES:
        raise ValueError(f"`agregacion` debe ser una de {AGREGACIONES}")

    col = "datetime_local" if tz == "local" else "datetime_utc"
    circular = V.CATALOGO[variable].tipo == "circular"
    if circular and agregacion != "media":
        raise ValueError(
            f"'{variable}' es circular: solo 'media' tiene sentido "
            "(el máximo de un ángulo no significa nada).")
    if agregacion == "suma" and V.CATALOGO[variable].unidad != "W/m²":
        warnings.warn(
            f"Sumar '{variable}' ({V.CATALOGO[variable].unidad}) rara vez "
            "significa algo; ¿querías 'media'?")

    f = _media_circular if circular else {
        "media": "mean", "max": "max", "min": "min", "suma": "sum"}[agregacion]
    g = (d.set_index(col)
           .groupby(["fuente", "nodo_id", "municipio"])["valor"]
           .resample(regla).agg(f)
           .reset_index())
    # Tras agregar, el otro reloj ya no aplica: se deja una sola columna de
    # tiempo, con el nombre que espera el dibujo.
    return g.rename(columns={col: "t"})


# --------------------------------------------------------------------------- #
# Textos automáticos
# --------------------------------------------------------------------------- #
def _titulo_auto(variable: str, d: pd.DataFrame, frecuencia: str,
                 agregacion: str) -> str:
    from urbano.clima import variables as V
    v = V.CATALOGO[variable]
    que = {"hora": "", "dia": f"{agregacion} diaria de ",
           "mes": f"{agregacion} mensual de "}[frecuencia]
    lugares = d["municipio"].nunique()
    donde = (d["municipio"].iloc[0] if lugares == 1
             else f"{lugares} municipios")
    # La descripción del catálogo trae la procedencia entre paréntesis
    # ("Temperatura del aire a 2 m (MERRA-2 T2M, corregida por elevación)"): en
    # un título de figura desborda y se come la leyenda. Se corta ahí.
    corta = v.descripcion.split(" (")[0]
    t = f"{que}{corta} — {donde}"
    # Solo la primera letra: `.capitalize()` bajaría también el nombre del
    # municipio ("Victoria" -> "victoria").
    return t[0].upper() + t[1:]


def _subtitulo_auto(d: pd.DataFrame, columna_t: str) -> str:
    t0, t1 = d[columna_t].min(), d[columna_t].max()
    fuentes = " · ".join(sorted(d["fuente"].unique(),
                                key=lambda f: list(FUENTES).index(f)))
    return f"{t0:%Y-%m-%d} a {t1:%Y-%m-%d}  ·  {fuentes}"


def _nota_auto(variable: str, d: pd.DataFrame, tz: str) -> str:
    """Las advertencias que la gráfica no puede mostrar pero cambian su lectura."""
    notas = []
    if variable in NO_COMPARABLES:
        notas.append(f"⚠ {variable}: {NO_COMPARABLES[variable]}")
    # El NSRDB de este repo termina en 2024; ERA5 sigue hasta 2025. Si el tramo
    # pedido se sale, la línea azul se corta y hay que decir por qué.
    col = "t" if "t" in d.columns else (
        "datetime_local" if tz == "local" else "datetime_utc")
    if "NSRDB" in set(d["fuente"]):
        fin_nsrdb = d.loc[d["fuente"] == "NSRDB", col].max()
        fin_era5 = d.loc[d["fuente"] != "NSRDB", col].max()
        if pd.notna(fin_era5) and pd.notna(fin_nsrdb) and fin_era5 > fin_nsrdb:
            notas.append(
                f"El NSRDB llega hasta {fin_nsrdb:%Y-%m-%d}; después solo hay ERA5.")
    if tz == "local":
        # Qué zona(s) hay en juego no es cosmético: si la gráfica mezcla un
        # municipio fronterizo con uno del interior, en verano sus ejes locales
        # están desplazados una hora entre sí.
        from urbano.clima.agregacion import tz_de_municipio
        cat = catalogo_lugares()
        zonas = sorted({tz_de_municipio(c) for c in
                        cat.loc[cat["municipio"].isin(d["municipio"].unique()),
                                "cve_mun"]})
        notas.append(f"Hora local ({', '.join(zonas)}).")
    else:
        notas.append("Hora UTC.")
    return "\n".join(notas)


# --------------------------------------------------------------------------- #
# La gráfica
# --------------------------------------------------------------------------- #
def comparar_series(variable: str = "ghi", lugares=None, desde=None, hasta=None,
                    fuentes=tuple(FUENTES), frecuencia: str = "hora",
                    agregacion: str = "media", horas=None, meses=None,
                    tz: str = "local", facetas="auto",
                    titulo=None, subtitulo=None, etiqueta_x=None,
                    etiqueta_y=None, nota=None, leyenda: bool = True,
                    figsize=None, ax=None, guardar=None, datos=None,
                    mostrar_tabla: bool = False):
    """
    Compara una variable entre NSRDB y ERA5 como series de tiempo.

    Parameters
    ----------
    variable : nombre del catálogo (`urbano.clima.variables`): "ghi",
        "temperature", "pressure", "dew_point", "relative_humidity",
        "wind_speed", "wind_direction"… Es lo único obligatorio.
    lugares : `nodo_id`, nombre de municipio, o lista de ellos. `None` = los 43.
    desde, hasta : fechas inclusivas en hora local. `None` = sin límite.
    fuentes : subconjunto de {"NSRDB", "ERA5-Land", "ERA5-single"}.
    frecuencia : "hora" (cruda), "dia" o "mes".
    agregacion : "media", "max", "min" o "suma". Solo aplica a "dia"/"mes".
    horas : filtro de hora del día. `(12, 20)` = rango inclusivo;
        `[6, 12, 18]` = esas horas sueltas. Útil para mirar solo horas de sol.
    meses : filtro de mes, `[6, 7, 8]` para el verano.
    tz : "local" (por omisión) o "utc". Cambia el eje Y LOS FILTROS de hora.
    facetas : "auto" (un panel por lugar si hay más de uno), True o False.
    titulo, subtitulo, etiqueta_x, etiqueta_y, nota : textos. `None` los
        autogenera; `""` los quita.
    leyenda : False para ocultarla (con una sola fuente se oculta sola).
    figsize : tupla; si no, se calcula según el número de paneles.
    ax : dibujar sobre un eje existente. Obliga a `facetas=False`.
    guardar : ruta donde escribir el PNG.
    datos : DataFrame ya cargado con `cargar()`, para no releer.
    mostrar_tabla : devuelve también la tabla de las series dibujadas.

    Returns
    -------
    `matplotlib.figure.Figure`, o `(Figure, DataFrame)` si `mostrar_tabla`.

    Examples
    --------
    >>> comparar_series("ghi", lugares="victoria",
    ...                 desde="2024-06-01", hasta="2024-06-07")
    >>> comparar_series("temperature", lugares=["Victoria", "Tampico", "Reynosa"],
    ...                 desde="2024-01-01", hasta="2024-12-31", frecuencia="mes")
    >>> comparar_series("ghi", lugares=2120, horas=(11, 17), frecuencia="dia",
    ...                 titulo="GHI en horas de sol", nota="")
    """
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from urbano.clima import variables as V

    if tz not in ("local", "utc"):
        raise ValueError("`tz` debe ser 'local' o 'utc'")

    d = datos if datos is not None else cargar(variable, lugares, desde, hasta,
                                               fuentes)
    if datos is not None:
        # Con datos ya cargados los filtros siguen valiendo: es lo que permite
        # pedir la serie una vez y recortarla distinto en cada gráfica.
        variable = d["variable"].iloc[0] if "variable" in d else variable
        if lugares is not None:
            d = d[d["nodo_id"].isin(resolver_lugares(lugares)["nodo_id"])]
        if isinstance(fuentes, str):
            fuentes = [fuentes]
        d = d[d["fuente"].isin(list(fuentes))]
        if desde is not None:
            d = d[d["datetime_local"] >= pd.Timestamp(desde)]
        if hasta is not None:
            fin = pd.Timestamp(hasta)
            if fin == fin.normalize():
                fin += pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            d = d[d["datetime_local"] <= fin]
    if d.empty:
        raise ValueError("Los filtros no dejaron ninguna fila. Revisa el rango "
                         "de fechas: el NSRDB va de 2020 a 2024.")

    d = _filtrar(d, horas, meses, tz)
    if d.empty:
        raise ValueError(f"Los filtros horas={horas} / meses={meses} no "
                         "dejaron ninguna fila.")
    d = _agregar(d, frecuencia, agregacion, variable, tz)
    col_t = "t" if "t" in d.columns else (
        "datetime_local" if tz == "local" else "datetime_utc")

    v = V.CATALOGO[variable]
    presentes = [f for f in FUENTES if f in set(d["fuente"])]
    municipios = list(dict.fromkeys(d.sort_values("nodo_id")["municipio"]))

    if facetas == "auto":
        facetas = len(municipios) > 1
    if ax is not None:
        facetas = False

    # ----- lienzo ---------------------------------------------------------- #
    if ax is not None:
        fig, ejes = ax.figure, [ax]
        paneles = [None]
    elif facetas:
        n = len(municipios)
        fig, axs = plt.subplots(n, 1, sharex=True,
                                figsize=figsize or (11, 2.4 * n + 1.2))
        ejes = list(np.atleast_1d(axs))
        paneles = municipios
    else:
        fig, a = plt.subplots(figsize=figsize or (11, 4.2))
        ejes, paneles = [a], [None]

    for eje, panel in zip(ejes, paneles):
        sub = d if panel is None else d[d["municipio"] == panel]
        for f in presentes:
            s = sub[sub["fuente"] == f].sort_values(col_t)
            if s.empty:
                continue
            # Con varios lugares en un mismo eje, el color sigue siendo el de la
            # fuente: se distinguen por el estilo de línea, nunca por otro color.
            if panel is None and len(municipios) > 1:
                for i, m in enumerate(municipios):
                    sm = s[s["municipio"] == m]
                    eje.plot(sm[col_t], sm["valor"], color=COLOR[f],
                             lw=ANCHO[f], zorder=ORDEN_Z[f], alpha=.9,
                             ls=["-", "--", ":", "-."][i % 4],
                             label=f"{f} · {m}")
            else:
                eje.plot(s[col_t], s["valor"], color=COLOR[f], lw=ANCHO[f],
                         zorder=ORDEN_Z[f], alpha=.9, label=f)
        if panel is not None:
            # El nombre del panel va dentro, pegado a la esquina: como título de
            # eje empujaría los paneles y rompería la comparación vertical.
            eje.text(.01, .93, panel, transform=eje.transAxes, fontsize=9.5,
                     va="top", ha="left", color="#0b0b0b", weight=600)
        eje.grid(True, lw=.5, color="#d9d8d3", alpha=.9)       # rejilla recesiva
        eje.set_axisbelow(True)
        for lado in ("top", "right"):
            eje.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            eje.spines[lado].set_color("#c3c2b7")
        eje.tick_params(colors="#52514e", labelsize=9)
        if v.tipo == "circular":
            eje.set_ylim(0, 360)
            eje.set_yticks([0, 90, 180, 270, 360])

    # ----- textos ---------------------------------------------------------- #
    # El eje x no siempre son horas: en "dia"/"mes" poner "Hora local" describe
    # mal lo que se está viendo.
    reloj = "local" if tz == "local" else "UTC"
    ex_auto = {"hora": f"Hora {reloj}", "dia": f"Día ({reloj})",
               "mes": f"Mes ({reloj})"}[frecuencia]
    ejes[-1].set_xlabel(etiqueta_x if etiqueta_x is not None else ex_auto,
                        fontsize=9.5, color="#52514e")
    ey = etiqueta_y if etiqueta_y is not None else f"{v.nombre} ({v.unidad})"
    if facetas:
        fig.supylabel(ey, fontsize=9.5, color="#52514e")
    else:
        ejes[0].set_ylabel(ey, fontsize=9.5, color="#52514e")

    # La cabecera se apila de arriba abajo —título, subtítulo, leyenda— y cada
    # pieza presente empuja a la siguiente. Se lleva la cuenta en `y` para que
    # quitar cualquiera de ellas (pasando "") no deje un hueco.
    n_txt = nota if nota is not None else _nota_auto(variable, d, tz)
    if ax is None:
        alto = fig.get_size_inches()[1]
        paso = .30 / alto            # ~0.3 pulgadas por línea de cabecera
        t = titulo if titulo is not None else _titulo_auto(variable, d,
                                                           frecuencia, agregacion)
        st = subtitulo if subtitulo is not None else _subtitulo_auto(d, col_t)
        y = .995
        if t:
            fig.suptitle(t, fontsize=12.5, weight=600, color="#0b0b0b",
                         x=.008, ha="left", y=y)
            y -= paso
        if st:
            fig.text(.008, y, st, fontsize=9.5, color="#52514e",
                     ha="left", va="top")
            y -= paso * .85
        # Una sola fuente no necesita caja de leyenda: el título ya la nombra.
        # Va alineada a la izquierda bajo el subtítulo; arriba a la derecha se
        # solapaba con los títulos largos.
        if leyenda and len(presentes) > 1:
            manejadores, etiquetas = ejes[0].get_legend_handles_labels()
            fig.legend(manejadores, etiquetas, loc="upper left",
                       bbox_to_anchor=(.008, y), ncol=min(len(etiquetas), 4),
                       frameon=False, fontsize=9.5, handlelength=1.8,
                       columnspacing=1.6)
            y -= paso * .85

        if n_txt:
            fig.text(.008, .002, n_txt, fontsize=8.5, color="#52514e",
                     ha="left", va="bottom")
        fig.autofmt_xdate()
        abajo = (.055 + .028 * (n_txt.count("\n") + 1)) if n_txt else .04
        fig.tight_layout(rect=[.008, abajo, .995, y - paso * .15])
    if guardar:
        os.makedirs(os.path.dirname(os.path.abspath(guardar)), exist_ok=True)
        fig.savefig(guardar, dpi=150, bbox_inches="tight",
                    facecolor="#fcfcfb")
        print(f"[fig] {guardar}")
    return (fig, d) if mostrar_tabla else fig
