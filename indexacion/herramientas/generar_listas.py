"""Genera indexacion/config/datos/stopwords.txt y lemas.txt a partir del vocabulario real.

Uso (desde la raíz del repo): python indexacion/herramientas/generar_listas.py

Entradas : estadisticas/word_counter.pkl (Counter palabra -> frecuencia, de compute_stats.py)
           NLTK: corpus "stopwords" y "wordnet" (nltk.download)
Salidas  : indexacion/config/datos/stopwords.txt, lemas.txt
"""
import pickle
import re
import sys
from pathlib import Path

import nltk
from nltk.corpus import stopwords as nltk_stopwords
from nltk.stem import WordNetLemmatizer

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "indexacion" / "config" / "datos"
FRECUENCIA_MIN_LEMAS = 20  # solo se lematizan palabras que aparecen al menos tanto en la colección

# Fragmentos que deja la tokenización al separar apóstrofes ("don't" -> "don", "t"; "Arsenal's" -> "s").
FRAGMENTOS = ["s", "t", "m", "d", "ll", "re", "ve", "l", "w", "th"]

# Formas que WordNet lematizaría mal en este dominio (nombres de equipos y apodos en minúscula).
PROTEGIDAS = {
    "united", "city", "leeds", "wolves", "spurs", "saints", "hammers", "blades", "villans",
    "foxes", "toffees", "gunners", "reds", "blues", "magpies", "seagulls", "bees", "eagles",
    "canaries", "hornets", "cherries", "baggies", "royals", "potters", "owls", "rovers",
    "wanderers", "athletic", "forest", "villa", "palace", "town", "county", "albion",
}

# Palabras que NLTK trae como stopwords por venir de contracciones pero que en fútbol son informativas.
NO_STOPWORDS = {"won"}
# Modales y adverbios muy frecuentes que la lista de NLTK no incluye (revisión de la lista de frecuencias).
EXTRAS_STOPWORDS = ["could", "would", "might", "must", "may", "shall", "also"]

# Plurales irregulares que sí queremos unir; las demás formas deben ser sufijos regulares.
IRREGULARES = {"children": "child", "women": "woman", "men": "man", "feet": "foot", "teeth": "tooth",
               "people": "person"}
# Sustantivos en -ing/-ed (o plurales) que WordNet reduciría mal.
EXCLUIDAS = {"wedding", "outing", "building", "meeting", "evening", "morning", "cookies", "media",
             "ending", "clothing", "bos"}

SOLO_LETRAS = re.compile(r"^[a-z]+$")


def _sufijo_regular(palabra: str, lema: str, es_verbo: bool) -> bool:
    w = palabra
    if es_verbo:  # played, scored, stopped, tried, playing, making, died
        posibles = {w[:-3], w[:-3] + "e", w[:-2], w[:-1], w[:-4], w[:-3] + "y"}
    else:         # goals, matches, stories, leaves, wives
        posibles = {w[:-1], w[:-2], w[:-3] + "y", w[:-3] + "f", w[:-3] + "fe"}
    return lema in posibles


def generar_stopwords(contador) -> list:
    nltk.download("stopwords", quiet=True)
    base = {w for w in nltk_stopwords.words("english") if "'" not in w}
    return sorted((base - NO_STOPWORDS) | set(FRAGMENTOS) | set(EXTRAS_STOPWORDS))


def generar_lemas(contador, stop: set) -> dict:
    nltk.download("wordnet", quiet=True)
    lem = WordNetLemmatizer()
    lemas = {}
    for palabra, frecuencia in contador.items():
        if frecuencia < FRECUENCIA_MIN_LEMAS or not SOLO_LETRAS.match(palabra):
            continue
        if palabra in stop or palabra in PROTEGIDAS:
            continue
        if palabra in EXCLUIDAS or palabra.endswith("ss"):
            continue
        if palabra in IRREGULARES:
            lemas[palabra] = IRREGULARES[palabra]
            continue
        lema, es_verbo = lem.lemmatize(palabra, "n"), False
        if lema == palabra and palabra.endswith(("ing", "ed")):
            lema, es_verbo = lem.lemmatize(palabra, "v"), True  # solo formas verbales claras
        if (lema != palabra and lema in contador and len(lema) > 1
                and _sufijo_regular(palabra, lema, es_verbo)):
            lemas[palabra] = lema
    return lemas


def main():
    with open(RAIZ / "estadisticas" / "word_counter.pkl", "rb") as f:
        contador = pickle.load(f)

    stop = generar_stopwords(contador)
    with open(DATOS / "stopwords.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write("# Stopwords del inglés: lista de NLTK (Bird, Klein & Loper, 2009) sin contracciones,\n")
        f.write("# más los fragmentos que deja separar apóstrofes (s, t, m, ...).\n")
        f.write("# Generado por indexacion/herramientas/generar_listas.py. Una por línea.\n")
        f.write("\n".join(stop) + "\n")

    lemas = generar_lemas(contador, set(stop))
    with open(DATOS / "lemas.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write("# Mapa forma -> lema (tabulador). WordNet (Fellbaum, 1998) vía NLTK: sustantivos,\n")
        f.write(f"# y verbos solo para formas en -ing/-ed, siempre con sufijo regular. Solo palabras con frecuencia >= {FRECUENCIA_MIN_LEMAS}\n")
        f.write("# en la colección y cuyo lema también aparece en ella. Excluye nombres de equipos.\n")
        f.write("# Generado por indexacion/herramientas/generar_listas.py.\n")
        for forma in sorted(lemas):
            f.write(f"{forma}\t{lemas[forma]}\n")

    print(f"stopwords: {len(stop)}  lemas: {len(lemas)}")
    print("Más frecuentes que NO son stopwords (revisar):")
    print([w for w, _ in contador.most_common(120) if w not in set(stop)][:60])
    print("Lemas más frecuentes (revisar):")
    top = sorted(lemas, key=lambda w: -contador[w])[:60]
    print([f"{w}->{lemas[w]}" for w in top])


if __name__ == "__main__":
    sys.exit(main())
