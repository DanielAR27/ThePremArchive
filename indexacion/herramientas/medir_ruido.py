"""Mide cuánto del índice son términos "ruido": números, alfanuméricos y términos de df bajo.

Uso (desde la raíz del repo):
    python indexacion/herramientas/medir_ruido.py indices/manual_A.idx [indices/manual_B.idx ...]
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from indexacion.indexador_manual.buscar import Indice
from indexacion.indexador_manual.formato import codificar_varint

_NUMERO = re.compile(r"\d+(?:\.\d+)?")
_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")
_ANIO = re.compile(r"(18[5-9]\d|19\d\d|20[0-3]\d)")

CATEGORIAS = {
    "fecha normalizada": lambda t, df: bool(_FECHA.fullmatch(t)),
    "año (1850-2039)": lambda t, df: bool(_ANIO.fullmatch(t)),
    "número de 1-3 dígitos": lambda t, df: bool(_NUMERO.fullmatch(t)) and len(t) <= 3,
    "número de 4+ dígitos (no año)": lambda t, df: bool(_NUMERO.fullmatch(t)) and len(t) > 3
                                                   and not _ANIO.fullmatch(t),
    "letras y dígitos mezclados": lambda t, df: any(c.isdigit() for c in t) and any(c.isalpha() for c in t),
    "df = 1": lambda t, df: df == 1,
    "df <= 2": lambda t, df: df <= 2,
    "término de 1 letra": lambda t, df: len(t) == 1 and t.isalpha(),
}


def medir(ruta):
    ind = Indice(ruta)
    total = {"terminos": 0, "postings": 0, "bytes": 0}
    por_cat = {c: {"terminos": 0, "postings": 0, "bytes": 0, "ejemplos": []} for c in CATEGORIAS}
    for termino, (df, _, plen) in ind.diccionario.items():
        bytes_t = 1 + len(termino.encode("utf-8")) + len(codificar_varint(df)) + len(codificar_varint(plen)) + plen
        total["terminos"] += 1
        total["postings"] += df
        total["bytes"] += bytes_t
        for nombre, pertenece in CATEGORIAS.items():
            if pertenece(termino, df):
                c = por_cat[nombre]
                c["terminos"] += 1
                c["postings"] += df
                c["bytes"] += bytes_t
                if len(c["ejemplos"]) < 12 and df > 1:
                    c["ejemplos"].append(f"{termino}({df})")

    print(f"\n{ruta}: {total['terminos']:,} términos, {total['postings']:,} postings, "
          f"{total['bytes'] / 2**20:.1f} MB en diccionario+postings")
    print(f"{'categoría':<32}{'términos':>12}{'%':>7}{'postings':>14}{'%':>7}{'MB':>9}{'%':>7}")
    for nombre, c in por_cat.items():
        print(f"{nombre:<32}{c['terminos']:>12,}{100 * c['terminos'] / total['terminos']:>6.1f}%"
              f"{c['postings']:>14,}{100 * c['postings'] / total['postings']:>6.1f}%"
              f"{c['bytes'] / 2**20:>9.1f}{100 * c['bytes'] / total['bytes']:>6.1f}%")
    for nombre, c in por_cat.items():
        print(f"  {nombre}: {' '.join(c['ejemplos'])}")


if __name__ == "__main__":
    for ruta in sys.argv[1:]:
        medir(ruta)