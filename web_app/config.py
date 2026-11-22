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

# Índice con el que se busca: la política elegida (ver la sección de calidad del documento del indexador)
POLITICA = _ruta("PREM_POLITICA", RAIZ / "indexacion" / "config" / "politica_C.conf")
JAR = _ruta("PREM_JAR", RAIZ / "indexacion" / "indexador_lucene" / "target" / "indexador-lucene.jar")
PUERTO_LUCENE = int(os.environ.get("PREM_PUERTO_LUCENE", "8081"))
LUCENE_URL = os.environ.get("PREM_LUCENE_URL", f"http://127.0.0.1:{PUERTO_LUCENE}")

# Datos que escribe la aplicación (marcas de relevancia, consultas y clics)
USO_DB = _ruta("PREM_USO_DB", RAIZ / "web_app" / "datos" / "uso.db")

PUERTO_WEB = int(os.environ.get("PREM_PUERTO_WEB", "5000"))
RESULTADOS_POR_PAGINA = 10
K_BUSQUEDA = 100            # cuántos resultados se piden al buscador (10 páginas de 10)
K_EVALUACION = 10           # cuántos resultados se muestran para marcar relevancia (P@10)
