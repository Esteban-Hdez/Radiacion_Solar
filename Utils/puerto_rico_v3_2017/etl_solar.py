import os
import h5py
import numpy as np
import pandas as pd
from scipy import stats

# ==========================================
# 1. Funciones de Lectura y Extracción
# ==========================================
def obtener_ejes_espaciotemporales(f):
    """Extrae el índice de tiempo (a nivel horario) y los IDs de los nodos."""
    time_index_completo = pd.to_datetime(f['time_index'][:].astype(str))
    
    # Tomamos solo el primer registro de cada bloque de 12 (Minuto 00)
    time_index_1h = time_index_completo[::12] 
    
    nodos_ids = pd.DataFrame(f['meta'][:]).index.values
    return time_index_1h, nodos_ids

def leer_variable_cruda(f, var_name):
    """Lee una variable del HDF5. Retorna None si no existe."""
    if var_name not in f.keys():
        return None
        
    dataset = f[var_name]
    scale_factor = dataset.attrs.get('psm_scale_factor', 1.0)
    
    return (dataset[:] / scale_factor).astype(np.float32)

# ==========================================
# 2. Funciones de Cálculo Matemático Vectorizado
# ==========================================
def calcular_metricas_horarias(matriz_cruda, regla):
    """
    Transforma la matriz de (PasosTotales, Nodos) a (Horas, 12, Nodos)
    y aplica la regla matemática correspondiente en el eje de los 5 minutos (axis=1).
    """
    n_horas = matriz_cruda.shape[0] // 12
    n_nodos = matriz_cruda.shape[1]
    
    # Remodelar a 3D: (Hora, Registro_Intrahorario, Nodo)
    matriz_3d = matriz_cruda.reshape((n_horas, 12, n_nodos))
    
    if regla == 'promedio':
        return np.nanmean(matriz_3d, axis=1)
    
    elif regla == 'maximo':
        return np.nanmax(matriz_3d, axis=1)
    
    elif regla == 'minuto_30':
        # El minuto 30 corresponde al índice 6 (00, 05, 10, 15, 20, 25, *30*)
        return matriz_3d[:, 6, :]
    
    elif regla == 'moda':
        # Scipy calcula la moda y devuelve un objeto; extraemos la matriz de modas
        resultado_moda = stats.mode(matriz_3d, axis=1, keepdims=False)
        return resultado_moda.mode
    
    else:
        raise ValueError(f"Regla no soportada: {regla}")

# ==========================================
# 3. Función Principal Orquestadora
# ==========================================
def procesar_nsrdb_anual(h5_path, output_dir, formato_salida='parquet'):
    """
    Ejecuta todas las reglas de negocio sobre un archivo HDF5 anual y lo exporta.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(h5_path)
    year = filename.split('_')[-1].split('.')[0]
    
    print(f"\n--- Iniciando ingeniería de características para el año {year} ---")
    
    datos_procesados = {}
    
    with h5py.File(h5_path, 'r') as f:
        time_index_1h, nodos_ids = obtener_ejes_espaciotemporales(f)
        n_horas = len(time_index_1h)
        n_nodos = len(nodos_ids)
        
        # Regla 1: Promedios aritméticos simples
        variables_promedio = ['ghi', 'dni', 'dhi', 'clearsky_ghi', 'air_temperature', 
                              'surface_pressure', 'wind_speed', 'total_precipitable_water']
        for var in variables_promedio:
            crudo = leer_variable_cruda(f, var)
            if crudo is not None:
                datos_procesados[var] = calcular_metricas_horarias(crudo, 'promedio')
            else:
                print(f"⚠️ Variable omitida (No existe): {var}")
            
        # Reglas Condicionales (Verifican existencia)
        
        # Regla 2: Moda
        crudo_cloud_type = leer_variable_cruda(f, 'cloud_type')
        if crudo_cloud_type is not None:
            datos_procesados['cloud_type'] = calcular_metricas_horarias(crudo_cloud_type, 'moda')
        
        # Regla 3: Minuto 30
        crudo_zenith = leer_variable_cruda(f, 'solar_zenith_angle')
        if crudo_zenith is not None:
            datos_procesados['solar_zenith_angle'] = calcular_metricas_horarias(crudo_zenith, 'minuto_30')
        
        # Regla 4: Máximo intrahorario
        crudo_opacity = leer_variable_cruda(f, 'cloud_opacity')
        if crudo_opacity is not None:
            datos_procesados['cloud_opacity'] = calcular_metricas_horarias(crudo_opacity, 'maximo')
        
        # Regla 5: Humedad Relativa
        crudo_rh = leer_variable_cruda(f, 'relative_humidity')
        if crudo_rh is not None:
            datos_procesados['RH_Promedio_Horario'] = calcular_metricas_horarias(crudo_rh, 'promedio')
            datos_procesados['RH_Max_Intrahorario'] = calcular_metricas_horarias(crudo_rh, 'maximo')

    print("Calculo matricial completado. Aplanando arreglos para ensamblar Dataset...")
    
    # Ensamblaje
    timestamps_rep = np.repeat(time_index_1h.values, n_nodos)
    nodos_tile = np.tile(nodos_ids, n_horas)
    
    df_dict = {
        'timestamp': timestamps_rep,
        'nodo_id': nodos_tile
    }
    
    for nombre_columna, matriz_2d in datos_procesados.items():
        df_dict[nombre_columna] = matriz_2d.flatten()
        
    df_final = pd.DataFrame(df_dict)
    
    print("Aplicando reglas de tiempo y filtros astronómicos...")
    df_final['hora'] = df_final['timestamp'].dt.hour.astype(np.int8)
    df_final['mes'] = df_final['timestamp'].dt.month.astype(np.int8)
    
    # Regla 8: Doble Filtro de Día (Asegurar que clearsky_ghi existe para filtrar)
    if 'clearsky_ghi' in df_final.columns and 'solar_zenith_angle' in df_final.columns:
        mask_diurno = (df_final['clearsky_ghi'] > 0) & (df_final['solar_zenith_angle'] < 85)
        df_filtrado = df_final[mask_diurno].reset_index(drop=True)
    else:
        print("⚠️ No se pudo aplicar el filtro diurno por falta de variables base.")
        df_filtrado = df_final
    
    # Guardado
    if formato_salida == 'parquet':
        out_file = os.path.join(output_dir, f'nsrdb_pr_preprocesado_{year}.parquet')
        df_filtrado.to_parquet(out_file, engine='pyarrow', index=False)
    else:
        out_file = os.path.join(output_dir, f'nsrdb_pr_preprocesado_{year}.csv')
        df_filtrado.to_csv(out_file, index=False)
        
    print(f"✅ Archivo guardado: {out_file}")
    
    return True