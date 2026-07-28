# Fase 10 — Advección refinada (exp07 v3)

Afina el bloque espacial: muestreo upwind semi-Lagrangiano, vecindario radio 2 y
`cloud_type` espacial. Ejecutado en la Mac M5.

## Qué se montó

- `features/adveccion.py::agregar_adveccion_upwind` — nuevo bloque espacial
  `adveccion_upwind` (requiere `viento` y `nubes`). 3 features (ver
  `catalogo_features.md` §9b):
  - `kt_upwind`: kt en τ-1 de la celda de donde viene el aire (origen = posición −
    viento·Δt en celdas; lag advectivo con dirección + velocidad).
  - `kt_vecinos_mean_r2`: kt medio en vecindario 5×5 (radio 2).
  - `cloud_op_vecinos_mean`: opacidad de nube media de los 8 vecinos en τ-1.
- `exp07_adveccion` **v3** = v2 + `adveccion_upwind`.

## Capacidad de la laptop

exp07 v3 (144 nodos, 6.3 M filas, 63 features): **~56 s**, pico **~6.6 GB**. OK.

## Resultados (test 2024)

| versión | features | skill | rampa fuerte | cubierto |
|---------|----------|-------|--------------|----------|
| exp07 v2 | 60 | 0.1117 | 0.199 | 0.000 |
| **exp07 v3** | 63 | **0.1213** | **0.218** | **0.017** |

- Global skill **0.112 → 0.121** (+8.6 %), RMSE 76.76 → 75.93.
- Por régimen (v2→v3): rampa fuerte **+0.018**, cubierto **+0.017** (ya POSITIVO: bate a
  persistence en cielo cubierto), moderada +0.009, parcial/despejado +0.008. Rampa suave
  −0.041 (irrelevante: persistence domina ahí).

### Importancia
- **`kt_vecinos_mean_r2` 2ª feature** (gain 0.101): el vecindario radio 2 capta mejor el
  campo nuboso que el radio 1 (que cae a 4ª).
- **`cloud_op_vecinos_mean` 3ª** (gain 0.057): el `cloud_type` ESPACIAL (con la opacidad
  de v2) por fin rinde fuerte — la codificación de nube gana valor al agregarse en el espacio.
- `kt_upwind` rank 21 (modesto): a resolución horaria/malla ~4 km el desplazamiento suele
  ser <1 celda, redundante con kt_lag1/vecinos.

**Lección:** XGBoost aprovecha el CONTEXTO ESPACIAL crudo; cuanto más rico (radio mayor,
nube espacial), mejor. El término/lookup físico explícito importa menos que las medias
de vecindario.

## Trayectoria completa del skill (test)

single 0.061 → 25 nodos 0.070 → 144 nodos 0.085 → +viento/cielo 0.086 → +advección 0.111
→ +nubes 0.112 → **+advección refinada 0.121**. RMSE 84.9 (persist) → **75.9 W/m²**.

## Notebook

`exp07_adveccion.ipynb` (default v3): comparación por régimen v3 vs exp06 (advección
total) y v2 vs v3 (refinamiento), importancias, y **momentos difíciles** (nodo 1736) con
RMSE diario persistence/v2/v3 y series superpuestas.

## Testing

`test_adveccion.py` (+2): features upwind presentes y sin fuga; con viento 0 `kt_upwind`
= kt del propio nodo (kt_lag1). Total suite: **36 tests**.

## Siguiente

exp04 v2 (conformal); escalar nodos / modelos secuenciales; posibles: vecindario radio 3,
gradiente de opacidad de nube, lag advectivo multi-hora.
