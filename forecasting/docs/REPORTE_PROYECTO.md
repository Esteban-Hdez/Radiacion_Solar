# Pronóstico de irradiancia solar (GHI) — Tamaulipas
### Reporte del proyecto

**Región:** Tamaulipas, México · **Fuente:** NSRDB/NREL · **Fecha del reporte:** 2026-07

---

## 1. Resumen ejecutivo

Se desarrolla un sistema de pronóstico de irradiancia solar horaria (GHI) sobre la
malla de nodos NSRDB de Tamaulipas, con **XGBoost** y una metodología cuidada contra
fuga temporal. El target no es el GHI crudo sino el **índice de cielo despejado
`kt = GHI/GHI_clearsky`**, y todo se compara contra el baseline **smart persistence**.

Partiendo de un modelo de un nodo (skill 0.061 sobre persistence), la incorporación de
**información espacial multi-nodo** (vecinos y advección de nubes) elevó el skill a
**0.127** en t+1 (RMSE 84.9 → 75.4 W/m²), con las mayores mejoras en los **episodios
difíciles** (rampas de nubosidad, cielo cubierto). Se extendió además a **multi-horizonte
t+1…t+24 horas operativas** (día/2-días adelante), donde el skill global sube a **0.244**
porque persistence colapsa a horizontes largos. Todo corre en una laptop (MacBook Air M5).

---

## 2. Objetivo

Predecir la **GHI horaria** en los nodos de Tamaulipas a horizonte **t+1** (y luego
**t+1…t+24 horas operativas**), superando de forma consistente al baseline de smart
persistence, con foco especial en los **momentos difíciles** (nubosidad variable,
rampas), que son los operativamente relevantes para la integración de energía solar en
la red. Métrica principal: **forecast skill** = 1 − RMSE_modelo/RMSE_persistence sobre
el GHI reconstruido.

---

## 3. Conjunto de datos

| Campo | Detalle |
|---|---|
| Fuente | **NSRDB** (National Solar Radiation Database, NREL), derivado de satélite |
| Región | Tamaulipas, México |
| Nodos | **4384** en malla regular (paso ~0.04° ≈ **4 km**) |
| Extensión | lat 22.25–27.65, lon −100.14 a −97.18, altitud **0–2994 msnm** (costa a sierra) |
| Periodo | Años **2020–2024** (también 2017 disponible; faltan 2018, 2019) |
| Resolución | **Horaria**, UTC |
| Registros | ~43 848 h/nodo (5 años) × 4384 nodos |

**Variables (34 columnas):**
- *Radiación:* `ghi`, `dni`, `dhi`; cielo despejado `clearsky_ghi/dni/dhi`; UV
  `ghi_uv_280_400`, `ghi_uv_295_385`.
- *Geometría:* `solar_zenith_angle`.
- *Nubes/relleno:* `cloud_type` (categórica), `cloud_fill_flag`, `fill_flag` (% relleno satelital).
- *Meteorología:* `temperature`, `dew_point`, `relative_humidity`, `pressure`,
  `precipitable_water`, `wind_speed`, `wind_direction`.
- *Aerosoles/superficie:* `surface_albedo`, `aerosol_optical_depth`, `alpha`,
  `asymmetry`, `ssa`, `ozone`.
- *Estáticas del nodo:* `latitude`, `longitude`, `msnm`.
- *Tiempo:* `datetime`, `year/month/day/hour`, `nodo_id`.

---

## 4. Preprocesamiento

1. **Target = índice de cielo despejado.** `kt = clip(ghi / clearsky_ghi, 0, 1)`. El
   GHI se reconstruye como `kt_pred · clearsky_ghi`. Se modela `kt` (no GHI) porque
   remueve la parte determinista (ciclo diario/estacional/geográfico, perfectamente
   predecible) y deja solo la **atenuación estocástica por nubes/aerosoles** → target
   estacionario, acotado y comparable entre horas/estaciones/nodos.
2. **Horas operativas.** Solo se predice donde `clearsky_ghi > 0` y
   `solar_zenith_angle < 85°` (día). Las noches nunca son target.
3. **Malla horaria contigua.** Por nodo se reindexa a horas continuas, exponiendo huecos
   como NaN (no se ocultan).
4. **QC físico.** Rangos plausibles por variable; hallazgo documentado: `fill_flag` es el
   **% de relleno (0–100)**, no la categórica (la categórica real es `cloud_fill_flag`).
5. **Codificación correcta de categóricas.** `cloud_type` (nominal) **no** se promedia
   como código: se usa **target/opacity encoding** (kt medio por tipo, ajustado solo en
   train) + fracción nublada. `nodo_id` **no** va one-hot; el nodo se describe con
   `lat/lon/msnm`.
6. **Descarte de fugas.** Se excluyen `ghi/dni/dhi` crudos en el instante objetivo y las
   UV (≈ función del ghi).
7. **Partición temporal (sin shuffle):** train **2020–2022**, val **2023**, test **2024**.

---

## 5. Metodología (reglas anti-fuga, obligatorias)

- **Anti-leakage por rol de variable:** DETERMINISTAS/known-future (clearsky_*, zenith,
  calendario) se usan en el instante objetivo τ; OBSERVADAS (meteo, aerosoles, nubes,
  ghi) solo **rezagadas** (`.shift(≥1)`).
- **Validación temporal** walk-forward (train→val→test por años), jamás shuffle.
- **Baseline obligatorio: smart persistence** `kt(t+1)=kt(t)`. Todo modelo debe lograr
  **skill > 0**. RMSE de referencia (GHI, test): **84.87 W/m²**.
- **Evaluación segmentada:** además del global, por **régimen de nubosidad** (despejado/
  parcial/cubierto), **régimen de rampa** (|Δkt|), **fill_flag** (limpio/rellenado) y
  **por nodo** — para ver dónde aporta el modelo (el skill global está diluido por horas
  fáciles).

---

## 6. Ingeniería de características (por tipo)

Detalle completo en `docs/catalogo_features.md`. Resumen:

| Tipo | Ejemplos | Rol |
|---|---|---|
| Deterministas (τ) | clearsky_*, zenith, hora/doy/mes + seno/coseno | esqueleto determinista known-future |
| Estáticas | lat, lon, msnm | describen el nodo (sin one-hot) |
| Observadas rezagadas | kt_lag{1,2,3,24}, meteo/aerosol/nube en τ-1 | estado reciente |
| Volatilidad | rampas Δkt, std/rango de kt | régimen inestable |
| Nocturno | medias/tendencias de meteo 12 h | informa la mañana |
| Viento | `wind_u`, `wind_v` (componentes), sin/cos dirección | corrige circularidad; base de advección |
| Cielo | fracción difusa `kd=dhi/ghi`, depresión de rocío `T−Td` | precursores de nubosidad |
| Nubes | opacity encoding de cloud_type, fracción nublada | categórica bien tratada |
| **Espaciales (advección)** | `kt_vecinos_mean_r2/r3`, gradientes, `kt_adveccion`, `kt_upwind`, nube espacial | **la física de "cuándo llega la nube"** |

**Física de la advección:** `∂kt/∂t ≈ −(u·∂kt/∂x + v·∂kt/∂y)`. Con viento típico
(~11–18 km/h), la nube que llega en 1 h está a ~10–18 km; por eso el vecindario de
radio 2 (~17 km) resultó la 2ª feature más importante — "ve venir" el campo nuboso.

---

## 7. Experimentos

Framework de experimentos **versionados** (código, dataset y resultados por carpeta,
reproducibles). Evolución del skill en **t+1** (test 2024):

| Experimento | Nodos | Novedad | Skill | RMSE |
|---|---|---|---|---|
| Baseline persistence | 1 | referencia | 0.000 | 84.87 |
| exp02/03 (single) | 1 | XGBoost + features base/nocturno | 0.061 | 79.7 |
| exp05 v1 | **25** | multi-nodo pooled (bloque 5×5) | 0.070 | 79.1 |
| exp05 v2 | **144** | escalar bloque (12×12) | 0.085 | 79.1 |
| exp06 | 144 | + viento (u/v) + cielo (difusa) | 0.086 | 79.0 |
| exp07 v1 | 144 | **+ advección espacial** | 0.111 | 76.8 |
| exp07 v2 | 144 | + nubes (opacity encoding) | 0.112 | 76.8 |
| exp07 v3 | 144 | + advección refinada (upwind, vecindario r2, nube espacial) | 0.121 | 75.9 |
| **exp07 v4** | **144** | + vecindario radio 3 | **0.127** | **75.4** |
| **exp08** | **25** | **multi-horizonte t+1…t+24 h operativas** | **0.244** (global) | 139.4 |

**Detalle de los experimentos multi-nodo (los principales):**
- **Bloque de prueba:** centrado en el nodo **1736 (Cd. Victoria)**. Se usaron **25
  nodos** (malla 5×5, ~16 km de lado) y **144 nodos** (12×12, ~50 km, incluye sierra y
  valle → diversidad de regímenes y altitudes 230–1482 m).
- **Modelo pooled:** un **único** XGBoost entrenado con todos los nodos del bloque; el
  nodo se describe con `lat/lon/msnm` (nunca con el id), de modo que un solo modelo
  generaliza a todos los nodos. El skill por nodo es **muy consistente** (144 nodos:
  0.11–0.13; los 25 nodos del exp08: 0.233–0.251).
- **Escalado:** de 1→25→144 nodos el skill subió 0.061→0.070→0.085; el gran salto
  posterior vino de las **features espaciales** (advección), no de más nodos.
- **Capacidad de la laptop (M5, 16 GB):** 144 nodos × 5 años (6.3 M filas) entrenan en
  ~40–56 s (pico ~6.8 GB); el multi-horizonte de 25 nodos (12.3 M filas) en ~35 s.

**Multi-horizonte (exp08):** horizontes en **horas operativas** (h = h-ésima hora de luz
futura). Como hay ~11.3 horas operativas/día, **h=24 ≈ 2 días de calendario**
(h≈11–12 ≈ 1 día). Un solo modelo directo con el horizonte como feature.

---

## 8. Resultados actuales

**Pronóstico a t+1 (mejor modelo, exp07 v4, 144 nodos):**
- Skill global **0.127** · RMSE **84.9 → 75.4 W/m²** · R² ~0.93.
- Por régimen: **rampa fuerte 0.218**, cubierto ya **positivo** (bate a persistence en
  cielo cubierto), parcial/despejado ~0.14. Las mejoras se concentran en los **episodios
  difíciles**, que era el objetivo.
- Features dominantes: `kt_lag1` (persistencia), `kt_vecinos_mean_r2` (contexto espacial),
  `cloud_op_vecinos_mean` (nube espacial).

**Pronóstico multi-horizonte (exp08, 25 nodos, t+1…t+24 h operativas):**
- Skill global **0.244** (RMSE 139.4 vs persistence 184.4).
- **Crece con el horizonte:** h=1 −0.08 (el modelo único no se especializa en el corto),
  h=6 0.25, **h=24 ~0.28** — persistence se vuelve inútil a 2 días y el modelo mantiene
  RMSE ~150 mientras persistence sube a ~208.
- Por mes 0.14 (jun, temporada convectiva) – 0.34 (ago); por nodo 0.233–0.251.

**Calidad de ingeniería:** paquete modular (`forecasting/`), **43 tests** (pytest) que
verifican anti-fuga, target/reconstrucción, features y métricas; portable a GPU (Ubuntu)
por autodetección de device.

---

## 9. Limitaciones

- **Resolución horaria:** una nube cruza en minutos; a 1 h solo se ve el kt promedio, no
  el instante del cruce. El techo de los "momentos al minuto" lo fija el dato.
- **h=1 en multi-horizonte:** el modelo directo único pierde contra persistence en el
  horizonte más corto (no se especializa). Se mitiga con modelos por horizonte.
- **Alcance espacial de la prueba:** 25–144 nodos (una zona), no toda la malla todavía.

---

## 10. Trabajo futuro (hoja de ruta)

1. **Escalar a todos los nodos (4384)** de Tamaulipas — modelo pooled de cobertura
   completa (en la máquina Ubuntu con GPU por memoria/cómputo).
2. **Migrar hacia modelos más expresivos** — modelos secuenciales que exploten la
   estructura temporal y la incertidumbre: **Temporal Fusion Transformer** (usa
   known-future clearsky, estáticas y da cuantiles), LSTM/GRU seq2seq; e **incorporar NWP**
   (HRRR/GFS) como covariable known-future, el gran lever para día-adelante.
3. **Implementación con GRAFOS (GNN).** Es la evolución natural de las features de
   advección: representar la malla de nodos como un **grafo** (nodos = celdas, aristas =
   vecindad/viento) y usar **Graph Neural Networks** (p.ej. graph spatio-temporal:
   GraphСast-like, GConvLSTM, ST-GNN). El GNN aprende la **propagación espacial de la
   nubosidad** de forma nativa, en vez de features de vecindario hechas a mano — es
   donde nuestros hallazgos (kt de vecinos + advección dominan) apuntan directamente.
4. **Refinamientos:** modelos por horizonte / cuantílico multi-horizonte (bandas de
   incertidumbre calibradas con conformal), y pronóstico probabilístico operativo.

---

## 11. Reproducibilidad

- Código: paquete `forecasting/` (config, target, features por bloques, modelos,
  evaluación, experimentos versionados, multihorizonte, tests). Entorno conda `rs`.
- Experimentos: `python -m forecasting.experiments.run <exp_id> [--version vN]`;
  multi-horizonte: `forecasting.multihorizonte.ejecutar(nodos)`.
- Artefactos por experimento: config, modelo, métricas (global/régimen/nodo/desglose),
  predicciones, resumen. Notebooks por experimento en `notebooks/experiments/`.
- Documentación por fase en `forecasting/docs/` (fase1…fase11) y catálogo de features.
