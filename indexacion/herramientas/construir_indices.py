"""Construye varias políticas con el indexador manual, con Lucene o con los dos, una tras otra.

Uso (desde cualquier carpeta):
    python indexacion/herramientas/construir_indices.py             # las seis políticas: A B C D E F
    python indexacion/herramientas/construir_indices.py B C         # solo las que se indiquen
    python indexacion/herramientas/construir_indices.py --limit 3000    # muestra pequeña, para probar
    python indexacion/herramientas/construir_indices.py --simular   # muestra los comandos sin ejecutarlos
    python indexacion/herramientas/construir_indices.py --motor lucene A B C   # solo Lucene (compilar antes con mvn)
    python indexacion/herramientas/construir_indices.py --motor ambos          # manual y Lucene de cada política

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
JAR = RAIZ / "indexacion" / "indexador_lucene" / "target" / "indexador-lucene.jar"


def main():
    ap = argparse.ArgumentParser(description="Construye varias políticas, una tras otra.")
    ap.add_argument("politicas", nargs="*", default=list(POLITICAS), metavar="POLITICA",
                    help="letras de las políticas (por defecto: todas)")
    ap.add_argument("--limit", type=int, default=0, help="usar solo una muestra de N documentos")
    ap.add_argument("-p", "--procesos", type=int, default=0,
                    help="procesos del manual / hilos de Lucene (0 = lo que diga el .conf)")
    ap.add_argument("--desde-cero", action="store_true", help="descarta el avance guardado de ejecuciones interrumpidas")
    ap.add_argument("--simular", action="store_true", help="muestra los comandos sin ejecutarlos")
    ap.add_argument("--motor", choices=("manual", "lucene", "ambos"), default="manual",
                    help="qué indexador usar (por defecto: manual)")
    args = ap.parse_args()

    elegidas = [p.upper() for p in args.politicas]
    for p in elegidas:
        if p not in POLITICAS:
            ap.error(f"política desconocida: {p} (válidas: {', '.join(POLITICAS)})")
    motores = ("manual", "lucene") if args.motor == "ambos" else (args.motor,)
    if "lucene" in motores and not args.simular and not JAR.exists():
        sys.exit(f"No existe {JAR}: compilar antes con  cd indexacion/indexador_lucene && mvn -q package")

    inicio = time.time()
    for p in elegidas:
        conf = str(RAIZ / "indexacion" / "config" / f"politica_{p}.conf")
        for motor in motores:
            if motor == "manual":
                comando = [sys.executable, "-m", "indexacion.indexador_manual", "build", "--config", conf]
                if args.procesos:
                    comando += ["-p", str(args.procesos)]
                if args.desde_cero:
                    comando.append("--desde-cero")
            else:
                comando = ["java", "-jar", str(JAR), "build", "--config", conf]
                if args.procesos:
                    comando += ["-t", str(args.procesos)]
            if args.limit:
                comando += ["--limit", str(args.limit)]
            print(f"\n=== Política {p} ({motor}) ===", flush=True)
            if args.simular:
                print(" ".join(comando))
                continue
            if subprocess.run(comando, cwd=RAIZ).returncode != 0:
                sys.exit(f"La política {p} ({motor}) no terminó; se detiene. "
                         "Vuelve a ejecutar el mismo comando para continuar.")
    if not args.simular:
        print(f"\nListo: {len(elegidas)} política(s) x {len(motores)} indexador(es) en "
              f"{(time.time() - inicio) / 60:.1f} min.")


if __name__ == "__main__":
    main()
