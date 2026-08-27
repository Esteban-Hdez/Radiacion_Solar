# Pronóstico de irradiancia solar (GHI) horaria — Tamaulipas

Pipeline de pronóstico de GHI horaria con XGBoost sobre datos NSRDB/NREL.
Objetivo: predecir GHI a **t+1** (luego **t+24**).

## Reglas metodológicas (obligatorias en todo el proyecto)

1. **Target = kt = ghi / clearsky_ghi** (índice de cielo despejado). El GHI se
   reconstruye como `kt_pred * clearsky_ghi`. Nunca se predice GHI crudo.
2. **Solo horas operativas**: `clearsky_ghi > 0` y `solar_zenith_angle < 85`.
   Las noches nunca son target.
3. **Validación temporal walk-forward**, jamás shuffle. Vigilar fuga temporal.
4. `nodo_id` **no** va one-hot; el nodo se describe con `lat/lon/msnm`.
   `cloud_type` tampoco va one-hot (orden por opacidad / target encoding).
5. **Baseline obligatorio: smart persistence** `kt(t+1)=kt(t)`. Todo modelo
   debe superarlo (forecast skill > 0).

La clave anti-leakage: distinguir variables **deterministas / known-future**
(usables en t+1: `clearsky_*`, `solar_zenith_angle`, hora, doy, lat/lon/msnm) de
las **observadas** (solo hasta t: `ghi`, `dni`, `cloud_type`, meteo, aerosoles,
UV → hay que rezagarlas). Ver `config.py`.

## Estructura

```
forecasting/
├── config.py                 # rutas, años, horas operativas, grupos anti-leakage
├── target.py                 # kt, máscara operativa, reconstruir GHI, split temporal
├── features/                 # feature-sets COMPONIBLES por bloques
│   ├── base.py               # META + bloque_base (35 features = Fase 3)
│   ├── volatilidad.py        # lags largos, rampas (Δkt), std/rango de kt
│   ├── nocturno.py           # agregados/tendencias de meteo 12 h (cubre la noche)
│   ├── viento.py             # viento en componentes u/v + sin/cos de la dirección
│   ├── cielo.py              # fracción difusa kd=dhi/ghi + depresión punto de rocío
│   ├── nubes.py              # cloud_type: opacity/target encoding (train) + fracción nublada
│   ├── adveccion.py          # ESPACIAL: vecinos/gradientes/advección + upwind semi-Lagrangiano (r2, nube espacial)
│   └── builder.py            # construir(df, bloques) single + construir_bloque multi-nodo
├── data/
│   ├── loaders.py            # cargar_serie_nodo (single) + cargar_bloque (multi-nodo, Data/) + calidad
│   ├── regiones.py           # bloques por REGIÓN de Tamaulipas + halo (entrena con halo, evalúa la región)
│   └── qc.py                 # selección de nodo + reporte QC + tabla fill_flag
├── multihorizonte.py         # t+1..t+24 horas operativas (directo, horizonte como feature)
├── models/
│   ├── xgb.py                # XGBoost kt(t+1) parametrizable, device autodetectado (cuda/cpu)
│   └── xgb_cuantilico.py     # XGBoost cuantílico P10/P50/P90 (base_score=0.5)
├── eval/
│   ├── metrics.py            # rmse, mae, mbe, r2, skill, evaluar (global + segmentada)
│   ├── persistence.py        # smart persistence kt(t+1)=kt(t), variantes A/B
│   ├── reporte.py            # tabla baseline split×variante×segmento + RMSE_ref
│   ├── comparar.py           # skill/R² modelo vs persistence sobre las mismas horas
│   ├── regimen.py            # métricas por régimen de nubosidad y de rampa
│   ├── cuantil.py            # pinball, cobertura, anchura (intervalo) global + régimen
│   └── desglose.py           # desglose rico multi-horizonte (horizonte/hora/mes/nodo/…)
├── experiments/             # framework de experimentos VERSIONADOS
│   ├── base.py               # ExperimentoConfig + Experimento (runner, puntual/cuantílico)
│   ├── registro.py           # catálogo (exp_id, version) -> config
│   ├── run.py                # CLI: python -m forecasting.experiments.run <id> [--version]
│   ├── reporte.py            # ReporteExperimento: carga artefactos para los notebooks
│   └── expNN_*.py            # exp02 base, exp03 volatilidad/nocturno, exp04 cuantílico,
│                             # exp09 regiones (bloques por región + halo)
├── viz.py                    # VisualizadorForecast (series, dispersión, días difíciles, intervalos)
├── tests/                   # pytest: anti-leakage, target, features, métricas, régimen, cuantil
└── docs/
    ├── fase1_qc.md … fase5_cuantilico.md   # bitácoras por fase
    ├── roadmap_episodios.md  # estrategia: foco en episodios difíciles
    └── hallazgo_fill_flag.md # procedencia y calidad del dato NSRDB: fill_flag (%),
                              # cloud_fill_flag (0-7), cómo se fabrica cada celda-hora,
                              # clearsky_* vía REST2 (NO es astronómico), y que la
                              # imputación se concentra en las rampas fuertes
notebooks/
├── 01_exploracion_qc.ipynb · 02_baseline_persistence.ipynb · 03_xgboost_t1.ipynb
└── experiments/             # un notebook por experimento (finos, vía ReporteExperimento)
    ├── exp02_xgb_base · exp03_xgb_volatilidad · exp04_xgb_cuantilico
    └── exp05_multinodo_victoria · exp06_viento_cielo · exp07_adveccion
```

### Portabilidad Ubuntu (GPU) / Mac (CPU)

El device de XGBoost se **autodetecta** (`nvidia-smi` → `cuda`, si no `cpu`).
Forzar con `RS_DEVICE=cpu|cuda`. Single-node corre en la Mac; multi-nodo en Ubuntu.

## Cómo ejecutar

Entorno conda **`rs`** (tiene pandas, numpy, pyarrow, xgboost-GPU, sklearn, pvlib, shap):

```bash
conda run -n rs python -m forecasting.data.qc          # QC completo + selección de nodo
conda run -n rs jupyter nbconvert --execute --to notebook --inplace notebooks/01_exploracion_qc.ipynb
```

## Datos

- Consolidados horarios en `Data/Tamaulipas/<AÑO>/Finales/completo/…parquet`.
- Años disponibles: **2017 y 2020–2024** (faltan 2018, 2019, 2025).
- Partición de arranque: train **2020–2022**, val **2023**, test **2024**.
- 4384 nodos, cadencia horaria UTC, 31 columnas.

## Estado

- **Fase 1 (QC/exploración)** — hecha. Ver `docs/fase1_qc.md`.
- **Fase 2 (baseline persistence)** — hecha. Ver `docs/fase2_baseline.md`.
  `RMSE_ref` (variante A, GHI): train 83.05 / val 84.63 / **test 84.87 W/m²**.
- **Fase 3 (primer XGBoost t+1)** — hecha. Ver `docs/fase3_xgboost.md`.
  Supera a persistence: **skill test 0.060** (RMSE 84.87 → 79.82 W/m²), skill>0 en
  todos los segmentos.
- **Fase 4 (framework de experimentos + experimento 1)** — hecha. Ver
  `docs/fase4_experimentos.md`. Experimentos versionados; evaluación por régimen.
  Experimento 1: `volatilidad` sobreajusta, `nocturno` marginal (exp03 v2, skill 0.061).
- **Fase 5 (notebooks por experimento + exp04 cuantílico)** — hecha. Ver
  `docs/fase5_cuantilico.md`. Un notebook por experimento; exp04 P10/P50/P90 (P50 skill
  0.054; banda se ensancha en nublado pero infracubierta → falta conformal).
- **Fase 6 (multi-nodo pooled)** — hecha. Ver `docs/fase6_multinodo.md`. exp05 v1:
  bloque 5×5 (25 nodos); skill 0.070 (+16 % vs single).
- **Fase 7 (viento/cielo + escalado 144 nodos)** — hecha. Ver
  `docs/fase7_viento_cielo_escalado.md`. exp05 v2 (144 nodos): **skill 0.085** (+21 %);
  exp06 (+viento+cielo): 0.086.
- **Fase 8 (advección espacial)** — hecha. Ver `docs/fase8_adveccion.md`. exp07 v1
  (+features espaciales): **skill 0.111** (+29 %), RMSE 84.9→76.8; mejora todos los
  regímenes. `kt_vecinos_mean` 3ª feature.
- **Fase 9 (codificación de cloud_type)** — hecha. Ver `docs/fase9_nubes_encoding.md`.
  exp07 v2 + bloque `nubes`: skill 0.112 (fix metodológico).
- **Fase 10 (advección refinada)** — hecha. Ver `docs/fase10_adveccion_refinada.md`.
  exp07 v3 + `adveccion_upwind` (upwind semi-Lagrangiano, vecindario r2, nube espacial):
  **skill 0.121**. exp07 **v4** + vecindario radio 3: **skill 0.127** (rendimientos
  decrecientes; r2 sigue dominando, rampa fuerte igual). RMSE 84.9→75.4.
- **Fase 11 (multi-horizonte t+1..t+24)** — hecha. Ver `docs/fase11_multihorizonte.md`.
  `multihorizonte.py` (directo, horizonte como feature) + `eval/desglose.py` (por
  horizonte/hora/mes/nodo/régimen/fill_flag/rangos). exp08 (25 nodos, 12.3 M filas):
  **skill global 0.244**; crece con el horizonte (h=24 ~0.28), h=1 pierde (no se
  especializa). ~35 s / 6.9 GB en la Mac.
- **Fase 12 (bloques por región + halo) — ESTADO COMPLETO** — hecha. Ver
  `docs/fase12_regiones.md`. El estado entero no cabe en RAM (219 GB con float32), así
  que se parte por las **6 regiones oficiales**: se entrena sobre `región + halo de 3
  celdas` y se evalúa solo sobre la región (sin halo, el 42 % de los nodos pierde el
  vecindario r2 completo). Los **4384 nodos** cubiertos en 22.5 min.
  Skill por región: Sur 0.165 · Centro 0.154 · Mante 0.151 · Valle de San Fernando
  0.148 · Fronteriza 0.146 · Altiplano 0.136. **Ningún nodo con skill negativo.**
  Pareado con exp07 v4 sobre 117 nodos comunes: **+0.011** (0.128 → 0.139), mejora en
  el 80 %. El relieve manda: skill ~ altitud **−0.687** entre regiones, y Altiplano
  necesita **1037** iteraciones frente a las 275 de Fronteriza.
  Rampa suave (−0.66 a −0.79) y cubierto (≈0) fallan **igual en las seis**: son
  déficits estructurales del enfoque, no de escala ni de partición.
- **Catálogo de features** por tipo: `docs/catalogo_features.md`.
- Siguiente: las otras 5 regiones + matriz de transferencia entre regiones; arreglar
  la rampa suave (skill −0.73 sobre el 68 % de las horas); NWP para día-adelante.

### Correr experimentos y tests

```bash
python -m forecasting.experiments.run --listar
python -m forecasting.experiments.run exp04_xgb_cuantilico
python -m pytest forecasting/tests/ -q
```
