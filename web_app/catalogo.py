"""Datos de cada documento para mostrarlo: dirección original, título y fecha (de data/crawl.db) y un fragmento
del texto (de repo/) con las palabras buscadas resaltadas."""
import re
import sqlite3
from datetime import datetime

from dateutil import parser as parser_fechas
from markupsafe import Markup, escape

from . import config

_HASH = re.compile(r"^[0-9a-f]{64}$")
_PALABRA = re.compile(r"\w+", re.UNICODE)


def _conexion() -> sqlite3.Connection:
    # Solo lectura; una conexión por consulta es barato (la búsqueda por hash usa un índice).
    return sqlite3.connect(f"file:{config.CRAWL_DB.as_posix()}?mode=ro", uri=True, timeout=10)


def fecha_iso(crudo):
    """Convierte las fechas de las páginas ('2026-09-21T18:15:00+01:00', 'Monday 21st September 2026 7:44 PM',
    '2 Apr 2016', ...) en 'AAAA-MM-DD'. Devuelve None si no se puede o si el año no es razonable."""
    if not crudo:
        return None
    try:
        f = parser_fechas.parse(str(crudo), fuzzy=True, dayfirst=True, default=datetime(1900, 1, 1))
    except (ValueError, OverflowError):
        return None
    if f.year < 2000 or f.year > datetime.now().year + 1:
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


def url_original(hash_doc: str):
    return (detalles([hash_doc]).get(hash_doc) or {}).get("url")


def _ruta_texto(hash_doc: str, host: str):
    return config.REPO / host / hash_doc[:2] / f"{hash_doc}.txt"


def fragmento(hash_doc: str, host: str, consulta: str, largo: int = 240) -> Markup:
    """Un trozo del texto alrededor de la primera palabra buscada, con las palabras buscadas resaltadas."""
    try:
        texto = _ruta_texto(hash_doc, host).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Markup("")
    cuerpo = " ".join(texto.split("\n", 1)[1].split()) if "\n" in texto else " ".join(texto.split())
    palabras = {p.lower() for p in _PALABRA.findall(consulta) if len(p) > 2}
    inicio = 0
    if palabras:
        patron = re.compile(r"\b(" + "|".join(re.escape(p) for p in sorted(palabras, key=len, reverse=True)) + r")\w*",
                            re.IGNORECASE)
        coincidencias = [(m.start(), m.group(1).lower()) for m in patron.finditer(cuerpo)]
        mejor = -1
        # Se elige la zona del texto donde aparecen más palabras distintas de la búsqueda; así el fragmento no sale
        # del menú de navegación del sitio, que suele repetir una sola palabra suelta ("news").
        for posicion, _ in coincidencias:
            ventana = [w for q, w in coincidencias if posicion <= q < posicion + largo]
            puntaje = len(set(ventana)) * 10 + min(len(ventana), 5)
            if puntaje > mejor:
                mejor, inicio = puntaje, max(0, posicion - largo // 6)
    trozo = cuerpo[inicio:inicio + largo].strip()
    if not trozo:
        return Markup("")
    salida = escape(trozo)
    if palabras:
        resaltar = re.compile(r"\b(" + "|".join(re.escape(escape(p)) for p in sorted(palabras, key=len, reverse=True))
                              + r")\b", re.IGNORECASE)   # solo palabras completas: "man" no se resalta en "Manchester"
        salida = Markup(resaltar.sub(lambda m: f"<mark>{m.group(0)}</mark>", str(salida)))
    return Markup(("… " if inicio > 0 else "") + str(salida) + " …")


def sitio_legible(host: str) -> str:
    return host[4:] if host.startswith("www.") else host
