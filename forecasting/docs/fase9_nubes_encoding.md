# Fase 9 — Codificación correcta de `cloud_type` (bloque `nubes`)

Corrige un fallo metodológico: `cloud_type_media_12h` promediaba una variable
**categórica nominal** (los códigos NSRDB no ordenan por opacidad). Ejecutado en la Mac.

## Qué se montó

- `features/nubes.py` — tratamiento correcto de `cloud_type`:
  - **Opacity/target encoding**: cada tipo → kt medio de ese tipo, ajustado SOLO en
    train (anti-fuga), **global** entre nodos en multi-nodo, no-visto → media global.
    Features `cloud_op_lag1` (instantáneo) y `cloud_op_media_12h` (media 12 h).
  - **Fracción nublada** `frac_nublado_12h` = proporción de horas con nube (código>0)
    en 12 h (mide FRECUENCIA; complementa a la opacidad).
- `nocturno.py`: se QUITÓ `cloud_type` del promedio crudo (`cloud_type_media_12h`).
- `builder`: `nubes` se ajusta una vez (global en `construir_bloque`) y se pasa a cada
  nodo. El encoding se guarda como artefacto `opacidad_cloud.json` (junto al dataset y
  en la carpeta del experimento) para reproducibilidad.
- `exp07_adveccion` **v2** = base+nocturno+viento+cielo+**nubes**+adveccion (v1 = con
  cloud_type crudo, para comparar).

## Encoding de opacidad (kt medio por tipo, train; mayor = más transparente)

overshooting 0.21 · hielo opaco 0.34 · agua super-enfriada 0.39 · mixto 0.39 ·
agua 0.51 · solapado 0.62 · cirros 0.67 · niebla 0.79 · despejado 0.99.
El **código crudo NO sigue este orden** (p.ej. cirros=7 es transparente pero código
alto), por eso promediarlo no tiene sentido.

## Resultados (test 2024)

| | skill global | rampa fuerte |
|---|---|---|
| exp07 v1 (cloud crudo) | 0.1107 | 0.196 |
| **exp07 v2 (nubes)** | **0.1117** | 0.199 |

Mejora **marginal** (+0.001 global; por régimen ±0.003-0.004). **Interpretación honesta:**
`cloud_type_lag1` (código crudo, en `base`) sigue siendo la **3ª feature** (gain 0.060):
XGBoost ya extraía la señal de nube partiendo el código nominal en varios cortes (un
árbol es robusto a categóricas crudas, a diferencia de un modelo lineal). Las nuevas se
usan (`cloud_op_lag1` 5ª, `frac_nublado_12h` 9ª) pero son en parte redundantes. El valor
del cambio es **metodológico** (no promediar una nominal; encoding anti-fuga guardado)
más que un salto de métrica.

## Notebook

`exp07_adveccion.ipynb` (default v2) añade una sección de **momentos difíciles** (nodo
1736): tabla de RMSE diario persistence / v1 / v2 en los días más difíciles y series
superpuestas (observado, persistence, v1, v2) para inspección visual de la mejora.

## Testing

`forecasting/tests/test_nubes.py` (+4): encoding solo usa train, categoría no vista →
global, fracción nublada correcta, `nubes` vía `construir` sin fuga (1ª fila NaN) y
encoding accesible. Total suite: **34 tests**.

## Nota de reproducibilidad

Al cambiar el bloque `nocturno` (quitar cloud_type), los datasets cacheados de
feature-sets con `nocturno` construidos antes de esta fase quedan desactualizados; se
reconstruyen solos al tener nuevo `feature_set_id` (v2 incluye `nubes`) o con
`--forzar-dataset`. Los resultados ya guardados (v1, exp03/05/06) son registro inmutable.

## Siguiente

exp07 v2 sigue siendo el mejor (skill 0.112). Pendientes: afinar advección (lag
advectivo, upwind explícito, `cloud_type` espacial), exp04 v2 (conformal), escalar
nodos / secuenciales.
