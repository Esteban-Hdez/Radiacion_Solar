# Utils/legacy — scripts históricos (un solo uso / tareas específicas)

Scripts del **armado inicial** de las mallas y datasets (sobre todo Tamaulipas 2017)
y mapas puntuales que quedaron **superados** por las herramientas activas. Se
conservan como referencia y reproducibilidad; **no** forman parte del flujo actual.

> Flujo activo (en `Utils/`):
> - Descarga por región/año → **`Utils/descarga_regiones/`** (ver `GUIA_COMANDOS.md`).
> - Mapas estáticos de cualquier variable → **`Utils/mapas_espaciales.py`**.
> - Mapa interactivo / selección de nodos → **`Utils/mapa_interactivo.py`**, **`Utils/seleccion_lasso.py`**.

## Contenido

| Script | Qué hacía | Reemplazado por |
|---|---|---|
| `generar_malla_tamaulipas.py` | generó la malla de Tamaulipas (paso 0.038°, origen del desfase) | malla final confirmada por API |
| `descarga_masiva_tamaulipas.py` | descarga masiva 2017 (4940 nodos) | `Utils/descarga_regiones/descargar_anio.py` |
| `parche_tamaulipas_v4.py` | re-descarga de nodos con falla de red (2017) | `Utils/descarga_regiones/parche_anio.py` |
| `verificar_alineacion_espacial.py` | consultó a la API las coords reales por nodo | metadata real ya consolidada |
| `completar_nodos_faltantes_tamaulipas.py` | completó coords de nodos con `lat=0` | — |
| `reconstruir_coordenadas_grid.py` | reconstrucción matemática de la rejilla | coords confirmadas por API |
| `graficar_malla_reconstruida.py` | gráfico de verificación de la malla | — |
| `deduplicar_dataset_tamaulipas.py` | quitó duplicados de celda (2017) | dedup ya integrado en el pipeline |
| `consolidar_tamaulipas_completo.py` | consolidó los crudos 2017 | `Utils/descarga_regiones/consolidar_anio.py` |
| `filtrar_nodos_tamaulipas.py` | quitó nodos de mar y reindexó (2017) | — |
| `identificar_nodos_mar_tamaulipas.py` | detectó nodos sobre agua por `msnm==0` | `Utils/seleccion_lasso.py` (interactivo) |
| `mapa_ghi_tamaulipas.py` | mapa puntual de GHI | `Utils/mapas_espaciales.py` |
| `mapa_radiacion_tamaulipas.py` | mapa puntual de radiación | `Utils/mapas_espaciales.py` |
| `mapa_radiacion_tamaulipas_12meses.py` | panel 12 meses de radiación | `Utils/mapas_espaciales.py --panel12` |
| `radiacion_diaria_promedio_tamaulipas.py` | radiación media diaria | `Utils/mapas_espaciales.py --agregacion suma_diaria` |

Las carpetas `Utils/puerto_rico_v3_2017/` y `Utils/puerto_rico_v4_2017/` son también
del armado histórico de Puerto Rico (se mantienen aparte porque un notebook aún
importa de ellas).
