"""Construye varias políticas del indexador manual, una tras otra.

Uso (desde cualquier carpeta):
    python indexacion/herramientas/construir_indices.py             # las seis políticas: A B C D E F
    python indexacion/herramientas/construir_indices.py B C         # solo las que se indiquen
    python indexacion/herramientas/construir_indices.py --limit 3000    # muestra pequeña, para probar
    python indexacion/herramientas/construir_indices.py --simular   # muestra los comandos sin ejecutarlos

Se ejecutan en fila y no en paralelo: cada política ya usa todos los núcleos. Si algo se interrumpe,
volver a ejecutar el mismo comando continúa donde se quedó (ver README). Si una política falla, se detiene.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
POLITICAS = "ABCDEF"


def main():
    ap = argparse.ArgumentParser(description="Construye varias políticas del indexador manual, una tras otra.")
    ap.add_argument("politicas", nargs="*", default=list(POLITICAS), metavar="POLITICA",
                    help="letras de las políticas (por defecto: todas)")
    ap.add_argument("--limit", type=int, default=0, help="usar solo una muestra de N documentos")
    ap.add_argument("-p", "--procesos", type=int, default=0, help="cantidad de procesos (0 = lo que diga el .conf)")
    ap.add_argument("--desde-cero", action="store_true", help="descarta el avance guardado de ejecuciones interrumpidas")
    ap.add_argument("--simular", action="store_true", help="muestra los comandos sin ejecutarlos")
    args = ap.parse_args()

    elegidas = [p.upper() for p in args.politicas]
    for p in elegidas:
        if p not in POLITICAS:
            ap.error(f"política desconocida: {p} (válidas: {', '.join(POLITICAS)})")

    inicio = time.time()
    for p in elegidas:
        comando = [sys.executable, "-m", "indexacion.indexador_manual", "build",
                   "--config", str(RAIZ / "indexacion" / "config" / f"politica_{p}.conf")]
        if args.limit:
            comando += ["--limit", str(args.limit)]
        if args.procesos:
            comando += ["-p", str(args.procesos)]
        if args.desde_cero:
            comando.append("--desde-cero")
        print(f"\n=== Política {p} ===", flush=True)
        if args.simular:
            print(" ".join(comando))
            continue
        if subprocess.run(comando, cwd=RAIZ).returncode != 0:
            sys.exit(f"La política {p} no terminó; se detiene. Vuelve a ejecutar el mismo comando para continuar.")
    if not args.simular:
        print(f"\nListo: {len(elegidas)} política(s) en {(time.time() - inicio) / 60:.1f} min.")


if __name__ == "__main__":
    main()
