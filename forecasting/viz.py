"""
Visualización del pronóstico: observado vs XGBoost vs persistence.

`VisualizadorForecast` toma las predicciones ya alineadas y ofrece:
- `serie_temporal(...)`: curvas GHI/kt en el tiempo, con filtros por año/mes/día
  concreto/rango de fechas.
- `dispersion(...)`: scatter predicho vs observado (XGB y persistence) con R².
- `dias_dificiles(...)`: rankea los días más difíciles. "Difícil" = día variable/
  nublado (alta desviación intradía de kt) y/o con poca información real (mucho
  relleno satelital, `fill_flag>0`); son donde se espera que el modelo sufra.
  Se puede validar con el error real del modelo por día.
- `plot_dias_dificiles(...)`: pinta esos días.

El índice interno está en HORA LOCAL (UTC + `tz_offset`, por defecto -6 para
Tamaulipas) para que un "día" agrupe el arco diurno completo y las horas se lean
en local. Solo contiene horas OPERATIVAS (las que se evalúan).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from forecasting.eval import metrics as M

TZ_OFFSET = -6   # Tamaulipas (CST). UTC + offset -> hora local.


class VisualizadorForecast:
    def __init__(self, datos: pd.DataFrame, etiqueta_modelo: str = "XGBoost"):
        """`datos`: índice datetime (hora local) con columnas ghi_obs, ghi_xgb,
        ghi_persist, kt_obs, kt_xgb, kt_persist, fill_flag, clearsky."""
        self.d = datos.sort_index()
        self.etiqueta = etiqueta_modelo

    # ------------------------------------------------------------------ #
    # Construcción
    # ------------------------------------------------------------------ #
    @classmethod
    def desde_predicciones(cls, pred_modelo: pd.DataFrame, per: pd.DataFrame,
                           etiqueta_modelo: str = "XGBoost",
                           tz_offset: int = TZ_OFFSET) -> "VisualizadorForecast":
        """`pred_modelo`: salida de xgb.predecir_ghi (índice τ UTC). `per`: salida de
        smart_persistence (índice UTC, con kt_pred_A / ghi_pred_A). Se alinean por
        índice, se filtra a operativas y se pasa a hora local."""
        d = pd.DataFrame(index=pred_modelo.index)
        d["ghi_obs"] = pred_modelo["ghi_true"]
        d["ghi_xgb"] = pred_modelo["ghi_pred"]
        d["ghi_persist"] = per["ghi_pred_A"].reindex(d.index)
        d["kt_obs"] = pred_modelo["kt_true"]
        d["kt_xgb"] = pred_modelo["kt_pred"]
        d["kt_persist"] = per["kt_pred_A"].reindex(d.index)
        d["fill_flag"] = pred_modelo["fill_flag"]
        d["clearsky"] = pred_modelo["clearsky_ghi"]
        d = d.dropna(subset=["ghi_obs", "ghi_xgb", "ghi_persist"])
        d.index = d.index + pd.Timedelta(hours=tz_offset)   # UTC -> local
        d.index.name = "hora_local"
        return cls(d, etiqueta_modelo)

    @classmethod
    def desde_predicciones_guardadas(cls, pred: pd.DataFrame,
                                     etiqueta_modelo: str = "XGBoost",
                                     tz_offset: int = TZ_OFFSET) -> "VisualizadorForecast":
        """Construye desde `predictions_test.parquet` de un experimento (índice τ UTC,
        con ghi_true/ghi_pred/ghi_persistence/kt_*, y opcionalmente ghi_pXX de cuantiles).
        Homogéneo para experimentos puntuales y cuantílicos."""
        d = pd.DataFrame(index=pred.index)
        d["ghi_obs"] = pred["ghi_true"]
        d["ghi_xgb"] = pred["ghi_pred"]
        d["ghi_persist"] = pred["ghi_persistence"]
        d["kt_obs"] = pred["kt_true"]
        d["kt_xgb"] = pred["kt_pred"]
        cs = pred["clearsky_ghi"].replace(0, np.nan)
        d["kt_persist"] = (pred["ghi_persistence"] / cs).clip(0, 1)
        d["fill_flag"] = pred["fill_flag"]
        d["clearsky"] = pred["clearsky_ghi"]
        # Columnas de cuantiles si el experimento las tiene (ghi_p10, ghi_p90, ...).
        for c in pred.columns:
            if c.startswith("ghi_p") and c[5:].isdigit():
                d[c] = pred[c]
        d = d.dropna(subset=["ghi_obs", "ghi_xgb", "ghi_persist"])
        d.index = d.index + pd.Timedelta(hours=tz_offset)
        d.index.name = "hora_local"
        return cls(d, etiqueta_modelo)

    # ------------------------------------------------------------------ #
    # Filtrado
    # ------------------------------------------------------------------ #
    def _filtrar(self, anio=None, mes=None, dia=None,
                 inicio=None, fin=None) -> pd.DataFrame:
        """Filtra por año, mes (1-12), día concreto ('YYYY-MM-DD') y/o rango
        [inicio, fin]. Los criterios se combinan (AND)."""
        d = self.d
        if anio is not None:
            d = d[d.index.year == anio]
        if mes is not None:
            meses = [mes] if np.isscalar(mes) else list(mes)
            d = d[d.index.month.isin(meses)]
        if dia is not None:
            fecha = pd.Timestamp(dia).date()
            d = d[d.index.date == fecha]
        if inicio is not None:
            d = d[d.index >= pd.Timestamp(inicio)]
        if fin is not None:
            d = d[d.index <= pd.Timestamp(fin)]
        return d

    # ------------------------------------------------------------------ #
    # Series temporales
    # ------------------------------------------------------------------ #
    def serie_temporal(self, anio=None, mes=None, dia=None, inicio=None, fin=None,
                       variable: str = "ghi", ax=None):
        """Curvas observado vs XGB vs persistence en la ventana filtrada.
        `variable`: 'ghi' (W/m²) o 'kt'."""
        d = self._filtrar(anio, mes, dia, inicio, fin)
        if d.empty:
            raise ValueError("El filtro no deja datos.")
        # Malla horaria continua: las noches (no operativas) quedan como NaN y la
        # línea se CORTA ahí (no une la última hora de un día con la primera del
        # siguiente).
        if len(d) > 1:
            grid = pd.date_range(d.index.min(), d.index.max(), freq="h")
            d = d.reindex(grid)
        obs, xgb, per = (f"{variable}_obs", f"{variable}_xgb", f"{variable}_persist")

        if ax is None:
            _, ax = plt.subplots(figsize=(14, 4.5))
        ax.plot(d.index, d[obs], color="k", lw=1.6, label="Observado")
        ax.plot(d.index, d[xgb], color="tab:blue", lw=1.2, alpha=0.9, label=self.etiqueta)
        ax.plot(d.index, d[per], color="tab:orange", lw=1.0, alpha=0.8, ls="--",
                label="Persistence")
        ax.set_ylabel("GHI [W/m²]" if variable == "ghi" else "kt")
        ax.set_xlabel("hora local (UTC-6)")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(alpha=0.3)
        self._formato_x(ax)
        return ax

    @staticmethod
    def _formato_x(ax):
        """Ejes X en formato mm-dd H:M, etiquetas a 45°."""
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(45)
            lbl.set_horizontalalignment("right")

    def serie_intervalo(self, anio=None, mes=None, dia=None, inicio=None, fin=None,
                        p_bajo: int = 10, p_alto: int = 90, ax=None):
        """Banda de incertidumbre P{p_bajo}-P{p_alto} + P50 vs observado (solo
        experimentos cuantílicos). La banda se corta en la noche igual que la serie."""
        cols_band = [f"ghi_p{p_bajo:02d}", "ghi_p50", f"ghi_p{p_alto:02d}"]
        faltan = [c for c in cols_band if c not in self.d.columns]
        if faltan:
            raise ValueError(f"No hay cuantiles en los datos (faltan {faltan}). "
                             "Usa un experimento cuantílico (exp04).")
        d = self._filtrar(anio, mes, dia, inicio, fin)
        if d.empty:
            raise ValueError("El filtro no deja datos.")
        if len(d) > 1:
            d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq="h"))

        if ax is None:
            _, ax = plt.subplots(figsize=(14, 4.5))
        ax.fill_between(d.index, d[f"ghi_p{p_bajo:02d}"], d[f"ghi_p{p_alto:02d}"],
                        color="tab:blue", alpha=0.2, label=f"P{p_bajo}-P{p_alto}")
        ax.plot(d.index, d["ghi_p50"], color="tab:blue", lw=1.2, label="P50")
        ax.plot(d.index, d["ghi_obs"], color="k", lw=1.6, label="Observado")
        ax.set_ylabel("GHI [W/m²]"); ax.set_xlabel("hora local (UTC-6)")
        ax.legend(loc="upper right", fontsize=8); ax.grid(alpha=0.3)
        self._formato_x(ax)
        return ax

    # ------------------------------------------------------------------ #
    # Dispersión
    # ------------------------------------------------------------------ #
    def dispersion(self, anio=None, mes=None, dia=None, inicio=None, fin=None,
                   variable: str = "ghi", color_fill: bool = True):
        """Scatter predicho vs observado para XGB y persistence, con R² en el título.
        Si `color_fill`, colorea por fill_flag (relleno satelital)."""
        d = self._filtrar(anio, mes, dia, inicio, fin)
        if d.empty:
            raise ValueError("El filtro no deja datos.")
        obs = d[f"{variable}_obs"]
        unidad = "[W/m²]" if variable == "ghi" else ""
        fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), sharex=True, sharey=True)
        for ax, col, nombre in [(axes[0], f"{variable}_xgb", self.etiqueta),
                                (axes[1], f"{variable}_persist", "Persistence")]:
            c = d["fill_flag"] if color_fill else "tab:blue"
            sc = ax.scatter(obs, d[col], c=c, cmap="viridis", s=6, alpha=0.35)
            lim = [0, max(obs.max(), d[col].max())]
            ax.plot(lim, lim, "r--", lw=1)
            r2 = M.r2(obs, d[col]); rmse = M.rmse(obs, d[col])
            ax.set_title(f"{nombre}\nR²={r2:.3f}  RMSE={rmse:.1f}")
            ax.set_xlabel(f"observado {unidad}")
            ax.grid(alpha=0.3)
        axes[0].set_ylabel(f"predicho {unidad}")
        if color_fill:
            fig.colorbar(sc, ax=axes, label="fill_flag (% relleno)", shrink=0.8)
        return axes

    # ------------------------------------------------------------------ #
    # Días difíciles
    # ------------------------------------------------------------------ #
    def _tabla_dias(self) -> pd.DataFrame:
        """Agrega por día local: variabilidad de kt, relleno y error del modelo."""
        g = self.d.groupby(self.d.index.date)
        def _rmse(x, a, b):
            return float(np.sqrt(np.mean((x[a] - x[b]) ** 2)))
        tab = pd.DataFrame({
            "n_horas": g.size(),
            "kt_mean": g["kt_obs"].mean(),
            "kt_std": g["kt_obs"].std(),                       # variabilidad (nubes)
            "fill_frac": g["fill_flag"].apply(lambda s: (s > 0).mean()),  # poca info
            "rmse_xgb": g.apply(lambda x: _rmse(x, "ghi_obs", "ghi_xgb"), include_groups=False),
            "rmse_persist": g.apply(lambda x: _rmse(x, "ghi_obs", "ghi_persist"), include_groups=False),
        })
        tab.index = pd.to_datetime(tab.index)
        tab.index.name = "dia_local"
        return tab

    def dias_dificiles(self, n: int = 10, criterio: str = "combinado",
                       anio=None) -> pd.DataFrame:
        """Rankea los `n` días más difíciles.

        criterio:
          - 'nublado'     : menor kt medio (día más cubierto/poca radiación relativa).
          - 'variabilidad': mayor desviación intradía de kt (nubosidad intermitente).
          - 'relleno'     : mayor fracción de horas con relleno satelital (poca info).
          - 'combinado'   : normaliza y suma nubosidad + variabilidad + relleno (default).
          - 'error_xgb'   : mayor RMSE real del modelo (validación de la dificultad).
        """
        tab = self._tabla_dias()
        if anio is not None:
            tab = tab[tab.index.year == anio]
        # 'nubosidad' = 1 - kt_mean: alto en días cubiertos (kt bajo).
        tab = tab.assign(nubosidad=1.0 - tab["kt_mean"])
        if criterio == "combinado":
            def _nrm(s):
                rng = s.max() - s.min()
                return (s - s.min()) / rng if rng > 0 else s * 0
            tab = tab.assign(score=(_nrm(tab["nubosidad"]) + _nrm(tab["kt_std"])
                                    + _nrm(tab["fill_frac"])))
            clave = "score"
        else:
            clave = {"nublado": "nubosidad", "variabilidad": "kt_std",
                     "relleno": "fill_frac", "error_xgb": "rmse_xgb"}[criterio]
        return tab.sort_values(clave, ascending=False).head(n).round(3)

    def plot_dias_dificiles(self, n: int = 6, criterio: str = "combinado",
                            anio=None, variable: str = "ghi"):
        """Series temporales de los `n` días más difíciles (rejilla)."""
        dias = self.dias_dificiles(n, criterio, anio).index
        ncol = 2
        nrow = int(np.ceil(len(dias) / ncol))
        fig, axes = plt.subplots(nrow, ncol, figsize=(14, 3.2 * nrow), squeeze=False)
        for ax, dia in zip(axes.ravel(), dias):
            self.serie_temporal(dia=dia.strftime("%Y-%m-%d"), variable=variable, ax=ax)
            ax.set_title(dia.strftime("%Y-%m-%d"), fontsize=9)
            ax.legend(fontsize=7)
        for ax in axes.ravel()[len(dias):]:
            ax.axis("off")
        fig.suptitle(f"Días más difíciles (criterio: {criterio})", y=1.0)
        fig.tight_layout()
        return axes

    # ------------------------------------------------------------------ #
    # Métricas de una ventana filtrada
    # ------------------------------------------------------------------ #
    def metricas(self, anio=None, mes=None, dia=None, inicio=None, fin=None,
                 variable: str = "ghi") -> pd.DataFrame:
        """RMSE/MAE/MBE/R² de XGB y persistence + skill, en la ventana filtrada."""
        d = self._filtrar(anio, mes, dia, inicio, fin)
        obs = d[f"{variable}_obs"]
        filas = []
        for col, nombre in [(f"{variable}_xgb", self.etiqueta),
                            (f"{variable}_persist", "Persistence")]:
            filas.append({"modelo": nombre, "n": len(d),
                          "RMSE": M.rmse(obs, d[col]), "MAE": M.mae(obs, d[col]),
                          "MBE": M.mbe(obs, d[col]), "R2": M.r2(obs, d[col])})
        tab = pd.DataFrame(filas)
        r_xgb = tab.loc[0, "RMSE"]; r_per = tab.loc[1, "RMSE"]
        tab["skill_vs_persist"] = [M.skill(r_xgb, r_per), np.nan]
        return tab
