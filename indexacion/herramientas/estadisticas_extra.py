"""Estadísticas que caracterizan la colección indexada: largo de los documentos, frecuencia de los términos y ley de Zipf.

    python indexacion/herramientas/estadisticas_extra.py

Lee indices/manual_X.idx (el índice propio guarda el largo de cada documento y los df de cada término; Lucene tiene
los mismos términos y postings, así que daría lo mismo). Imprime las tablas del documento y deja
estadisticas/estadisticas_extra.json y estadisticas/frecuencias.png (distribución de frecuencias, escala logarítmica).
"""
import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "estadisticas"))

from indexacion.indexador_manual.buscar import Indice  # noqa: E402
import graficos_indexador as g  # noqa: E402

POLITICAS = "ABCDEF"


def analizar(p: str):
    indice = Indice(str(RAIZ / "indices" / f"manual_{p}.idx"))
    terminos = list(indice.diccionario.keys())
    df = np.array([indice.diccionario[t][0] for t in terminos], dtype=np.int64)
    largos = indice.docs["n_tokens"].astype(np.int64)
    orden = np.argsort(-df)
    n_docs, total_postings = indice.n_docs, int(df.sum())
    resumen = {
        "documentos": int(n_docs),
        "terminos": len(terminos),
        "largo_medio": float(largos.mean()),
        "largo_mediana": float(np.median(largos)),
        "largo_max": int(largos.max()),
        "docs_menos_100_palabras_pct": float((largos < 100).mean() * 100),
        "terminos_en_un_solo_doc_pct": float((df == 1).mean() * 100),
        "postings_top100_pct": float(df[orden[:100]].sum() / total_postings * 100),
        "top_terminos": [(terminos[i], int(df[i]), float(df[i] / n_docs * 100)) for i in orden[:10]],
    }
    zipf_df = df[orden]
    indice.cerrar()
    return resumen, zipf_df


def figura(series):
    """Frecuencia de documento de cada término según su puesto (ley de Zipf), una línea por política."""
    fig, ax = g.plt.subplots(figsize=(7.2, 4.2), dpi=150)
    colores = {"A": g._SERIES_BLUE, "B": g._SERIES_GREEN, "C": g._SERIES_AMBER}
    for p, df in series.items():
        n = len(df)
        puestos = np.unique(np.logspace(0, np.log10(n), 600).astype(int)) - 1
        ax.plot(puestos + 1, df[puestos], color=colores[p], linewidth=2, label=f"Política {p}")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Puesto del término (1 = el que aparece en más documentos)")
    ax.set_ylabel("Documentos que lo contienen")
    ax.set_title("Pocos términos aparecen en muchos documentos; la mayoría, en muy pocos", fontsize=10.5,
                 fontweight="bold", pad=10)
    ax.grid(True, color=g._GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    fig.tight_layout()
    g._guardar(fig, RAIZ / "estadisticas" / "frecuencias.png")


def main():
    resumenes, series = {}, {}
    for p in POLITICAS:
        resumenes[p], zipf_df = analizar(p)
        if p in "ABC":
            series[p] = zipf_df
        print(f"política {p} lista", file=sys.stderr, flush=True)
    (RAIZ / "estadisticas" / "estadisticas_extra.json").write_text(
        json.dumps(resumenes, indent=1, ensure_ascii=False), encoding="utf-8")
    figura(series)

    print("\n| Política | Palabras por documento (media / mediana) | Documentos con menos de 100 palabras "
          "| Términos que aparecen en un solo documento | Postings que ocupan los 100 términos más frecuentes |")
    print("|---|---|---|---|---|")
    for p in POLITICAS:
        r = resumenes[p]
        print(f"| {p} | {r['largo_medio']:.0f} / {r['largo_mediana']:.0f} | {r['docs_menos_100_palabras_pct']:.0f} % "
              f"| {r['terminos_en_un_solo_doc_pct']:.0f} % | {r['postings_top100_pct']:.0f} % |")
    for p in "AB":
        print(f"\nTérminos en más documentos, política {p}:")
        print("| Término | Documentos | % de la colección |\n|---|---|---|")
        for t, d, pct in resumenes[p]["top_terminos"]:
            print(f"| {t} | {d:,} | {pct:.0f} % |".replace(",", " "))


if __name__ == "__main__":
    main()
