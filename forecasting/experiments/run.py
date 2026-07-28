"""
CLI para lanzar experimentos por id.

    python -m forecasting.experiments.run exp03_xgb_volatilidad
    python -m forecasting.experiments.run --listar
    python -m forecasting.experiments.run exp03_xgb_volatilidad --forzar-dataset

Escribe los artefactos en Results/<region>/forecast/experiments/<id>/<version>/.
"""
from __future__ import annotations
import argparse

from forecasting.experiments import Experimento, obtener, listar


def main() -> None:
    p = argparse.ArgumentParser(description="Lanza un experimento versionado.")
    p.add_argument("exp_id", nargs="?", help="id del experimento (ver --listar)")
    p.add_argument("--version", default=None, help="versión concreta (por defecto, la última)")
    p.add_argument("--listar", action="store_true", help="lista experimentos registrados")
    p.add_argument("--forzar-dataset", action="store_true",
                   help="reconstruye el dataset de features aunque exista en caché")
    args = p.parse_args()

    if args.listar or not args.exp_id:
        print("Experimentos registrados:")
        for eid in listar():
            print(" -", eid)
        return

    cfg = obtener(args.exp_id, args.version)
    print(f"Ejecutando {cfg.exp_id} ({cfg.version}) | bloques={list(cfg.bloques)}")
    res = Experimento(cfg).run(forzar_dataset=args.forzar_dataset)
    g = res["metrics_global"]
    g = g[(g.split == "test") & (g.segmento == "global")].iloc[0]
    print(f"OK -> {cfg.dir_salida}")
    print(f"Test global: RMSE {g.RMSE_modelo:.2f} vs persist {g.RMSE_persistence:.2f} "
          f"| skill {g.skill:.4f} | R2 {g.R2_modelo:.3f}")


if __name__ == "__main__":
    main()
