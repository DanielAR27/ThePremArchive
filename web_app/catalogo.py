"""Datos de cada documento para mostrarlo: dirección original, título y fecha (de data/crawl.db) y un fragmento
del texto (de repo/). El resaltado de las palabras buscadas lo hace la interfaz, así que el fragmento es texto plano."""
import re
import sqlite3
from datetime import datetime

from . import config
from .preparar_fechas import fecha_de_texto

_HASH = re.compile(r"^[0-9a-f]{64}$")
_PALABRA = re.compile(r"\w+", re.UNICODE)


def _conexion() -> sqlite3.Connection:
    # Solo lectura; una conexión por consulta es barato (la búsqueda por hash usa un índice).
    return sqlite3.connect(f"file:{config.CRAWL_DB.as_posix()}?mode=ro", uri=True, timeout=10)


def fecha_iso(crudo):
    """Convierte la fecha de una página ('2026-09-21T18:15:00+01:00', 'Monday 21st September 2026 7:44 PM', '2 Apr 2016',
    ...) en 'AAAA-MM-DD'. Es la misma lectura que usa el filtro por fecha (preparar_fechas.py), para que lo que se muestra
    coincida con lo que se filtra. Devuelve None si no se puede o si el año no es razonable."""
    if not crudo:
        return None
    f = fecha_de_texto(str(crudo))
    if f is None or f.year < 2000 or f.year > datetime.now().year + 1:
        return None
    return f.strftime("%Y-%m-%d")


def detalles(hashes):
    """{hash: {'url', 'titulo', 'host', 'fecha'}} de los documentos pedidos."""
    hashes = [h for h in hashes if _HASH.match(h)]
    if not hashes:
        return {}
    con = _conexion()
    try:
        marcas = ",".join("?" * len(hashes))
        filas = con.execute(f"SELECT sha256, url, title, host, published_at FROM documents WHERE sha256 IN ({marcas})",
                            hashes).fetchall()
    finally:
        con.close()
    return {h: {"url": url, "titulo": (titulo or url), "host": host, "fecha": fecha_iso(fecha)}
            for h, url, titulo, host, fecha in filas}


def total_rastreados() -> int:
    con = _conexion()
    try:
        return con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    finally:
        con.close()


def _ruta_texto(hash_doc: str, host: str):
    return config.REPO / host / hash_doc[:2] / f"{hash_doc}.txt"


def fragmento(hash_doc: str, host: str, consulta: str, largo: int = 300) -> str:
    """Un trozo de texto de la zona del documento donde aparecen más palabras distintas de la búsqueda."""
    try:
        texto = _ruta_texto(hash_doc, host).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    cuerpo = " ".join(texto.split("\n", 1)[1].split()) if "\n" in texto else " ".join(texto.split())
    palabras = {p.lower() for p in _PALABRA.findall(consulta) if len(p) > 2}
    inicio = 0
    if palabras:
        # Palabras completas (con plural): "news" no debe coincidir con "Newsletter", que está en el menú de casi todos
        # los sitios.
        patron = re.compile(r"\b(" + "|".join(re.escape(p) for p in sorted(palabras, key=len, reverse=True)) + r")(?:e?s)?\b",
                            re.IGNORECASE)
        coincidencias = [(m.start(), m.group(1).lower()) for m in patron.finditer(cuerpo)]
        mejor = -1
        # Se elige la zona donde aparecen más palabras distintas de la búsqueda; así el fragmento no sale del menú de
        # navegación del sitio, que suele repetir una sola palabra suelta ("news").
        for posicion, _ in coincidencias:
            ventana = [w for q, w in coincidencias if posicion <= q < posicion + largo]
            puntaje = len(set(ventana)) * 10 + min(len(ventana), 5)
            if puntaje > mejor:
                mejor, inicio = puntaje, max(0, posicion - largo // 6)
    trozo = cuerpo[inicio:inicio + largo].strip()
    if not trozo:
        return ""
    return ("… " if inicio > 0 else "") + trozo + " …"
