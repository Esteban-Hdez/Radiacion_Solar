# Roadmap — foco en los EPISODIOS difíciles

## Tesis del proyecto

Lo que aporta valor no son los días soleados (persistence y XGBoost ya dan R²>0.95),
sino los **episodios**: días nublados/variables, rampas de kt (entra/sale una nube) y
las primeras horas de la mañana. El skill global (~6 %) está **diluido** por miles de
horas fáciles; hay que medir y optimizar **por régimen**.

## Límite físico del dato (importante)

NSRDB es **horario** y satelital. Una nube cruza en minutos ⇒ a resolución horaria
solo se ve el kt medio de la hora, no el "cruce". Predecir el minuto de llegada de una
nube **no es alcanzable** con este dato; haría falta satélite 5-15 min, imágenes de
cielo o campos de nube de un NWP. Lo alcanzable: el kt medio de la próxima hora y —más
útil— su **incertidumbre** (banda P10-P90).

## Qué se mide ahora (para VER los episodios)

`forecasting/eval/regimen.py`: métricas por **régimen de nubosidad** (kt<0.3 cubierto /
0.3-0.7 parcial / >0.7 despejado) y por **régimen de rampa** (|Δkt| suave/moderada/
fuerte). Hallazgos (test 2024, exp02 base):
- **Rampa fuerte (>0.25): skill +0.15** → aquí es donde el ML aporta de verdad.
- **Rampa suave: skill −0.69** → persistence casi imbatible en horas planas.
- **Cubierto estable: skill negativo** → el modelo sobrepasa; persistence gana.

## Experimentos (framework versionado en `forecasting/experiments/`)

| id | idea | estado | resultado |
|----|------|--------|-----------|
| `exp02_xgb_base` | XGBoost + feature-set base (= Fase 3) | ✅ | referencia. Test skill 0.060 |
| `exp03_xgb_volatilidad` | + volatilidad/rampas + agregados nocturnos | ✅ | **v1** (todo): NO mejora (0.055). **v2** (base+nocturno): +marginal (0.061). `volatilidad` sobreajusta a resolución horaria single-node |
| `exp04_xgb_cuantilico` | banda P10/P50/P90 (probabilístico) | ✅ | P50 skill 0.054 (a la par); banda se ensancha en nublado pero **infracubierta** (0.50 vs 0.80) por el borde kt=1. Falta recalibrar (v2) |
| `exp05_multinodo_victoria` | pooled 25 (v1) / 144 (v2) nodos | ✅ | v1 (25): skill 0.070. **v2 (144): skill 0.085** (+21 %). Escalar nodos es el gran efecto. Corre ~30 s en la Mac |
| `exp06_viento_cielo` | +viento (u/v) + cielo (difusa, rocío), 144 nodos | ✅ | skill 0.086; mejora en el sitio correcto (**rampa fuerte 0.166→0.170**). `kd_difusa` 5ª feature. Viento modesto sin advección |
| `exp07_adveccion` v1 | +features espaciales (vecinos, gradientes, advección), 144 nodos | ✅ | **skill 0.111** (+29 %). Mejora todos los regímenes: cubierto +0.042, rampa moderada +0.027, rampa fuerte +0.026. `kt_vecinos_mean` 3ª feature. RMSE 84.9→76.8 |
| `exp07_adveccion` v2 | + bloque `nubes` (opacity encoding + fracción nublada) | ✅ | skill 0.112 (marginal). Fix metodológico: no promediar categórica. `cloud_type` crudo ya era 3ª feature; encoding aporta poco extra |
| `exp07_adveccion` v3 | + `adveccion_upwind` (upwind semi-Lagrangiano, vecindario r2, nube espacial) | ✅ | **skill 0.121** (+8.6 %). Rampa fuerte 0.218, cubierto ya positivo (0.017). `kt_vecinos_mean_r2` 2ª y `cloud_op_vecinos_mean` 3ª feature |
| `exp07_adveccion` v4 | + vecindario **radio 3** (7×7 ~26 km) | ✅ | **skill 0.127** (+4.9 %). Empujón general (cubierto 0.029, parcial/despejado +0.004) pero rampa fuerte igual (0.218); `kt_vecinos_mean_r3` 5ª. Rendimientos decrecientes. RMSE 84.9→75.4 |

### Pendientes (prioridad por ROI)

1. **Recalibración conformal del intervalo** — split-conformal para que exp04 alcance
   cobertura 0.80. Barato (Mac). *(exp04 v2)*
2. **Escalar más el bloque** — cientos de nodos dispersos; habilita secuenciales.
3. **Más advección** — gradiente de opacidad de nube, lag advectivo multi-hora,
   afinar hiperparámetros. *(exp07 v5+)*
4. **Modelos secuenciales** — LSTM/GRU seq2seq (48→24) o **Temporal Fusion Transformer**
   (usa known-future clearsky + estáticas + cuantiles). Honesto: raramente superan a un
   GBM bien featurizado salvo con muchos datos; hacer tras escalar, en Ubuntu GPU.

Nowcasting real de rampas (sub-horario) quedaría fuera del alcance tabular: visión
sobre imágenes satelitales / optical flow.

## Principio de trabajo

Cada idea = un experimento versionado (`expNN`), reproducible por su `config.json`,
con dataset de features cacheado por feature-set y artefactos en carpeta propia.
Los resultados negativos también se documentan (como v1 de exp03).
