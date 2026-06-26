import os
import time
import pandas as pd

def aplicar_filtros_astronomicos():
    ruta_entrada = 'Data/Puerto_Rico_v4_2017/Finales/completo/dataset_maestro_v4_2017_completo.parquet'
    ruta_salida = 'Data/Puerto_Rico_v4_2017/Finales/filtrado/dataset_v4_filtrado_diurno_2017.parquet'
    
    print("=== INICIANDO PIPELINE DE FILTRADO FÍSICO (V4) ===")
    inicio = time.time()
    
    # 1. Cargar el dataset maestro
    print("Cargando dataset maestro a memoria RAM...")
    df = pd.read_parquet(ruta_entrada)
    filas_originales = len(df)
    
    # 2. Definir las variables estrictamente necesarias con los NOMBRES CORRECTOS (V4)
    columnas_objetivo = [
        'nodo_id', 'year', 'month', 'day', 'hour',
        'ghi', 'dni', 'dhi', 'clearsky_ghi', 
        'temperature',          # Antes air_temperature
        'pressure',             # Antes surface_pressure
        'wind_speed', 
        'precipitable_water',   # Antes total_precipitable_water
        'cloud_type', 
        'solar_zenith_angle', 
        'relative_humidity'     # cloud_opacity eliminado por no existir en V4
    ]
    
    print("Seleccionando atributos y descartando variables innecesarias...")
    df = df[columnas_objetivo].copy()
    
    # Renombrar la humedad relativa según tus instrucciones
    df.rename(columns={'relative_humidity': 'RH_Promedio_Horario'}, inplace=True)
    
    # ==========================================
    # Creación de la columna DateTime
    # ==========================================
    print("Generando índice temporal unificado (DateTime)...")
    df['datetime'] = pd.to_datetime(df[['year', 'month', 'day', 'hour']])
    
    # Reordenar las columnas para poner 'datetime' justo después de 'nodo_id'
    columnas_ordenadas = ['nodo_id', 'datetime'] + [col for col in df.columns if col not in ['nodo_id', 'datetime']]
    df = df[columnas_ordenadas]
    
    # 3. Aplicar el DOBLE FILTRO (Horas diurnas)
    print("Aplicando doble filtro astronómico...")
    df_filtrado = df[(df['clearsky_ghi'] > 0) & (df['solar_zenith_angle'] < 85)].copy()
    
    # Ordenar espaciotemporalmente
    df_filtrado.sort_values(by=['nodo_id', 'datetime'], inplace=True, ignore_index=True)
    
    # 4. Guardar el archivo definitivo
    print(f"Escribiendo dataset filtrado en: {ruta_salida}")
    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)
    df_filtrado.to_parquet(ruta_salida, engine='pyarrow', index=False)
    
    # Bloque de Validación
    filas_finales = len(df_filtrado)
    porcentaje_retenido = (filas_finales / filas_originales) * 100
    tiempo_total = time.time() - inicio
    
    print("\n" + "="*50)
    print("✅ REPORTE DE FILTRADO")
    print("="*50)
    print(f"Tiempo de cómputo:   {tiempo_total:.2f} segundos")
    print(f"Filas originales:    {filas_originales:,}")
    print(f"Filas retenidas:     {filas_finales:,} ({porcentaje_retenido:.1f}% del total)")
    print(f"Filas eliminadas:    {filas_originales - filas_finales:,} (Horas nocturnas y ángulos > 85°)")
    print(f"Total de columnas:   {len(df_filtrado.columns)}")
    print("="*50 + "\n")
    
    print("Vista de las primeras filas:")
    print(df_filtrado.head())

if __name__ == "__main__":
    aplicar_filtros_astronomicos()