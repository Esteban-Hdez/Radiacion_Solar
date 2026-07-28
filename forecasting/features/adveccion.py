"""
Features ESPACIALES de advección (multi-nodo) — la física de "cuándo llega la nube".

A diferencia del resto de bloques (por nodo), estas features cruzan nodos: para cada
nodo usan el kt de sus VECINOS en la malla en el instante τ-1 (observado, sin fuga).
La nubosidad se mueve advectada por el viento; la ecuación de advección dice

    ∂kt/∂t ≈ -( u·∂kt/∂x + v·∂kt/∂y )

es decir, el cambio esperado de kt = -(vector viento · gradiente espacial de kt). Eso
es un predictor directo de RAMPAS: si a barlovento hay menos kt (nube) y el viento
sopla hacia aquí, kt bajará.

Implementación: se pasa el kt a formato ANCHO (filas=hora, columnas=nodo), se toma
τ-1 con `shift(1)` (malla horaria contigua) y se calculan, por diferencias finitas
sobre los vecinos de la malla lat/lon:
- media y desviación de kt en el vecindario (contexto/heterogeneidad espacial),
- gradientes gx=(E-W), gy=(N-S),
- término de advección -(u·gx + v·gy), con u,v = componentes del viento en τ-1.

Requiere que el feature-set incluya el bloque `viento` (u/v). Se aplica en
`features.construir_bloque` cuando `adveccion` está entre los bloques.
"""
from __future__ import annotations
import warnings
import numpy as np
import pandas as pd

# Vecinos en la malla: (Δíndice_lat, Δíndice_lon).
_DIRS8 = {"E": (0, 1), "W": (0, -1), "N": (1, 0), "S": (-1, 0),
         "NE": (1, 1), "NW": (1, -1), "SE": (-1, 1), "SW": (-1, -1)}


def _paso(valores: np.ndarray) -> float:
    """Paso de malla = mínima diferencia positiva entre coordenadas únicas."""
    u = np.unique(np.round(valores, 6))
    d = np.diff(u)
    d = d[d > 0]
    return float(d.min()) if len(d) else 1.0


def agregar_adveccion(feat: pd.DataFrame) -> pd.DataFrame:
    """Añade features espaciales a la matriz multi-nodo `feat` (índice datetime con
    columnas nodo_id, kt, wind_u_lag1, wind_v_lag1, latitude, longitude)."""
    dt = feat.index.name or "datetime"
    largo = feat.reset_index().rename(columns={"index": dt})

    # Índices de malla (ilat, ilon) por nodo.
    coords = largo.groupby("nodo_id")[["latitude", "longitude"]].first()
    plat, plon = _paso(coords["latitude"].values), _paso(coords["longitude"].values)
    lat0, lon0 = coords["latitude"].min(), coords["longitude"].min()
    ilat = ((coords["latitude"] - lat0) / plat).round().astype(int)
    ilon = ((coords["longitude"] - lon0) / plon).round().astype(int)
    celda_a_nodo = {(ilat[n], ilon[n]): n for n in coords.index}

    # kt en formato ancho (filas=hora, columnas=nodo) y su valor en τ-1.
    K = largo.pivot(index=dt, columns="nodo_id", values="kt").sort_index()
    nodos = list(K.columns)
    pos = {n: k for k, n in enumerate(nodos)}
    Kprev = K.shift(1).to_numpy()                       # (T, N) = kt de vecinos en τ-1

    def _vals_dir(dlat, dlon):
        """Matriz (T, N): para cada nodo, kt del vecino en esa dirección (NaN si no)."""
        idx = np.full(len(nodos), -1, dtype=int)
        for k, n in enumerate(nodos):
            vecino = celda_a_nodo.get((ilat[n] + dlat, ilon[n] + dlon))
            if vecino is not None:
                idx[k] = pos[vecino]
        out = np.full_like(Kprev, np.nan)
        val = idx >= 0
        out[:, val] = Kprev[:, idx[val]]
        return out

    E, W = _vals_dir(0, 1), _vals_dir(0, -1)
    Nn, S = _vals_dir(1, 0), _vals_dir(-1, 0)
    with warnings.catch_warnings():                     # nanmean de filas todo-NaN
        warnings.simplefilter("ignore", RuntimeWarning)
        pila = np.stack([_vals_dir(*d) for d in _DIRS8.values()])   # (8, T, N)
        vec_mean = np.nanmean(pila, axis=0)
        vec_std = np.nanstd(pila, axis=0)
    gx, gy = E - W, Nn - S                              # gradientes espaciales de kt

    def _largo(mat, nombre):
        return (pd.DataFrame(mat, index=K.index, columns=nodos)
                .stack().rename(nombre))
    esp = pd.concat([_largo(vec_mean, "kt_vecinos_mean"),
                     _largo(vec_std, "kt_vecinos_std"),
                     _largo(gx, "kt_grad_x"), _largo(gy, "kt_grad_y")], axis=1)
    esp.index = esp.index.set_names([dt, "nodo_id"])

    out = largo.merge(esp.reset_index(), on=[dt, "nodo_id"], how="left")
    # Término de advección: -(u·gx + v·gy). u,v = viento (componentes) en τ-1.
    out["kt_adveccion"] = -(out["wind_u_lag1"] * out["kt_grad_x"]
                            + out["wind_v_lag1"] * out["kt_grad_y"])
    return out.set_index(dt)


# --------------------------------------------------------------------------- #
# Advección refinada (exp07 v3): upwind semi-Lagrangiano + vecindario r2 + nube
# --------------------------------------------------------------------------- #
_RMAX = 3          # desplazamiento upwind máximo en celdas
_M_POR_GRADO = 111_320.0
_DT_S = 3600.0     # horizonte t+1 = 1 h


def _offsets_radio(r: int) -> list[tuple[int, int]]:
    """Offsets del vecindario de radio r: ventana (2r+1)×(2r+1) sin el centro.
    r=1 -> 8 vecinos (3×3), r=2 -> 24 (5×5), r=3 -> 48 (7×7)."""
    return [(di, dj) for di in range(-r, r + 1) for dj in range(-r, r + 1)
            if (di, dj) != (0, 0)]


def _malla(coords: pd.DataFrame):
    """Índices de malla (ilat, ilon) por nodo + pasos en grados."""
    plat, plon = _paso(coords["latitude"].values), _paso(coords["longitude"].values)
    lat0, lon0 = coords["latitude"].min(), coords["longitude"].min()
    ilat = ((coords["latitude"] - lat0) / plat).round().astype(int)
    ilon = ((coords["longitude"] - lon0) / plon).round().astype(int)
    return ilat, ilon, plat, plon


def agregar_adveccion_upwind(feat: pd.DataFrame,
                             radios: tuple[int, ...] = (2,)) -> pd.DataFrame:
    """Features espaciales REFINADAS (requiere bloques `viento` y `nubes`):

    - `kt_upwind`: muestreo semi-Lagrangiano — kt en τ-1 de la celda de DONDE viene el
      aire (desplazamiento = -viento·Δt). Combina dirección y velocidad (lag advectivo).
    - `kt_vecinos_mean_r{r}` por cada r en `radios`: kt medio en el vecindario de radio r
      (r=2 -> 5×5 ~17 km; r=3 -> 7×7 ~26 km). Ventanas mayores "ven venir" el campo
      nuboso más lejos (la nube que llega en 1 h está a ~10-18 km con viento típico).
    - `cloud_op_vecinos_mean`: opacidad de nube media de los 8 vecinos en τ-1
      (`cloud_type` espacial).
    """
    dt = feat.index.name or "datetime"
    largo = feat.reset_index().rename(columns={"index": dt})
    coords = largo.groupby("nodo_id")[["latitude", "longitude"]].first()
    ilat, ilon, plat, plon = _malla(coords)
    nodos = list(coords.index)

    # Array 2D (ilat, ilon) -> nodo_id (para lookups vectorizados).
    arr = np.full((int(ilat.max()) + 1, int(ilon.max()) + 1), -1, dtype=np.int64)
    for n in nodos:
        arr[ilat[n], ilon[n]] = n

    # kt ancho en τ-1 y su versión larga (para el muestreo upwind por fila).
    K = largo.pivot(index=dt, columns="nodo_id", values="kt").sort_index()
    Kprev = K.shift(1)
    ktprev_largo = (Kprev.stack().rename("kt_upwind").reset_index()
                    .rename(columns={"level_0": dt, "level_1": "nodo_id"}))
    ktprev_largo.columns = [dt, "nodo_id", "kt_upwind"]

    # --- kt_upwind: celda origen = posición - viento·Δt (en celdas) ---
    cell_m_lat = _M_POR_GRADO * plat
    cell_m_lon = _M_POR_GRADO * np.cos(np.deg2rad(coords["latitude"].mean())) * plon
    o = largo[[dt, "nodo_id", "wind_u_lag1", "wind_v_lag1"]].copy()
    o["ilat"] = o["nodo_id"].map(ilat); o["ilon"] = o["nodo_id"].map(ilon)
    di = np.clip(np.round(-o["wind_v_lag1"] * _DT_S / cell_m_lat), -_RMAX, _RMAX)
    dj = np.clip(np.round(-o["wind_u_lag1"] * _DT_S / cell_m_lon), -_RMAX, _RMAX)
    sil = (o["ilat"] + di).fillna(o["ilat"]).astype(int).clip(0, arr.shape[0] - 1)
    sio = (o["ilon"] + dj).fillna(o["ilon"]).astype(int).clip(0, arr.shape[1] - 1)
    o["source_nodo"] = arr[sil.to_numpy(), sio.to_numpy()]
    o = o.merge(ktprev_largo.rename(columns={"nodo_id": "source_nodo"}),
                on=[dt, "source_nodo"], how="left")

    # --- vecindarios (radio 2 de kt; opacidad de nube de 8 vecinos) ---
    Kp = Kprev.to_numpy()
    pos = {n: k for k, n in enumerate(K.columns)}

    def _mean_offsets(mat_prev, cols, offsets):
        suma = np.zeros_like(mat_prev); cuenta = np.zeros_like(mat_prev)
        for dlat, dlon in offsets:
            idx = np.array([pos.get(int(arr[ilat[n] + dlat, ilon[n] + dlon]) if
                                    0 <= ilat[n] + dlat < arr.shape[0] and
                                    0 <= ilon[n] + dlon < arr.shape[1] else -1, -1)
                            for n in cols], dtype=int)
            val = idx >= 0
            trozo = np.full_like(mat_prev, np.nan)
            trozo[:, val] = mat_prev[:, idx[val]]
            m = ~np.isnan(trozo)
            suma[m] += trozo[m]; cuenta[m] += 1
        with np.errstate(invalid="ignore"):
            return np.where(cuenta > 0, suma / cuenta, np.nan)

    # Opacidad de nube: cloud_op_lag1 ya está en τ-1 -> se pivota sin volver a shiftar.
    C = largo.pivot(index=dt, columns="nodo_id", values="cloud_op_lag1").sort_index()
    cop = _mean_offsets(C.to_numpy(), list(C.columns), list(_DIRS8.values()))

    def _largo(mat, cols, nombre):
        s = pd.DataFrame(mat, index=K.index, columns=cols).stack().rename(nombre)
        s.index = s.index.set_names([dt, "nodo_id"])
        return s.reset_index()

    esp = _largo(cop, list(C.columns), "cloud_op_vecinos_mean")
    for r in radios:
        kt_r = _mean_offsets(Kp, list(K.columns), _offsets_radio(r))
        esp = esp.merge(_largo(kt_r, list(K.columns), f"kt_vecinos_mean_r{r}"),
                        on=[dt, "nodo_id"])

    out = largo.merge(o[[dt, "nodo_id", "kt_upwind"]], on=[dt, "nodo_id"], how="left")
    out = out.merge(esp, on=[dt, "nodo_id"], how="left")
    return out.set_index(dt)
