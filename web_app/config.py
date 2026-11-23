"""Rutas y parámetros de la aplicación web. Todo se puede cambiar con variables de entorno PREM_*, para mover la
aplicación a otra máquina sin tocar el código."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _ruta(variable: str, defecto: Path) -> Path:
    return Path(os.environ.get(variable, defecto))


# Datos que lee la aplicación (solo lectura)
CRAWL_DB = _ruta("PREM_CRAWL_DB", RAIZ / "data" / "crawl.db")   # url, título y fecha de cada documento
REPO = _ruta("PREM_REPO", RAIZ / "repo")                          # texto de cada documento, para los fragmentos
CONFIG_DIR = _ruta("PREM_CONFIG_DIR", RAIZ / "indexacion" / "config")   # politica_A..F.conf y consultas.txt
POLITICAS = "ABCDEF"

# Resultados del Proyecto 2 que usan las métricas: los 10 primeros de cada motor y política para las 12 consultas de
# prueba, y los juicios de relevancia del pool (sirven de referencia)
RANKINGS_P2 = _ruta("PREM_RANKINGS_P2", RAIZ / "estadisticas" / "evaluacion" / "resultados_busqueda.json")
JUICIOS_P2 = _ruta("PREM_JUICIOS_P2", RAIZ / "estadisticas" / "evaluacion" / "pool_juzgado.csv")
FECHA_P2 = "2026-11-14"

# Servicio de búsqueda de Lucene (programa aparte, en Java)
JAR = _ruta("PREM_JAR", RAIZ / "indexacion" / "indexador_lucene" / "target" / "indexador-lucene.jar")
PUERTO_LUCENE = int(os.environ.get("PREM_PUERTO_LUCENE", "8081"))
LUCENE_URL = os.environ.get("PREM_LUCENE_URL", f"http://127.0.0.1:{PUERTO_LUCENE}")

# Datos que escribe la aplicación (juicios de relevancia y búsquedas)
USO_DB = _ruta("PREM_USO_DB", RAIZ / "web_app" / "datos" / "uso.db")
CACHE_SITIOS = RAIZ / "web_app" / "datos" / "sitios.json"
FECHAS_BIN = RAIZ / "web_app" / "datos" / "fechas.bin"       # día de publicación de cada documento (preparar_fechas.py)
FECHAS_META = RAIZ / "web_app" / "datos" / "fechas.json"

# Interfaz (React) ya compilada: se genera con  cd interfaz && npm run publicar
UI_DIR = _ruta("PREM_UI_DIR", RAIZ / "web_app" / "ui")

PUERTO_WEB = int(os.environ.get("PREM_PUERTO_WEB", "8000"))   # el mismo puerto al que apunta interfaz/vite.config.js
MAX_K = 1000                  # cuántos resultados se piden como máximo al buscador
POLITICA_POR_OMISION = "C"    # la que mejor resultó con Lucene (ver el documento del indexador)
# Modo normal (público): solo Lucene con la política C. Con --dev se ofrecen los dos motores y las seis políticas.
MODO_DEV = os.environ.get("PREM_DEV", "") == "1"

DESCRIPCION_POLITICAS = {
    "A": ("Minimal", "Tokenization and lowercase only. The baseline."),
    "B": ("Intermediate", "Possessives, accents, stopwords, dates and numbers."),
    "C": ("Full", "B plus lemmatization, synonyms and known entities (clubs, competitions)."),
    "D": ("Stopwords only", "A plus stopword removal."),
    "E": ("Full, stemmed", "Same as C, with Porter stemming instead of lemmatization."),
    "F": ("Synonyms", "B plus football-domain synonyms."),
}
