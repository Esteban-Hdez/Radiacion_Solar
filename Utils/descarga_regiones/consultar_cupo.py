"""
Consulta el cupo restante de la API de descarga NSRDB.

El endpoint de descarga responde con un 302 (redirección a S3) que lleva las
cabeceras de rate-limit de api.data.gov:
    X-Ratelimit-Limit       -> límite diario (10000 para este endpoint)
    X-Ratelimit-Remaining   -> peticiones restantes hoy

Cada consulta CUESTA 1 petición. Ejecutar:
    python -m Utils.descarga_regiones.consultar_cupo
"""

import requests
from Utils.descarga_regiones._comun import URL_BASE, cargar_credenciales


def cupo():
    """Devuelve (limite, restantes) como int, o (None, None) si no vienen."""
    api_key, email = cargar_credenciales()
    params = {
        'api_key': api_key, 'email': email,
        'wkt': 'POINT(-97.9 22.25)', 'names': '2024',
        'attributes': 'ghi', 'interval': '60', 'utc': 'true', 'leap_day': 'false',
    }
    # stream=True: leemos solo cabeceras, sin descargar el cuerpo del archivo.
    r = requests.get(URL_BASE, params=params, stream=True, timeout=30)
    headers = r.history[0].headers if r.history else r.headers   # el 302 trae el cupo
    r.close()
    lim = headers.get('X-Ratelimit-Limit')
    rem = headers.get('X-Ratelimit-Remaining')
    return (int(lim) if lim else None, int(rem) if rem else None)


if __name__ == "__main__":
    lim, rem = cupo()
    if rem is None:
        print("No se encontraron cabeceras de rate-limit en la respuesta.")
    else:
        print(f"Cupo NSRDB (hoy): {rem:,} / {lim:,} restantes  ·  usadas: {lim - rem:,}")
