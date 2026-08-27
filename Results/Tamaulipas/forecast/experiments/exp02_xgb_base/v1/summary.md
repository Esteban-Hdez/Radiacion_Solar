# exp02_xgb_base — v1

XGBoost t+1 con feature-set base (lags kt 1/2/3/24 + kt_last_op + deterministas known-future + estáticas + observadas lag1). Reproduce la Fase 3; referencia para el resto de experimentos.

- Alcance: nodo 1736 | feature-set: `base` (35 features) | best_iteration: 226
- Bloques: ['base'] | modelo: xgboost | cuantiles: —

**Test global (P50 si cuantílico):** RMSE 79.78 vs persistence 84.87 W/m² · skill 0.0600 · R² 0.926

## Métricas globales (val + test)

| segmento         |    n |   RMSE_persistence |   RMSE_modelo |   MAE_modelo |   MBE_modelo |   R2_persistence |   R2_modelo |   skill | split   |
|:-----------------|-----:|-------------------:|--------------:|-------------:|-------------:|-----------------:|------------:|--------:|:--------|
| global           | 4112 |             84.625 |        77.271 |       42.054 |        3.144 |            0.921 |       0.935 |   0.087 | val     |
| limpio_ff0       | 3712 |             86.679 |        79.03  |       42.737 |        2.342 |            0.912 |       0.927 |   0.088 | val     |
| rellenado_ff_pos |  400 |             62.425 |        58.471 |       35.714 |       10.593 |            0.89  |       0.903 |   0.063 | val     |
| global           | 4123 |             84.873 |        79.783 |       46.515 |        1.375 |            0.916 |       0.926 |   0.06  | test    |
| limpio_ff0       | 3734 |             86.482 |        81.511 |       47.81  |        1.477 |            0.906 |       0.917 |   0.057 | test    |
| rellenado_ff_pos |  389 |             67.497 |        60.747 |       34.087 |        0.396 |            0.887 |       0.908 |   0.1   | test    |

## Por régimen de nubosidad (test)

| regimen_nubosidad   |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| cubierto (kt<0.3)   |  286 |       143.909 |            135.642 |      103.709 |      -3.754 |  -0.061 |
| parcial (0.3-0.7)   |  708 |       115.857 |            127.541 |       79.742 |       0.524 |   0.092 |
| despejado (kt>=0.7) | 3129 |        58.799 |             64.26  |       33.769 |       0.954 |   0.085 |

## Por régimen de rampa (test)

| regimen_rampa             |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| rampa suave (<0.1)        | 2818 |        39.538 |             23.286 |       24.887 |       0.981 |  -0.698 |
| rampa moderada (0.1-0.25) |  817 |        93.449 |             97.163 |       71.547 |       0.864 |   0.038 |
| rampa fuerte (>0.25)      |  487 |       173.761 |            204.961 |      129.712 |       0.383 |   0.152 |

## Top 15 importancias (gain)

|                         |      0 |
|:------------------------|-------:|
| kt_lag1                 | 0.3859 |
| kt_last_op              | 0.1793 |
| cloud_type_lag1         | 0.0535 |
| cos_hour                | 0.0307 |
| cloud_fill_flag_lag1    | 0.0202 |
| hour                    | 0.017  |
| temperature_lag1        | 0.0154 |
| wind_direction_lag1     | 0.015  |
| sin_hour                | 0.0147 |
| clearsky_dhi            | 0.014  |
| clearsky_ghi            | 0.0137 |
| clearsky_dni            | 0.0137 |
| relative_humidity_lag1  | 0.0135 |
| solar_zenith_angle      | 0.0131 |
| precipitable_water_lag1 | 0.0129 |
