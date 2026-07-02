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
├── data/
│   ├── loaders.py            # cargar nodo multi-año (índice horario contiguo) + calidad
│   └── qc.py                 # selección de nodo + reporte QC + tabla fill_flag
└── docs/
    ├── fase1_qc.md           # bitácora y hallazgos de la Fase 1
    └── hallazgo_fill_flag.md # qué es fill_flag (% de relleno), fuentes e implicaciones
notebooks/
└── 01_exploracion_qc.ipynb   # notebook de la fase de exploración/QC
```

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
- Fase 2 (baseline persistence), Fase 3 (features + XGBoost), … — pendientes.
