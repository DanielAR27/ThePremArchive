"""Genera las graficas de estadisticas del repositorio a partir de
estadisticas/word_counter.pkl (producido por compute_stats.py).

Uso: python estadisticas/make_charts.py
"""
from __future__ import annotations

import pickle
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

_OUT_DIR = Path(__file__).resolve().parent

_INK_PRIMARY = "#0b0b0b"
_INK_SECONDARY = "#52514e"
_INK_MUTED = "#898781"
_GRIDLINE = "#e1e0d9"
_SURFACE = "#fcfcfb"
_SERIES_BLUE = "#2a78d6"

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


def _short(n: float, _pos=None) -> str:
    for div, suf in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "k")):
        if abs(n) >= div:
            return f"{n / div:.0f}{suf}"
    return f"{n:.0f}"


def zipf_curve(counter) -> None:
    """Curva rango-frecuencia (ley de Zipf) en escala log-log, toda la coleccion."""
    frequencies = sorted(counter.values(), reverse=True)
    ranks = range(1, len(frequencies) + 1)

    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)
    ax.plot(ranks, frequencies, color=_SERIES_BLUE, linewidth=2, solid_capstyle="round")
    ax.set_xscale("log")
    ax.set_yscale("log")

    ax.set_xlabel("Rango de la palabra (de más a menos frecuente)")
    ax.set_ylabel("Frecuencia (ocurrencias)")
    ax.set_title("Distribución de frecuencia de palabras en el repositorio",
                  fontsize=13, fontweight="bold", color=_INK_PRIMARY, pad=14)

    ax.grid(True, which="both", color=_GRIDLINE, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(_GRIDLINE)

    ax.xaxis.set_major_formatter(FuncFormatter(_short))
    ax.yaxis.set_major_formatter(FuncFormatter(_short))

    fig.text(0.99, 0.01, f"{len(frequencies):,} palabras distintas",
             ha="right", va="bottom", fontsize=9, color=_INK_MUTED)

    fig.tight_layout()
    fig.savefig(_OUT_DIR / "curva_frecuencia_palabras.png", bbox_inches="tight")
    plt.close(fig)


def top_words_bar(counter, n: int = 20) -> None:
    """Barra horizontal de las n palabras mas frecuentes."""
    top = counter.most_common(n)[::-1]
    words = [w for w, _ in top]
    counts = [c for _, c in top]

    fig, ax = plt.subplots(figsize=(8, 7), dpi=150)
    bars = ax.barh(words, counts, color=_SERIES_BLUE, height=0.65)

    ax.set_xlabel("Ocurrencias en el repositorio")
    ax.set_title(f"{n} palabras más frecuentes",
                 fontsize=13, fontweight="bold", color=_INK_PRIMARY, pad=14)

    ax.xaxis.set_major_formatter(FuncFormatter(_short))
    ax.grid(True, axis="x", color=_GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(_GRIDLINE)
    ax.tick_params(axis="y", length=0)

    for bar, count in zip(bars, counts):
        ax.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2,
                f"{count:,}", va="center", ha="left", fontsize=8.5, color=_INK_SECONDARY)

    fig.tight_layout()
    fig.savefig(_OUT_DIR / "top_palabras.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    with open(_OUT_DIR / "word_counter.pkl", "rb") as f:
        counter = pickle.load(f)
    zipf_curve(counter)
    top_words_bar(counter)
    print("Graficas guardadas en estadisticas/curva_frecuencia_palabras.png y estadisticas/top_palabras.png")


if __name__ == "__main__":
    main()
