"""Genera los diagramas y gráficos del documento del indexador.

Uso (desde la raíz del repo):  python estadisticas/graficos_indexador.py [--dir indices]

Diagramas (no dependen de datos, van a imagenes/):
    indexacion_flujo.png     de la colección a los dos índices
    lucene_analisis.png      cadena de análisis del indexador Lucene
    formato_idx.png          campos de cada registro del archivo manual_X.idx
Gráfico (a partir de indices/*.stats.json, va a estadisticas/; se omite si no hay resultados):
    comparacion_indices.png  tamaño y tiempo de cada política, propio contra Lucene
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

RAIZ = Path(__file__).resolve().parents[1]

_INK_PRIMARY = "#0b0b0b"
_INK_SECONDARY = "#52514e"
_INK_MUTED = "#898781"
_GRIDLINE = "#e1e0d9"
_SURFACE = "#fcfcfb"
_SERIES_BLUE = "#2a78d6"
_SERIES_GREEN = "#1f9d6b"
_SERIES_AMBER = "#d08a1c"
_NEUTRAL = "#e9e8e2"
# Rellenos claros de cada serie, para cajas con texto encima
_FILL_BLUE = "#dbe8f8"
_FILL_GREEN = "#d6efe4"
_FILL_AMBER = "#f6e7cc"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "text.color": _INK_PRIMARY,
    "axes.edgecolor": _GRIDLINE,
    "axes.labelcolor": _INK_SECONDARY,
    "xtick.color": _INK_MUTED,
    "ytick.color": _INK_MUTED,
    "figure.facecolor": _SURFACE,
    "axes.facecolor": _SURFACE,
    "savefig.facecolor": _SURFACE,
})

POLITICAS = "ABCDEF"


# --- piezas de dibujo ---------------------------------------------------------------------

def _lienzo(ancho, alto):
    fig, ax = plt.subplots(figsize=(ancho, alto), dpi=150)
    ax.set_xlim(0, ancho)
    ax.set_ylim(0, alto)
    ax.axis("off")
    return fig, ax


def _caja(ax, x, y, w, h, texto, relleno, borde, sub=None, tam=9.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                facecolor=relleno, edgecolor=borde, linewidth=1.2))
    if sub:
        ax.text(x + w / 2, y + h * 0.62, texto, ha="center", va="center", fontsize=tam, fontweight="bold")
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=tam - 1.8, color=_INK_SECONDARY)
    else:
        ax.text(x + w / 2, y + h / 2, texto, ha="center", va="center", fontsize=tam, fontweight="bold")


def _flecha(ax, a, b, color=_INK_MUTED, estilo="-", texto=None):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=11, color=color, linewidth=1.2,
                                 linestyle=estilo, shrinkA=2, shrinkB=2))
    if texto:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.12, texto, ha="center", va="bottom", fontsize=7.5,
                color=_INK_SECONDARY)


def _guardar(fig, ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, bbox_inches="tight")
    plt.close(fig)
    print(f"  {ruta.relative_to(RAIZ)}")


# --- diagramas ----------------------------------------------------------------------------

def flujo():
    fig, ax = _lienzo(13, 5.6)
    gris = dict(relleno=_NEUTRAL, borde=_INK_MUTED)
    azul = dict(relleno=_FILL_BLUE, borde=_SERIES_BLUE)
    verde = dict(relleno=_FILL_GREEN, borde=_SERIES_GREEN)
    ambar = dict(relleno=_FILL_AMBER, borde=_SERIES_AMBER)

    _caja(ax, 0.1, 3.5, 1.7, 0.85, "repo/", sub="1 440 556 .txt", **gris)
    _caja(ax, 0.1, 1.3, 1.7, 0.85, "data/crawl.db", sub="host, URL, título", **gris)
    _caja(ax, 2.3, 2.4, 1.8, 0.95, "Depuración", sub="depuracion.txt\n1 010 827 docs", **ambar)
    _flecha(ax, (1.8, 3.9), (2.3, 3.0))
    _flecha(ax, (1.8, 1.7), (2.3, 2.7))
    # rama del indexador propio (arriba) y de Lucene (abajo); la política en medio alimenta a las dos
    y1, y2, h = 3.75, 0.45, 0.9
    pasos1 = [("Normalizador", "Python, re + NLTK"), ("Bloques SPIMI", "un proceso por núcleo"),
              ("Mezcla k-vías", "diccionario + normas"), ("manual_X.idx", "un solo archivo")]
    pasos2 = [("Analizador", "Lucene + filtros propios"), ("IndexWriter", "hilos → segmentos"),
              ("forceMerge(1)", "un segmento"), ("lucene_X/", "~13 archivos")]
    xs = [4.6, 6.5, 8.4, 10.3]
    for i, ((t1, s1), (t2, s2)) in enumerate(zip(pasos1, pasos2)):
        _caja(ax, xs[i], y1, 1.6, h, t1, sub=s1, **azul)
        _caja(ax, xs[i], y2, 1.6, h, t2, sub=s2, **verde)
        if i:
            _flecha(ax, (xs[i - 1] + 1.6, y1 + h / 2), (xs[i], y1 + h / 2))
            _flecha(ax, (xs[i - 1] + 1.6, y2 + h / 2), (xs[i], y2 + h / 2))
    _flecha(ax, (4.1, 3.05), (4.6, y1 + h / 2))
    _flecha(ax, (4.1, 2.7), (4.6, y2 + h / 2))
    _caja(ax, 4.6, 2.05, 3.5, 1.05, "politica_X.conf + datos/",
          sub="mismas reglas para los dos indexadores\nverificado: mismos términos (comparar_normalizacion.py)",
          **ambar)
    _flecha(ax, (5.4, 3.1), (5.4, y1))
    _flecha(ax, (5.4, 2.05), (5.4, y2 + h))
    _caja(ax, 12.1, 2.25, 0.85, 1.0, "stats\n.json", **gris, tam=8.5)
    _flecha(ax, (11.9, y1 + h / 2), (12.3, 3.25))
    _flecha(ax, (11.9, y2 + h / 2), (12.3, 2.25))
    ax.text(12.52, 2.05, "generar_tablas.py", ha="center", va="top", fontsize=7.5, color=_INK_SECONDARY)

    ax.text(4.6, y1 + h + 0.12, "Indexador propio (Python)", fontsize=9, color=_SERIES_BLUE, fontweight="bold")
    ax.text(4.6, y2 - 0.3, "Indexador Lucene (Java)", fontsize=9, color=_SERIES_GREEN, fontweight="bold")
    _guardar(fig, RAIZ / "imagenes" / "indexacion_flujo.png")


def analisis_lucene():
    pasos = [
        ("Transformacion", "CharFilter propio", "entidades, fechas, miles", True),
        ("PatternTokenizer", "Lucene", "misma regex que Python", False),
        ("Posesivo", "propio", "apostrofes = posesivo", True),
        ("Minusculas", "propio", "minusculas = true", True),
        ("QuitarAcentos", "propio", "quitar_acentos = true", True),
        ("CodepointCount", "Lucene", "largo ≤ 40", False),
        ("StopFilter", "Lucene", "stopwords = …", False),
        ("SynonymGraph", "Lucene", "sinonimos = …", False),
        ("KeywordMarker", "Lucene", "solo palabras de letras", False),
        ("StemmerOverride\n/ PorterStem", "Lucene", "reduccion = …", False),
    ]
    fig, ax = _lienzo(12.6, 3.9)
    w, h, sep = 2.05, 1.15, 0.45
    for i, (nombre, origen, clave, propio) in enumerate(pasos):
        fila, col = divmod(i, 5)
        col = col if fila == 0 else 4 - col  # en serpiente: la segunda fila va de derecha a izquierda
        x, y = 0.15 + col * (w + sep), 2.3 - fila * 1.95
        estilo = dict(relleno=_FILL_BLUE, borde=_SERIES_BLUE) if propio else dict(relleno=_FILL_GREEN,
                                                                                    borde=_SERIES_GREEN)
        _caja(ax, x, y, w, h, nombre, sub=f"{origen}\n{clave}", tam=9, **estilo)
        if i and i != 5:
            if fila == 0:
                _flecha(ax, (x - sep, y + h / 2), (x, y + h / 2))
            else:
                _flecha(ax, (x + w + sep, y + h / 2), (x + w, y + h / 2))
    x4 = 0.15 + 4 * (w + sep) + w / 2
    _flecha(ax, (x4, 2.3), (x4, 2.3 - 1.95 + h))
    ax.add_patch(Rectangle((0.2, 3.62), 0.25, 0.18, facecolor=_FILL_BLUE, edgecolor=_SERIES_BLUE))
    ax.text(0.52, 3.71, "escrito por nosotros (Lucene no lo hace igual)", va="center", fontsize=8.5)
    ax.add_patch(Rectangle((4.6, 3.62), 0.25, 0.18, facecolor=_FILL_GREEN, edgecolor=_SERIES_GREEN))
    ax.text(4.92, 3.71, "componente de Lucene", va="center", fontsize=8.5)
    ax.text(0.15, 0.08, "texto del documento → … → términos del índice; cada paso se activa con su clave del .conf",
            fontsize=8, color=_INK_MUTED)
    _guardar(fig, RAIZ / "imagenes" / "lucene_analisis.png")


def formato_idx():
    registros = [
        ("Cabecera (96 B)", [("PREMIDX1", 8), ("ver", 2), ("0", 2), ("n_docs", 4), ("n_terms", 4),
                             ("n_postings", 8), ("tokens", 8), ("off_meta", 8), ("off_hosts", 8),
                             ("off_docs", 8), ("off_dict", 8), ("off_post", 8), ("tamaño", 8), ("relleno", 12)]),
        ("Documento (42 B)", [("hash SHA-256", 32), ("host", 2), ("n_tokens", 4), ("norma", 4)]),
        ("Entrada del diccionario", [("largo", 1), ("término (UTF-8)", 9), ("df", 2), ("long_post", 2)]),
        ("Postings de un término", [("Δdoc", 2), ("tf", 1), ("Δdoc", 2), ("tf", 1), ("Δdoc", 1), ("tf", 1),
                                    ("…", 4)]),
    ]
    notas = ["enteros big-endian de tamaño fijo", "arreglo de n_docs registros: el doc_id es la posición",
             "varint LEB128 en df y long_post", "varint; Δdoc = diferencia con el doc_id anterior"]
    colores = [_FILL_AMBER, _FILL_BLUE, _FILL_GREEN, _NEUTRAL]
    bordes = [_SERIES_AMBER, _SERIES_BLUE, _SERIES_GREEN, _INK_MUTED]
    fig, ax = _lienzo(13, 5.0)
    escalas = [12.8 / 96, 12.8 / 64, 12.8 / 24, 12.8 / 24]
    for fila, ((titulo, campos), nota, c, b) in enumerate(zip(registros, notas, colores, bordes)):
        y = 4.05 - fila * 1.25
        ax.text(0.1, y + 0.62, titulo, fontsize=9.5, fontweight="bold")
        ax.text(0.1 + 0.105 * len(titulo), y + 0.62, "·  " + nota, fontsize=8, color=_INK_SECONDARY)
        x = 0.1
        for nombre, bytes_ in campos:
            w = bytes_ * escalas[fila]
            ax.add_patch(Rectangle((x, y), w, 0.45, facecolor=c, edgecolor=b, linewidth=1))
            ax.text(x + w / 2, y + 0.225, nombre, ha="center", va="center", fontsize=6.6 if w < 0.6 else 7.8)
            if fila < 2:
                ax.text(x + w / 2, y - 0.1, f"{bytes_}", ha="center", va="center", fontsize=6.5, color=_INK_MUTED)
            x += w
    _guardar(fig, RAIZ / "imagenes" / "formato_idx.png")


# --- gráfico con los resultados -----------------------------------------------------------

def _leer(ruta):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def comparacion(dir_indices: Path):
    propio = {p: _leer(dir_indices / f"manual_{p}.idx.stats.json") for p in POLITICAS}
    lucene = {p: _leer(dir_indices / f"lucene_{p}.stats.json") for p in POLITICAS}
    pols = [p for p in POLITICAS if propio[p] and lucene[p]]
    if not pols:
        print("  (sin resultados de ambos indexadores en", dir_indices, "- se omite comparacion_indices.png)")
        return
    fig, ejes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150)
    medidas = [("tamano_bytes", "Tamaño del índice (MB)", 1e6), ("segundos_total", "Tiempo de indexación (min)", 60)]
    for ax, (clave, titulo, div) in zip(ejes, medidas):
        x = range(len(pols))
        a = [propio[p][clave] / div for p in pols]
        b = [lucene[p][clave] / div for p in pols]
        ax.bar([i - 0.19 for i in x], a, width=0.36, color=_SERIES_BLUE, label="Propio (Python)")
        ax.bar([i + 0.19 for i in x], b, width=0.36, color=_SERIES_GREEN, label="Lucene (Java)")
        for i, (va, vb) in enumerate(zip(a, b)):
            ax.text(i - 0.19, va, f"{va:.0f}" if va >= 10 else f"{va:.1f}", ha="center", va="bottom", fontsize=7.5,
                    color=_INK_SECONDARY)
            ax.text(i + 0.19, vb, f"{vb:.0f}" if vb >= 10 else f"{vb:.1f}", ha="center", va="bottom", fontsize=7.5,
                    color=_INK_SECONDARY)
        ax.set_xticks(list(x), [f"Política {p}" for p in pols])
        ax.set_title(titulo, fontsize=11, fontweight="bold", pad=10)
        ax.grid(True, axis="y", color=_GRIDLINE, linewidth=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.tick_params(axis="x", length=0)
    ejes[0].legend(frameon=False, fontsize=8.5, loc="upper right")
    docs = propio[pols[0]]["documentos"]
    fig.text(0.99, 0.0, f"{docs:,} documentos".replace(",", " "), ha="right", va="bottom", fontsize=8,
             color=_INK_MUTED)
    fig.tight_layout()
    _guardar(fig, RAIZ / "estadisticas" / "comparacion_indices.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(RAIZ / "indices"))
    args = ap.parse_args()
    print("Generando:")
    flujo()
    analisis_lucene()
    formato_idx()
    comparacion(Path(args.dir))


if __name__ == "__main__":
    main()
