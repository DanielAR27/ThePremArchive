"""Levanta The Prem Archive:  python -m web_app   (desde la raíz del repo)

Arranca el servicio de búsqueda de Lucene (si no está ya corriendo y existe el .jar) y la aplicación web en
http://127.0.0.1:5000. Con --sin-lucene usa solo el índice propio en Python.
"""
import argparse
import atexit
import subprocess
import sys
import time

from . import config
from .app import crear_app
from .buscador import Buscador


def levantar_lucene(buscador: Buscador):
    if buscador.lucene_disponible():
        print("Servicio de Lucene ya estaba corriendo.")
        return None
    if not config.JAR.exists():
        print(f"No encontré {config.JAR}: se usará el índice propio. Compilar con: cd indexacion/indexador_lucene && mvn -q package")
        return None
    print("Iniciando el servicio de búsqueda de Lucene...")
    proceso = subprocess.Popen(
        ["java", "-jar", str(config.JAR), "servir", "--config", str(config.POLITICA), "--puerto", str(config.PUERTO_LUCENE)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    atexit.register(proceso.terminate)
    for _ in range(60):
        if proceso.poll() is not None:
            print("El servicio de Lucene se cerró al iniciar; se usará el índice propio.")
            return None
        if buscador.lucene_disponible():
            print("Lucene listo.")
            return proceso
        time.sleep(1)
    print("Lucene no respondió a tiempo; se usará el índice propio.")
    return proceso


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-lucene", action="store_true", help="no iniciar Lucene; buscar con el índice propio")
    ap.add_argument("--puerto", type=int, default=config.PUERTO_WEB)
    args = ap.parse_args()
    if not args.sin_lucene:
        levantar_lucene(Buscador())
    app = crear_app()
    print(f"The Prem Archive en http://127.0.0.1:{args.puerto}")
    app.run(host="127.0.0.1", port=args.puerto, threaded=True)


if __name__ == "__main__":
    sys.exit(main())
