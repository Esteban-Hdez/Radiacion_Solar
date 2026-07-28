# Fase 6 — Multi-nodo pooled (exp05, bloque Cd. Victoria)

Prueba de concepto: entrenar UN solo XGBoost con un bloque de nodos, para ver si
agrupar ayuda y medir la capacidad de la laptop. Ejecutado en la MacBook Air M5.

## Qué se montó

- `data/loaders.cargar_bloque(nodos, anios)` — lee el bloque de `Data/*.parquet` con
  filtro `nodo_id in [...]` (empuje a row-group, eficiente) y asegura lat/lon/msnm.
- `features.construir_bloque(df_bloque, bloques)` — construye features POR NODO (los
  lags no cruzan nodos) y concatena; `nodo_id` es columna META (el nodo se describe
  con lat/lon/msnm, nunca con el id).
- Evaluación multi-nodo sin reindex frágil: `predecir_ghi` añade `ghi_persistence`
  (de `kt_last_op`, correcta por nodo) y `nodo_id`; `comparar`/`metricas_por_regimen`
  usan esa persistencia en-frame (`ref=None`) y la rampa se calcula por nodo.
- Runner ampliado: `ExperimentoConfig.nodos`/`bloque_id`; dataset cacheado por
  feature-set + bloque; nuevo artefacto `metrics_por_nodo.csv` (skill del pooled en
  cada nodo). `exp05_multinodo_victoria` (bloque 5×5 = 25 nodos).

## Capacidad de la laptop (M5, 16 GB)

- Cargar 25 nodos × 5 años (1.096.200 filas): **0.3 s**.
- Construir features multi-nodo (45 feats): **0.5 s**, ~340 MB, RSS ~1.5 GB.
- Experimento completo (train + eval, **514.680 horas operativas**): **~6 s**.

Sobra margen. Escalar a cientos de nodos es viable en esta máquina; los 4384 completos
irían mejor en la Ubuntu por memoria.

## Resultados (test 2024)

| modelo | skill test | RMSE | notas |
|--------|-----------|------|-------|
| single-node exp02 (base) | 0.060 | 79.82 | 1 nodo |
| single-node exp03 (base+noct) | 0.061 | 79.70 | 1 nodo |
| **pooled exp05 (25 nodos)** | **0.070** | **78.92** | +16 % rel. sobre single |

- **Skill del pooled EN el nodo 1736: 0.072** (RMSE 78.77) vs 0.061 del modelo
  single-node en el mismo nodo → agrupar mejora el pronóstico del propio nodo
  (aprende de los episodios de los vecinos). Comparación apples-to-apples.
- **Consistente entre nodos:** skill medio 0.070, rango 0.063–0.080; los 25 nodos
  positivos. El modelo único generaliza a todo el bloque (con lat/lon/msnm).
- **Por régimen:** parcial 0.108 (single ~0.05-0.10) y despejado 0.098 mejoran; la
  **rampa fuerte queda ~0.155** (igual que single). Interpretación: el volumen de
  datos mejora la calibración general y el régimen parcial, pero el régimen más duro
  (rampas fuertes) está limitado por FÍSICA ESPACIAL, no por datos → lo ataca exp06
  (features upwind/advección), no más nodos pooled.

## Conclusión

Agrupar nodos **sí ayuda** (skill +16 % y generalización robusta) y la laptop lo
corre en segundos. Es la base para (a) escalar a más nodos y (b) añadir features
espaciales upwind, que es donde se espera el salto en rampas fuertes.

## Testing

`forecasting/tests/test_multinodo.py` (+4): `nodo_id` es META, **no hay fuga entre
nodos** (kt_lag1 de la 1ª fila de cada nodo es NaN), persistencia en-frame por nodo,
`comparar` con `ref=None`. Total suite: **22 tests**.

## Siguiente

exp06: features espaciales upwind (kt/cloud_type de vecinos a barlovento según
`wind_direction`) sobre este bloque. Escalar bloque (50–100 nodos dispersos).
