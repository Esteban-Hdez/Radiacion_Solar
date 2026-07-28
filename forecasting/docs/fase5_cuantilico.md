# Fase 5 — Notebooks por experimento + exp04 (XGBoost cuantílico)

## Notebook por experimento (finos y consistentes)

Cada experimento tiene su notebook en `notebooks/experiments/<exp_id>.ipynb`, apoyado
en `forecasting/experiments/reporte.py::ReporteExperimento`, que **carga** los
artefactos ya generados (o **ejecuta** el experimento con `ejecutar=True`) y expone:

- `resumen()` — id, feature-set, best_iteration, RMSE/skill/R² de test.
- `metrics_global`, `regimen_nubosidad`, `regimen_rampa` (+ `intervalo`,
  `intervalo_regimen` si es cuantílico).
- `plot_importancias(n)`.
- `visualizador()` → `VisualizadorForecast` (series con corte nocturno y ejes a 45°,
  dispersión con R², días difíciles, y —cuantílico— `serie_intervalo` con banda P10-P90).

Así el notebook es una secuencia ORDENADA de secciones (métricas → régimen →
importancias → series → dispersión → días difíciles [→ intervalos]) sin lógica
duplicada. `VisualizadorForecast.desde_predicciones_guardadas` unifica puntual y
cuantílico leyendo `predictions_test.parquet`.

Notebooks: `exp02_xgb_base`, `exp03_xgb_volatilidad`, `exp04_xgb_cuantilico`.

## exp04 — XGBoost cuantílico (P10/P50/P90)

Pronóstico **probabilístico** para los episodios: en cielo nublado/variable el punto
siempre falla (kt de alta varianza), así que se predice una **banda**. Código:
`forecasting/models/xgb_cuantilico.py` (multi-cuantil, `reg:quantileerror`) y
`forecasting/eval/cuantil.py` (pinball, cobertura, anchura, global y por régimen).

### Gotcha clave (documentado)

La mediana de kt es **exactamente 1.0** (domina el cielo despejado); `reg:quantileerror`
inicializa `base_score` en el cuantil empírico ⇒ el P50 **colapsa a la constante 1.0**
(best_iteration=0). Solución: fijar `base_score=0.5`. Con eso el P50 recupera calidad
(MAE de kt ≈ el del modelo squared).

### Resultados (test 2024)

- **Puntual (P50):** RMSE 80.28, skill 0.054, R² 0.925 — a la par de exp03 (el P50
  sigue batiendo a persistence). MBE +8 W/m²: la mediana sobrestima algo (kt es
  asimétrico, mediana > media).
- **Intervalo P10-P90:** pinball 14.36; **cobertura global 0.50** (nominal 0.80);
  anchura media 132 W/m².
- **Por régimen** la banda se **ensancha correctamente** donde hay más incertidumbre:
  parcial 202 y cubierto 199 W/m² vs despejado 109. Pero la **cobertura queda baja**.

### Interpretación honesta

La infracobertura viene del **borde kt=1**: en cielo despejado el 56 % de horas tienen
kt clipado a 1.0 y el P90 (función suave) no alcanza ese pico ⇒ `obs>P90` se concentra
en despejado (49 %). Operativamente el clear-sky es trivial; lo relevante es que la
banda crece en los episodios. Aun así, la calibración marginal debe corregirse.

### Siguiente (exp04 v2)

Recalibración **conformal** (split-conformal sobre residuos de val) para que la
cobertura alcance el 0.80 nominal sin inflar la anchura en cielo despejado. Es barato
y estándar.

## Testing

`forecasting/tests/test_cuantil.py` (+4 tests): pinball simétrico en la mediana y
asimétrico en cuantiles extremos, columnas y rangos de las métricas de intervalo.
Total suite: **18 tests** (`python -m pytest forecasting/tests/ -q`).
