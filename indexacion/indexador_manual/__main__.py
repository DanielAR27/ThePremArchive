"""Uso (desde la raíz del repo):

    python -m indexacion.indexador_manual build  --config indexacion/config/politica_A.conf [--limit N] [-p P]
    python -m indexacion.indexador_manual buscar --config indexacion/config/politica_A.conf [-k 10] consulta...
    python -m indexacion.indexador_manual info   indices/manual_A.idx
"""
import argparse


def main():
    ap = argparse.ArgumentParser(prog="indexador_manual", description="Indexador manual (PREMIDX)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="construye el índice de una política")
    b.add_argument("--config", required=True)
    b.add_argument("--limit", type=int, default=0, help="usar solo una muestra de N documentos")
    b.add_argument("-p", "--procesos", type=int, default=0, help="0 = lo que diga el .conf")
    b.add_argument("--desde-cero", action="store_true",
                   help="descarta el avance guardado de una ejecución interrumpida")

    q = sub.add_parser("buscar", help="consulta un índice")
    q.add_argument("--config", required=True)
    q.add_argument("--indice", default="", help="por defecto, la salida indicada en el .conf")
    q.add_argument("-k", type=int, default=10)
    q.add_argument("consulta", nargs="+")

    i = sub.add_parser("info", help="muestra la cabecera de un índice")
    i.add_argument("indice")

    args = ap.parse_args()
    if args.cmd == "build":
        from .construir import construir
        construir(args.config, args.limit, args.procesos, args.desde_cero)
    elif args.cmd == "buscar":
        from .buscar import buscar
        buscar(args.config, " ".join(args.consulta), args.indice, args.k)
    else:
        from .buscar import informacion
        informacion(args.indice)


if __name__ == "__main__":
    main()
