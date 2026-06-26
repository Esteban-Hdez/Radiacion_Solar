import os
import time
import shutil
import pandas as pd
import pyarrow.dataset as ds

def consolidar_y_limpiar_v4():
    # Rutas
    dir_nodos = 'Data/Puerto_Rico_v4_2017/crudos_api/2017_V4_Completo'
    archivo_maestro = 'Data/Puerto_Rico_v4_2017/Finales/completo/dataset_maestro_v4_2017_completo.parquet'
    
    print("=== FASE 1: CONSOLIDACIÓN DE DATOS V4 ===")
    inicio = time.time()
    
    # 1. Escanear y cargar todos los archivos Parquet en un solo movimiento
    print(f"Escaneando directorio: {dir_nodos}...")
    dataset = ds.dataset(dir_nodos, format="parquet")
    df_maestro = dataset.to_table().to_pandas()
    
    # 2. Normalizar nombres de columnas (snake_case)
    print("Normalizando esquema de columnas...")
    df_maestro.columns = df_maestro.columns.str.strip().str.lower().str.replace(' ', '_')
    
    # 3. Guardar el archivo consolidado
    print(f"Escribiendo Dataset Maestro: {archivo_maestro}")
    df_maestro.to_parquet(archivo_maestro, engine='pyarrow', index=False)
    
    tiempo_escritura = time.time() - inicio
    
    # ==========================================
    # FASE 2: VALIDACIÓN ESTRICTA
    # ==========================================
    print("\n=== FASE 2: VALIDACIÓN DE INTEGRIDAD ===")
    filas_esperadas = 2480 * 8760  # 21,724,800
    filas_reales = len(df_maestro)
    
    print(f"Filas obtenidas: {filas_reales:,}")
    print(f"Filas esperadas: {filas_esperadas:,}")
    
    if filas_reales == filas_esperadas:
        print("✅ VALIDACIÓN PERFECTA. Integridad espaciotemporal al 100%.")
        
        # ==========================================
        # FASE 3: LIMPIEZA DEL DISCO
        # ==========================================
        print("\n=== FASE 3: LIMPIEZA DE ARCHIVOS TEMPORALES ===")
        confirmacion = input(f"¿Deseas eliminar los 2,480 archivos individuales de {dir_nodos}? (s/n): ")
        
        if confirmacion.lower() == 's':
            print("Eliminando archivos temporales...")
            shutil.rmtree(dir_nodos) # Borra la carpeta y su contenido
            print(f"✅ Carpeta {dir_nodos} eliminada con éxito.")
        else:
            print("Archivos individuales conservados por instrucción del usuario.")
            
    else:
        print("\n❌ ADVERTENCIA: La cantidad de filas no coincide.")
        print("La limpieza automática ha sido ABORTADA para proteger los datos.")
        print("Por favor, revisa si el script de descarga fue interrumpido.")

    print(f"\nTiempo total de la operación: {tiempo_escritura:.2f} segundos.")

if __name__ == "__main__":
    consolidar_y_limpiar_v4()