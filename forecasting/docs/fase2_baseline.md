# Fase 2 — Baseline smart persistence (nodo 1736)

Referencia obligatoria `kt(t+1)=kt(t)`. GHI reconstruido como `kt_pred *
clearsky_ghi`; evaluación solo en horas operativas (`clearsky_ghi>0` y
`solar_zenith_angle<85`); partición temporal train 2020-22 / val 2023 / test 2024.
Entrada: `Results/Tamaulipas/forecast/nodo_1736_serie.parquet` (5 años, horario,
0 NaN en GHI, 0 datetimes duplicados; 20 586 horas operativas, ~4 100/año).

## Código

- `forecasting/data/loaders.py::cargar_serie_nodo` — lee el parquet de la serie
  committeada (no `Data/`), índice datetime, malla horaria contigua.
- `forecasting/target.py` — `calcular_kt` (clip [0,1]), `mascara_operativa`,
  `reconstruir_ghi`, `split_temporal`.
- `forecasting/eval/metrics.py` — `rmse`, `mae`, `mbe` (=mean(pred-obs)),
  `skill` (1 - RMSE/REF), `evaluar` (tabla global + segmentada).
- `forecasting/eval/persistence.py::smart_persistence` — construye kt_pred/ghi_pred
  de las dos variantes sobre la malla contigua (shift(1) = 1 h de reloj).
- `forecasting/eval/reporte.py` — `tabla_baseline` (split×variante×segmento) y
  `rmse_referencia`. Skill del baseline vs predictor tonto de cielo despejado (kt=1).
- `notebooks/02_baseline_persistence.ipynb` — ejecución + gráficas; guarda
  `fase2_baseline_metrics.csv` y `fase2_rmse_referencia.csv`.

## Dos variantes (discontinuidad noche→mañana)

- **A carry-forward:** usa el último kt operativo (salta la noche). Cubre TODAS
  las horas operativas → es el `RMSE_ref` de la tarea completa para la Fase 3.
- **B consecutivos:** usa kt(t-1) solo si t-1 fue operativa; descarta la 1ª hora
  operativa de cada mañana (~366/año). Persistencia de 1 h "pura" (diagnóstico).

## Resultados (GHI reconstruido, W/m²)

| split | variante | RMSE global | MAE | MBE | skill vs clearsky |
|-------|----------|-------------|-----|-----|-------------------|
| train | A | 83.05 | 40.10 | +2.23 | 0.536 |
| val   | A | 84.63 | 41.81 | +1.80 | 0.565 |
| test  | A | 84.87 | 44.59 | +2.12 | 0.538 |
| train | B | 85.54 | 41.05 | +3.02 | 0.522 |
| val   | B | 87.13 | 42.77 | +2.25 | 0.552 |
| test  | B | 87.49 | 45.72 | +2.82 | 0.524 |

**RMSE_ref (variante A) que la Fase 3 debe superar:** train 83.05, val 84.63,
**test 84.87 W/m²**. Skill del modelo = 1 - RMSE_modelo / RMSE_ref.

### Segmentación por fill_flag
El segmento **rellenado (ff>0) tiene MENOR RMSE** que el limpio (test A: 67.5 vs
86.5) — el dato interpolado por satélite es más suave, por tanto más persistente.
No es que el pronóstico sea "mejor" ahí; refleja menor variabilidad real. Se seguirá
reportando segmentado para no confundir mejora de modelo con facilidad del tramo.

## Notas

- Persistence ya reduce ~52–54 % el RMSE frente a suponer cielo despejado (kt=1):
  el baseline no es trivial de superar.
- MBE pequeño y positivo (~2 W/m²): leve sobreestimación sistemática.
- Variante A tiene RMSE global algo menor que B porque incluye las 1ª horas de la
  mañana (clearsky bajo → error absoluto pequeño que baja el RMSE promedio).

## Siguiente (Fase 3)

Features rezagadas (kt, meteo, aerosoles a t, t-1, …) + deterministas known-future
(clearsky_*, zenith, hora, doy) + estáticas (lat/lon/msnm). Primer XGBoost (GPU)
que logre **skill > 0** sobre el `RMSE_ref` de arriba, evaluado sobre el MISMO
conjunto de horas (variante A) para comparación justa.
