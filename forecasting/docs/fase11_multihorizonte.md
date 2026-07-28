# Fase 11 — Multi-horizonte t+1 … t+24 (horas operativas) + evaluación rica

Extiende el pronóstico de t+1 a **t+1 … t+24 horas OPERATIVAS** (día-adelante) con
desglose de métricas por horizonte, hora, mes, nodo, régimen y fill_flag. En la Mac M5.

## Diseño

- `forecasting/multihorizonte.py` — enfoque DIRECTO: un solo modelo con el **horizonte
  como feature**. Se trabaja sobre la serie SOLO operativa de cada nodo; h = h-ésima
  hora operativa futura (target siempre definido).
  - Features OBSERVADAS ancladas en el base t (kt reciente, meteo, viento u/v, difusa,
    opacidad de nube, depresión de rocío…). DETERMINISTAS known-future en el objetivo
    τ_h (clearsky_*, zenith, calendario). Más `horizonte` y `gap_horas` (τ_h − t).
  - Persistence de referencia por horizonte = kt(t) (`kt_last_op`), igual para toda h.
  - Contrato META compatible con el pipeline t+1 → reutiliza `models.xgb.entrenar`.
- `forecasting/eval/desglose.py` — métricas por grupo (global, horizonte, hora local,
  mes, nodo, régimen de nubosidad, fill_flag), resúmenes de RANGO (min/media/max) y
  `heatmap_hora_horizonte`.
- `multihorizonte.ejecutar(nodos)` construye, entrena, evalúa y guarda todos los
  desgloses + modelo + predicciones en `experiments/exp08_multihorizonte/v1/`.

## Capacidad de la laptop

exp08 (25 nodos × 24 horizontes = **12.34 M filas**, 35 features float32): **~35 s**,
pico **~6.9 GB**. Escalar a 144 nodos (~71 M filas) sería Ubuntu.

## Resultados (test 2024)

- **Global skill 0.244** (RMSE 139.4 vs persistence 184.4) — muy superior al t+1
  (~0.13) porque persistence colapsa a horizontes largos.
- **Por horizonte:** skill **crece con h** → h=1 **−0.08** (el modelo global no se
  especializa; persistence casi óptima), h=3 0.15, h=6 0.25, h=18-24 **~0.28**. RMSE
  del modelo se aplana (~150) mientras el de persistence sigue subiendo (~208).
- **Por mes:** 0.14 (jun, temporada convectiva, RMSE alto) a **0.34 (ago)**.
- **Por hora local (objetivo):** skill 0.19-0.36; RMSE máximo al mediodía (GHI alto).
- **Por nodo:** muy consistente, skill 0.233-0.251 en los 25 nodos.
- Desgloses adicionales: régimen de nubosidad, fill_flag, y tabla de RANGOS.

### Nota honesta (h=1)
El modelo directo único **pierde contra persistence en h=1** (skill −0.08): reparte
capacidad entre 24 horizontes y no se especializa en el corto. Mitigaciones:
usar el modelo t+1 dedicado (exp07, skill +0.13) para h=1 y el multi-horizonte para
h≥2, o entrenar modelos por horizonte. El valor del multi-horizonte está en h≥3, que
es justo donde persistence falla.

## Testing

`forecasting/tests/test_multihorizonte.py` (+5): solo horas operativas, target = h
operativas adelante, persistencia = kt(t), horizonte/gap como features, deterministas
tomadas del objetivo. Total suite: **43 tests**.

## Siguiente

- Modelos por horizonte (o t+1 dedicado + multi-horizonte para h≥2) para arreglar h=1.
- Features espaciales (vecinos) al base para el multi-horizonte.
- **NWP** como covariable known-future (el gran lever para día-adelante).
- Cuantílico multi-horizonte + escalar nodos (Ubuntu).
