# Fase 4 — Framework de experimentos + Experimento 1 (volatilidad/nocturno)

## Arquitectura (para no mezclar experimentos y reproducir cualquier versión)

Separación limpia entre **librería reutilizable** y **definición de experimentos**:

```
forecasting/
├── features/                 # feature-sets COMPONIBLES por bloques
│   ├── base.py               # META + bloque_base (35 features = Fase 3)
│   ├── volatilidad.py        # lags largos, rampas (Δkt), std/rango de kt
│   ├── nocturno.py           # agregados/tendencias de meteo 12 h (cubre la noche)
│   └── builder.py            # construir(df, bloques) + columnas_features
├── eval/
│   └── regimen.py            # métricas por régimen de nubosidad y de rampa
├── models/xgb.py             # entrenar(feat, cols, params, ...) parametrizable
└── experiments/
    ├── base.py               # ExperimentoConfig (dataclass) + Experimento (runner)
    ├── registro.py           # catálogo (exp_id, version) -> config
    ├── run.py                # CLI: python -m forecasting.experiments.run <id> [--version]
    ├── exp02_xgb_base.py     # CONFIGS (una por versión)
    └── exp03_xgb_volatilidad.py
```

**Reproducibilidad por carpetas** (nada se mezcla):

```
Results/<region>/forecast/experiments/
├── datasets/<feature_set_id>/nodo<ID>.parquet     # dataset cacheado por feature-set
└── <exp_id>/<version>/
    ├── config.json            # config exacta + n_features + best_iteration
    ├── model.json             # modelo XGBoost serializado
    ├── metrics_global.csv      # val+test, global + por fill_flag, con R² y skill
    ├── metrics_regimen_nubosidad.csv
    ├── metrics_regimen_rampa.csv
    ├── feature_importance.csv
    ├── predictions_test.parquet
    └── summary.md             # resumen legible
```

Lanzar / reproducir:

```bash
python -m forecasting.experiments.run --listar
python -m forecasting.experiments.run exp03_xgb_volatilidad --version v2
```

Feature-set identificado por sus bloques (`base-nocturno`, …); el dataset se cachea y
se reutiliza entre experimentos que comparten feature-set. `--forzar-dataset` lo
reconstruye.

## Experimento 1 — `exp03_xgb_volatilidad`

**Hipótesis:** volatilidad/rampas + historia nocturna mejoran los episodios.

**Ablación (test 2024):**

| feature-set | nfeat | RMSE | skill global | skill rampa fuerte |
|-------------|-------|------|--------------|--------------------|
| base (exp02) | 35 | 79.82 | 0.0596 | 0.153 |
| base+volatilidad | 48 | 80.22 | 0.0548 | 0.148 |
| **base+nocturno** | 45 | **79.70** | **0.0610** | **0.156** |
| base+vol+noct (v1) | 58 | 80.24 | 0.0545 | 0.153 |

**Conclusión:** `volatilidad` (lags largos, rampas, rolling std) **sobreajusta** a
resolución horaria single-node y empeora. `nocturno` (meteo trailing 12 h) **aporta
marginalmente** (skill 0.060→0.061 y rampas fuertes 0.153→0.156). Config retenida:
**v2 = base + nocturno**. El resultado (mejora pequeña) refuerza el roadmap: los levers
grandes para episodios son **espaciales (upwind/advección)** y **pérdida cuantílica**,
no más lags locales.

## Métricas por régimen (exp02 base, test) — dónde aporta el ML

- Rampa fuerte (>0.25): **skill +0.15** (aquí sí ayuda el modelo).
- Rampa suave (<0.1): skill −0.69 (persistence casi perfecta en horas planas).
- Cielo cubierto estable (kt<0.3): skill negativo (el modelo sobrepasa).

## Testing

`forecasting/tests/` (pytest, 14 tests): anti-leakage (features en τ no usan observadas
crudas; los lags miran atrás), target/reconstrucción de GHI, composición de bloques,
métricas y clasificación por régimen. Corre con:

```bash
python -m pytest forecasting/tests/ -q
```

## Siguiente

exp04 (XGBoost cuantílico) en la Mac; exp05 (features espaciales upwind) en la Ubuntu.
Ver `roadmap_episodios.md`.
