# Fase 3 — Primer XGBoost para kt(t+1) (nodo 1736)

Modelo que predice `kt(t+1)` y **supera a smart persistence (skill > 0)**. GHI
reconstruido como `kt_pred * clearsky_ghi(τ)`, evaluado sobre las MISMAS horas
operativas que persistence A (comparación justa). Corre en Ubuntu (GPU) y Mac (CPU):
device autodetectado.

## Código

- `forecasting/features.py::construir_features` — fila indexada por la hora objetivo
  τ. Features: deterministas known-future en τ (`clearsky_*`, `solar_zenith_angle`,
  hora/doy/mes + seno/coseno), estáticas (lat/lon/msnm) y observadas REZAGADAS
  (`kt_lag{1,2,3,24}`, `kt_last_op` = persistencia como feature, meteo/aerosol/nubes
  a τ-1). Se excluyen ghi/dni/dhi crudos en τ (fuga) y las UV (≈ f(ghi)). 35 features.
- `forecasting/models/xgb.py` — `detectar_device` (nvidia-smi → cuda, si no cpu;
  override `RS_DEVICE`), `entrenar` (early stopping en val), `predecir_ghi`.
- `forecasting/eval/comparar.py::comparar` — alinea modelo y persistence por índice
  y calcula RMSE/MAE/MBE/**R²** + skill = 1 - RMSE_modelo/RMSE_persistence por
  segmento de fill_flag.
- `forecasting/eval/metrics.py` — añadido `r2` (incluido en `evaluar`).
- `forecasting/viz.py::VisualizadorForecast` — series temporales observado vs XGB vs
  persistence con filtros (año/mes/día/rango), dispersión con R² coloreada por
  fill_flag, y `dias_dificiles`/`plot_dias_dificiles`. Índice en hora local (UTC-6).
  - Las series se reindexan a malla horaria continua: la línea se **corta en la
    noche** (no une la última hora operativa de un día con la primera del siguiente).
  - Criterios de dificultad: `nublado` (menor kt medio), `variabilidad` (desv. de kt),
    `relleno` (fracción fill_flag>0), `combinado` (default: nubosidad+variabilidad+
    relleno) y `error_xgb` (RMSE real, para validar). Hallazgo: en días muy nublados
    persistence a veces bate al XGB (GHI bajo y estable; el modelo sobrepasa).
- `notebooks/03_xgboost_t1.ipynb` — entrena, guarda modelo y `fase3_xgb_metrics.csv`,
  + secciones de visualización temporal, dispersión y días difíciles. Modelo en
  `Results/Tamaulipas/forecast/modelos/xgb_t1_nodo1736.json`.

## Resultados (GHI reconstruido, W/m²)

| split | segmento | RMSE persist | RMSE XGB | MAE XGB | R² XGB (vs persist) | skill |
|-------|----------|------|------|------|------|-------|
| val   | global   | 84.63 | 77.39 | 42.05 | — | 0.085 |
| test  | global   | 84.87 | **79.82** | 46.64 | 0.926 (0.916) | **0.060** |
| test  | limpio ff=0 | 86.48 | 81.51 | 47.95 | 0.917 (0.906) | 0.058 |
| test  | rellenado ff>0 | 67.50 | 61.28 | 34.09 | 0.906 (0.887) | 0.092 |

(Números exactos en `Results/Tamaulipas/forecast/fase3_xgb_metrics.csv`.)

**Skill > 0 en todos los segmentos de val y test**: el modelo supera al baseline.
RMSE test 84.87 → 79.82 (≈ 6 % de mejora sobre persistence, además del ~53 % que
persistence ya gana a cielo despejado). Skill mayor en val (0.085) que en test
(0.060): leve degradación esperable en el año más lejano.

## Decisiones

- **Sin ponderar por clearsky².** Se probó `sample_weight = clearsky²` para alinear
  el objetivo (MSE de kt) con el RMSE de GHI; empeoró RMSE (81.26) y MAE (48.79):
  concentra en el mediodía y generaliza peor. Default `ponderar_ghi=False`.
- **NaN nativos.** Los `kt_lag*` son NaN en noches; XGBoost aprende la dirección por
  defecto. No se imputan.
- **Split fijo** train 2020-22 / early stop val 2023 / test 2024 (walk-forward
  expanding simple). El rolling-refit se deja para fase posterior.
- **Bug corregido:** `clearsky_ghi` es int16 en el parquet; cualquier operación tipo
  `clearsky²` debe castear a float64 antes (si no, desborda a negativos).

## Features dominantes (gain)

`kt_lag1` (~0.47) ≫ `kt_last_op` (~0.17) > `cloud_type_lag1` (~0.07) > calendario
cíclico y meteo rezagada. Confirma que la persistencia reciente manda y el modelo
añade corrección con nubosidad/estacionalidad.

## Siguiente

Afinar hiperparámetros; features de nubes/aerosoles y target encoding de cloud_type;
horizonte **t+24**; generalización **multi-nodo** (aplicar `construir_features` por
nodo y concatenar; lat/lon/msnm ya describen el nodo) en la máquina Ubuntu con GPU;
walk-forward con refit rodante.
