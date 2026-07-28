# Catálogo de features (ordenado por tipo)

Todas las features se indexan por la **hora objetivo τ = t+1** y respetan el
anti-leakage: deterministas/estáticas en τ; observadas SIEMPRE rezagadas (`.shift(≥1)`).
El target es `kt = ghi/clearsky_ghi` y el GHI se reconstruye como `kt·clearsky_ghi`.
Cada bloque vive en `forecasting/features/`.

Convención: `_lag1` = valor en τ-1, `_lag24` = 24 h antes, `_12h` = ventana móvil de
12 h terminada en τ-1.

---

## 0. META (no entran al modelo)
Sirven para el target y la evaluación. `forecasting/features/base.py::construir_meta`.

| variable | descripción |
|----------|-------------|
| `kt` | target: índice de cielo despejado en τ (`ghi/clearsky_ghi`, [0,1], operativas) |
| `op` | máscara de hora operativa (`clearsky_ghi>0 & zenith<85`) |
| `clearsky_ghi_target` | clearsky en τ, para reconstruir GHI = kt·clearsky |
| `ghi_true` | GHI observado en τ (evaluación) |
| `fill_flag` | % de relleno satelital en τ (segmentación de métricas) |
| `nodo_id` | id del nodo (evaluación multi-nodo; el nodo se DESCRIBE con lat/lon/msnm) |

---

## 1. DETERMINISTAS / known-future (bloque `base`)
Conocidas de antemano en τ (geometría solar y calendario). **Uso:** dan el "esqueleto"
determinista del día. **Creación:** copiadas/derivadas del timestamp de τ.

| variable | descripción | cómo se crea |
|----------|-------------|--------------|
| `clearsky_ghi`,`clearsky_dni`,`clearsky_dhi` | irradiancia de cielo despejado en τ | del dato (modelo de cielo claro NSRDB) |
| `solar_zenith_angle` | ángulo cenital solar en τ | del dato |
| `hour`,`doy`,`month` | hora, día del año, mes de τ | del índice |
| `sin_hour`,`cos_hour` | hora en codificación cíclica | `sin/cos(2π·hour/24)` |
| `sin_doy`,`cos_doy` | día del año cíclico (estacionalidad) | `sin/cos(2π·doy/365.25)` |

## 2. ESTÁTICAS del nodo (bloque `base`)
**Uso:** describen el nodo sin one-hot; permiten que un modelo pooled generalice
entre nodos. **Creación:** de la metadata, constantes por nodo.

| variable | descripción |
|----------|-------------|
| `latitude`,`longitude` | coordenadas del nodo |
| `msnm` | altitud (metros sobre el nivel del mar) |

## 3. OBSERVADAS rezagadas (bloque `base`)
Solo conocidas hasta τ-1. **Uso:** estado reciente de radiación/meteo/aerosoles.
**Creación:** `columna.shift(1)` (o del kt para los lags).

| variable | descripción | cómo se crea |
|----------|-------------|--------------|
| `kt_last_op` | último kt operativo conocido = predicción de smart persistence A | `kt_op.ffill().shift(1)` |
| `kt_lag1`,`kt_lag2`,`kt_lag3` | kt de 1/2/3 h antes (persistencia reciente) | `kt.shift(k)` |
| `kt_lag24` | kt de la misma hora del día anterior | `kt.shift(24)` |
| `temperature_lag1`,`dew_point_lag1`,`relative_humidity_lag1`,`pressure_lag1`,`precipitable_water_lag1` | meteo en τ-1 | `.shift(1)` |
| `wind_speed_lag1`,`wind_direction_lag1` | viento crudo en τ-1 (dir. circular; ver bloque viento) | `.shift(1)` |
| `surface_albedo_lag1`,`aerosol_optical_depth_lag1`,`alpha_lag1`,`asymmetry_lag1`,`ssa_lag1`,`ozone_lag1` | aerosoles/albedo en τ-1 | `.shift(1)` |
| `cloud_type_lag1`,`cloud_fill_flag_lag1`,`fill_flag_lag1` | nubosidad/relleno en τ-1 | `.shift(1)` |

*(Se excluyen a propósito `ghi/dni/dhi` crudos en τ —fuga con el target— y las UV.)*

## 4. VOLATILIDAD / rampas (bloque `volatilidad`)
**Uso:** señal de "régimen inestable". Nota: en single-node sobreajustaba; se conserva
opcional. **Creación:** sobre kt operativo rezagado.

| variable | descripción | cómo se crea |
|----------|-------------|--------------|
| `kt_lag4`,`kt_lag5`,`kt_lag6`,`kt_lag48` | arco largo del pasado de kt | `kt.shift(k)` |
| `kt_ramp1`,`kt_ramp2` | rampa reciente (Δkt entre horas contiguas) | `kt.shift(1)-kt.shift(2)`, etc. |
| `kt_ramp_abs1` | magnitud de la rampa reciente | `|kt_ramp1|` |
| `kt_std_3`,`kt_std_6` | volatilidad de kt en 3/6 h | `kt_op.shift(1).rolling(w).std()` |
| `kt_mean_3`,`kt_mean_6` | media de kt reciente | `.rolling(w).mean()` |
| `kt_rango_3`,`kt_rango_6` | rango (max-min) de kt reciente | `.rolling(w).max()-min()` |

## 5. HISTORIA NOCTURNA (bloque `nocturno`)
**Uso:** informa las primeras horas de la mañana (la meteo existe de noche aunque el
kt no). **Creación:** ventanas móviles de 12 h y tendencias, todo rezagado.

| variable | descripción | cómo se crea |
|----------|-------------|--------------|
| `relative_humidity_media_12h`,`precipitable_water_media_12h` | media trailing 12 h | `.shift(1).rolling(12).mean()` |
| `temperature_min_12h`,`temperature_max_12h` | mínimo/máximo nocturno de T | `.rolling(12).min()/max()` |
| `relative_humidity_min_12h`,`relative_humidity_max_12h` | rango de HR reciente | idem |
| `pressure_tend_12h`,`precipitable_water_tend_12h`,`temperature_tend_12h` | tendencia (valor τ-1 − valor de hace 12 h) | `.shift(1)-.shift(13)` |

## 6. VIENTO en componentes (bloque `viento`)
**Uso:** la dirección es circular (0°=360°) y cruda confunde al modelo; las componentes
son continuas y llevan velocidad+dirección. Base de la advección. **Creación:** del
viento en τ-1 (convención meteo, DV = dirección desde la que sopla).

| variable | descripción | cómo se crea |
|----------|-------------|--------------|
| `wind_u_lag1` | componente zonal (E-O) del viento | `-VV·sin(DV)` en τ-1 |
| `wind_v_lag1` | componente meridional (N-S) del viento | `-VV·cos(DV)` en τ-1 |
| `wind_dir_sin_lag1`,`wind_dir_cos_lag1` | dirección continua (sin velocidad) | `sin/cos(DV)` en τ-1 |

## 7. ESTADO DE CIELO / precursores de nubosidad (bloque `cielo`)
**Uso:** anticipan nubosidad de forma barata. `kd_difusa` resultó la ~5ª feature más
importante. **Creación:** rezagadas.

| variable | descripción | cómo se crea |
|----------|-------------|--------------|
| `kd_difusa_lag1` | fracción difusa en τ-1 (↑ con nubes) | `(dhi/ghi)` recortada [0,1], `.shift(1)` |
| `kd_difusa_lag2` | fracción difusa 2 h antes | `.shift(2)` |
| `kd_difusa_tend` | tendencia de la difusa (cielo cerrándose +) | `kd.shift(1)-kd.shift(2)` |
| `dewpoint_depresion_lag1` | depresión del punto de rocío T−Td (↓ ⇒ saturación/nubes) | `(temperature-dew_point).shift(1)` |

*Nota:* `cloud_type` (categórica nominal) se QUITÓ de este promedio: se maneja en el
bloque `nubes`. Ver sección 8.

## 8. NUBES — codificación de `cloud_type` (bloque `nubes`)
`cloud_type` es categórica **nominal** (sus códigos no ordenan por opacidad), así que
no se promedia cruda. **Uso:** estado de nube con sentido físico. **Creación:** target/
opacity encoding = kt medio de cada tipo, ajustado SOLO en train (anti-fuga), global
entre nodos en multi-nodo, guardado como `opacidad_cloud.json`. Categoría no vista →
media global.

| variable | descripción | para qué | cómo se crea |
|----------|-------------|----------|--------------|
| `cloud_op_lag1` | opacidad del tipo de nube en τ-1 (kt medio del tipo) | orden por opacidad en lugar del código crudo | `cloud_type.map(kt_medio_train).shift(1)` |
| `cloud_op_media_12h` | opacidad media de las últimas 12 h | nubosidad reciente ponderada por opacidad | `.shift(1).rolling(12).mean()` del score |
| `frac_nublado_12h` | fracción de horas nubladas (código>0) en 12 h | FRECUENCIA de nubes (complementa a la opacidad) | `(cloud_type>0).shift(1).rolling(12).mean()` |

*Nota empírica:* `cloud_type_lag1` (código crudo, en `base`) sigue siendo muy
importante — XGBoost separa el código nominal con varios cortes; `cloud_op_lag1`/
`frac_nublado_12h` aportan poco extra (redundantes). El valor del bloque es
metodológico (dejar de promediar una categórica) más que un salto de métrica.

## 9. ESPACIALES / ADVECCIÓN (bloque `adveccion`, multi-nodo)
**Qué es:** features que cruzan nodos — para cada nodo usan el kt de sus **vecinos** en
la malla en τ-1. **Para qué:** la física de "cuándo llega la nube" (las rampas): la
nubosidad se advecta con el viento, `∂kt/∂t ≈ -(u·∂kt/∂x + v·∂kt/∂y)`. **Cómo se crean:**
se pasa el kt a formato ancho (hora × nodo), se toma τ-1 con `shift(1)` y se calculan
por diferencias finitas sobre los vecinos de la malla lat/lon (ver
`features/adveccion.py`). Requiere el bloque `viento`.

| variable | descripción | para qué | cómo se crea |
|----------|-------------|----------|--------------|
| `kt_vecinos_mean` | kt medio de los ≤8 vecinos en τ-1 | contexto espacial de nubosidad (la más importante del bloque) | media del vecindario 3×3 sobre `kt` ancho en τ-1 |
| `kt_vecinos_std` | desviación de kt entre vecinos en τ-1 | heterogeneidad = borde nuboso/frente entrando | desviación del vecindario |
| `kt_grad_x` | gradiente E-O de kt | ¿de qué lado (E/O) está más nublado? | `kt(vecino_E)-kt(vecino_O)` en τ-1 |
| `kt_grad_y` | gradiente N-S de kt | ídem N/S | `kt(vecino_N)-kt(vecino_S)` en τ-1 |
| `kt_adveccion` | término de advección | cambio de kt esperado por el viento (predictor directo de rampas) | `-(wind_u_lag1·kt_grad_x + wind_v_lag1·kt_grad_y)` |

*Nota empírica:* `kt_vecinos_mean/std` (contexto espacial crudo) pesan mucho más que el
término `kt_adveccion` explícito — XGBoost reconstruye la advección a partir del kt de
vecinos + viento; el producto hecho a mano es redundante pero no estorba.

### 9b. Advección REFINADA (bloque `adveccion_upwind`, espacial; requiere `viento` y `nubes`)
**Para qué:** afinar la señal espacial de rampas. **Cómo:** sobre el kt/opacidad anchos
en τ-1 y la geometría de la malla.

| variable | descripción | para qué | cómo se crea |
|----------|-------------|----------|--------------|
| `kt_upwind` | kt en τ-1 de la celda de DONDE viene el aire | muestreo semi-Lagrangiano (lag advectivo: dirección + velocidad) | origen = posición − viento·Δt (en celdas), lookup del kt(τ-1) de esa celda |
| `kt_vecinos_mean_r{r}` | kt medio en vecindario de radio r (r2=5×5 ~17 km; r3=7×7 ~26 km) | contexto espacial del campo nuboso; ventana mayor ve venir la nube más lejos | media de los vecinos (2r+1)²−1 en τ-1 |
| `cloud_op_vecinos_mean` | opacidad de nube media de los 8 vecinos en τ-1 | `cloud_type` ESPACIAL | media de `cloud_op_lag1` de los vecinos |

*Nota empírica:* `kt_vecinos_mean_r2` (2ª feature) y `cloud_op_vecinos_mean` (3ª) son muy
potentes — el contexto espacial más amplio y la nube espacial mandan. `kt_upwind`
(semi-Lagrangiano) se usa poco: a resolución horaria/malla de ~4 km el desplazamiento
suele ser <1 celda (redundante con kt_lag1 y los vecinos). Añadir **radio 3**
(`kt_vecinos_mean_r3`, exp07 v4) aporta un empujón general modesto (skill +0.006, usado
como 5ª feature) pero con rendimientos decrecientes: r2 sigue dominando y la rampa fuerte
no se mueve. El radio se controla por experimento con los bloques `adveccion_upwind`
(r2) y `adveccion_upwind_r23` (r2+r3).
