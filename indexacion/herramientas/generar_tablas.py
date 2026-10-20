"""Genera las tablas de estadísticas del documento a partir de indices/*.stats.json.

Uso (desde la raíz del repo):  python indexacion/herramientas/generar_tablas.py [--dir indices] [-o salida.md]

No depende de cómo se construyó cada índice: solo lee un archivo de resultados por índice.

    indexador propio : indices/manual_<P>.idx.stats.json         (lo escribe el indexador manual)
    Lucene           : indices/lucene_<P>.stats.json             (lo escribe el indexador Lucene)
    referencia       : indices/experimento_sin_depuracion.idx.stats.json

<P> es la letra de la política (A..F). Campos que debe traer cada archivo:

    {
      "documentos": 3000,          # documentos indexados
      "tokens_totales": 5750000,   # suma de frecuencias de todos los términos
      "terminos": 61805,           # términos distintos (tamaño del vocabulario)
      "postings": 2016080,         # pares (término, documento)
      "tamano_bytes": 4930000,     # tamaño del índice en disco
      "segundos_total": 12.4       # tiempo de indexación de principio a fin
    }

Si falta un archivo, esa fila queda con "—" en vez de fallar.
"""
import argparse
import json
import sys
from pathlib import Path

POLITICAS = "ABCDEF"
NOMBRES = {"A": "A (base)", "B": "B", "C": "C", "D": "D (A + stopwords)", "E": "E (C con stemming)",
           "F": "F (B + sinónimos)"}
VACIO = "—"


def cargar(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tam(b):
    if b is None:
        return VACIO
    return f"{b / 1e9:.2f} GB" if b >= 1e9 else f"{b / 1e6:.1f} MB"


def tiempo(s):
    if s is None:
        return VACIO
    if s < 90:
        return f"{s:.1f} s"
    m, seg = divmod(round(s), 60)
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min {seg:02d} s"


def num(n):
    return VACIO if n is None else f"{n:,}".replace(",", " ")


def razon(a, b):
    return VACIO if a is None or not b else f"{a / b:.2f}×"


def cambio(nuevo, base):
    if nuevo is None or not base:
        return VACIO
    c = (nuevo - base) / base
    return "≈ 0 %" if abs(c) < 0.005 else f"{c:+.0%}".replace("%", " %")


def tabla(titulo, cabecera, filas):
    out = [f"**{titulo}**", "", "| " + " | ".join(cabecera) + " |", "|" + "|".join("---" for _ in cabecera) + "|"]
    out += ["| " + " | ".join(f) + " |" for f in filas]
    return "\n".join(out) + "\n"


def tabla_motor(titulo, datos):
    filas = []
    for p in POLITICAS:
        d = datos.get(p) or {}
        bpp = d["tamano_bytes"] / d["postings"] if d.get("tamano_bytes") and d.get("postings") else None
        filas.append([NOMBRES[p], num(d.get("documentos")), num(d.get("tokens_totales")), num(d.get("terminos")),
                      num(d.get("postings")), tam(d.get("tamano_bytes")),
                      VACIO if bpp is None else f"{bpp:.2f}", tiempo(d.get("segundos_total"))])
    return tabla(titulo, ["Política", "Documentos", "Tokens", "Términos", "Postings", "Tamaño", "Bytes/posting",
                          "Tiempo"], filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="indices")
    ap.add_argument("-o", "--salida", default="")
    args = ap.parse_args()
    base = Path(args.dir)

    propio = {p: cargar(base / f"manual_{p}.idx.stats.json") for p in POLITICAS}
    lucene = {p: cargar(base / f"lucene_{p}.stats.json") for p in POLITICAS}
    sin_dep = cargar(base / "experimento_sin_depuracion.idx.stats.json")

    for nombre, datos in (("propio", propio), ("Lucene", lucene)):
        cantidades = {d["documentos"] for d in datos.values() if d}
        if len(cantidades) > 1:
            print(f"AVISO: los índices {nombre} no tienen el mismo número de documentos {sorted(cantidades)}; "
                  "las comparaciones no son válidas (¿se construyeron con distinto --limit?).", file=sys.stderr)

    partes = [tabla_motor("Tabla 1. Indexador propio", propio), tabla_motor("Tabla 2. Indexador con Lucene", lucene)]

    filas = []
    for p in POLITICAS:
        a, b = propio.get(p) or {}, lucene.get(p) or {}
        filas.append([NOMBRES[p], tam(a.get("tamano_bytes")), tam(b.get("tamano_bytes")),
                      razon(b.get("tamano_bytes"), a.get("tamano_bytes")),
                      tiempo(a.get("segundos_total")), tiempo(b.get("segundos_total")),
                      razon(b.get("segundos_total"), a.get("segundos_total"))])
    partes.append(tabla("Tabla 3. Indexador propio contra Lucene (razón = Lucene / propio)",
                        ["Política", "Tamaño propio", "Tamaño Lucene", "Razón", "Tiempo propio", "Tiempo Lucene",
                         "Razón"], filas))

    pares = [("D contra A", "D", "A", "efecto de las stopwords"), ("E contra C", "E", "C", "stemming contra lematización"),
             ("F contra B", "F", "B", "efecto de los sinónimos")]
    filas = []
    for nombre, nuevo, base_p, que in pares:
        n, b = propio.get(nuevo) or {}, propio.get(base_p) or {}
        filas.append([nombre, que, cambio(n.get("terminos"), b.get("terminos")),
                      cambio(n.get("postings"), b.get("postings")), cambio(n.get("tamano_bytes"), b.get("tamano_bytes")),
                      cambio(n.get("segundos_total"), b.get("segundos_total"))])
    a = propio.get("A") or {}
    s = sin_dep or {}
    filas.append(["A contra sin depuración", "efecto de depurar la colección", cambio(a.get("terminos"), s.get("terminos")),
                  cambio(a.get("postings"), s.get("postings")), cambio(a.get("tamano_bytes"), s.get("tamano_bytes")),
                  cambio(a.get("segundos_total"), s.get("segundos_total"))])
    partes.append(tabla("Tabla 4. Efecto de cada decisión (indexador propio, cambio respecto a la segunda política)",
                        ["Comparación", "Qué se mide", "Términos", "Postings", "Tamaño", "Tiempo"], filas))

    texto = "\n".join(partes)
    if args.salida:
        Path(args.salida).write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
