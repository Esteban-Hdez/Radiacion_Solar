# Fase 7 — Features viento/cielo + escalado a 144 nodos

Responde a: (1) descomponer el viento en componentes y añadir precursores de
nubosidad; (2) escalar el bloque de 25 a 144 nodos. Ejecutado en la MacBook Air M5.

## Bloques de features nuevos

- `features/viento.py::bloque_viento` — el viento (VV, DV) en **componentes** (la
  dirección es circular y cruda confunde al modelo):
  `u = -VV·sin(DV)`, `v = -VV·cos(DV)` (convención meteo) + `sin(DV)`, `cos(DV)`.
  Rezagado (`shift(1)`, viento observado). Prepara la advección espacial (exp07).
- `features/cielo.py::bloque_cielo` — precursores de nubosidad baratos:
  **fracción difusa** `kd = dhi/ghi` (+ `kd_difusa_lag2`, `kd_difusa_tend`) y
  **depresión del punto de rocío** `T − Td`. Todo rezagado.

Registrados en `features.BLOQUES` como `viento` y `cielo`.

## Escalado del bloque

`data/loaders.nodos_cercanos(pivote, n)` selecciona los `n` nodos más cercanos
(determinista). `exp05` ahora tiene **v1** (5×5 = 25 nodos) y **v2** (12×12 = 144
nodos). `exp06` = 144 nodos + viento + cielo.

## Capacidad de la laptop (M5, 16 GB) — 144 nodos

- Cargar 144 nodos × 5 años (6.314.112 filas): ~2.7 s.
- Features (53 cols): ~3.6 s, matriz ~2.3 GB. **2.964.537 horas operativas**.
- Experimento completo: **~28–34 s**; **pico de memoria ~4.6 GB**. Cómodo.

## Resultados (test 2024, skill vs persistence)

| experimento | nodos | features | skill | rampa fuerte |
|-------------|-------|----------|-------|--------------|
| single (exp03) | 1 | base+noct | 0.061 | 0.153 |
| exp05 v1 | 25 | base+noct | 0.070 | 0.155 |
| **exp05 v2** | **144** | base+noct | **0.085** | 0.166 |
| **exp06** | 144 | +viento+cielo | **0.086** | **0.170** |

### Escalar nodos (el gran efecto)
25 → 144 nodos subió el skill **0.070 → 0.085** (+21 %). Más datos y más diversidad
(el bloque abarca sierra y valle) mejoran de forma clara, y el modelo pooled sigue
generalizando a todos los nodos.

### Viento + cielo (efecto pequeño pero en el sitio correcto)
Sobre 144 nodos: skill **0.085 → 0.086** global, y por régimen la mejora se concentra
donde importa: **rampa fuerte 0.166 → 0.170**, cubierto +0.005, parcial +0.003 (la
rampa suave baja un poco, irrelevante: ahí manda persistence).

- **`kd_difusa_lag1` (fracción difusa) queda 5ª de 53 features** — es un termómetro de
  nubosidad potente, como se esperaba. `dewpoint_depresion_lag1` 9ª.
- Las componentes de viento se usan (dir cos/sin 13ª/22ª) pero de forma modesta: el
  viento por sí solo, sin el kt de los vecinos, tiene señal limitada. Su gran valor
  llega con la **advección espacial** (exp07 = gradiente de kt · vector viento).

## Testing

`forecasting/tests/test_viento_cielo.py` (+5): convención u/v, dirección continua
acotada, no-fuga (τ-1), rango y lag de la fracción difusa, depresión del rocío.
Total suite: **27 tests**.

## Siguiente

exp07: features espaciales **upwind/advección** (kt/cloud_type de vecinos a barlovento
según el vector viento; gradiente espacial de kt · viento) sobre el bloque de 144.
Ahí se espera el salto real en rampas fuertes.
