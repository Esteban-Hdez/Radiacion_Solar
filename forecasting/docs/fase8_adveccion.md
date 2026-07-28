# Fase 8 — Features espaciales de advección (exp07)

El lever físico para las RAMPAS. Ejecutado en la MacBook Air M5.

## Qué se montó

- `features/adveccion.py::agregar_adveccion` — primer bloque **ESPACIAL** (cruza
  nodos). Pasa el kt a formato ancho (hora × nodo), toma τ-1 con `shift(1)` y calcula
  por diferencias finitas sobre los vecinos de la malla: media/desviación del
  vecindario, gradientes gx/gy y el término de advección `-(u·gx+v·gy)`. Ver el
  catálogo de features (`catalogo_features.md`, sección 8) para cada variable.
- `features.BLOQUES_ESPACIALES` + `construir_bloque` aplican los bloques espaciales
  sobre la matriz multi-nodo ya concatenada (los por-nodo se construyen antes). Requiere
  el bloque `viento` (u/v).
- `exp07_adveccion` = 144 nodos, base+nocturno+viento+cielo+**adveccion**.

## Capacidad de la laptop (M5, 16 GB)

Experimento completo (144 nodos, 6.3 M filas, 58 features): **~39 s**, pico de memoria
**~6.8 GB**. Dentro de margen.

## Resultados (test 2024, skill vs persistence)

| experimento | features | skill | rampa fuerte | rampa moderada |
|-------------|----------|-------|--------------|----------------|
| exp06 | 144, +viento+cielo | 0.086 | 0.170 | 0.088 |
| **exp07** | 144, **+adveccion** | **0.111** | **0.196** | **0.115** |

- **Global skill 0.086 → 0.111** (+29 %), RMSE 78.95 → 76.84.
- Mejora en **todos** los regímenes, concentrada en los difíciles (Δskill):
  cubierto **+0.042** (−0.045→−0.004, casi cierra la brecha con persistence),
  rampa moderada **+0.027**, rampa fuerte **+0.026**, parcial +0.021, despejado +0.019.
- Consistente entre nodos (skill medio 0.111).

### Importancia
- **`kt_vecinos_mean` es la 3ª feature de 58** (gain 0.064): el contexto espacial de
  nubosidad alrededor del nodo es lo que más aporta. `kt_vecinos_std` 6ª.
- `kt_grad_x/y` y `kt_adveccion` pesan poco (rank 43/52/54): XGBoost **reconstruye la
  advección** con el kt de vecinos + viento crudos; el término explícito es redundante
  (no estorba). El bloque como grupo es el que da el salto.

## Trayectoria completa del skill (test)

single 0.061 → 25 nodos 0.070 → 144 nodos 0.085 → +viento/cielo 0.086 → **+advección 0.111**.
El pronóstico ha pasado de 84.9 (persistence) a **76.8 W/m²** de RMSE, con la mejora
concentrada donde importa: los episodios nublados y de rampa.

## Testing

`forecasting/tests/test_adveccion.py` (+3): features espaciales presentes y como
features (no meta), no-fuga (τ-1 ⇒ 1ª hora NaN), y `kt_vecinos_mean` del nodo central
= media de sus 8 vecinos en τ-1 (correctitud contra un cálculo independiente). Total
suite: **30 tests**.

## Siguiente

- Afinar advección: lag advectivo (distancia/velocidad), vecino upwind explícito,
  ventanas de vecindario mayores; features espaciales de `cloud_type`.
- exp04 v2 (recalibración conformal del intervalo cuantílico).
- Escalar a más nodos / modelos secuenciales (TFT) con el pooled como base.
