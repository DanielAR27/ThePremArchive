"""Búsqueda: le pregunta al servicio de Lucene y, si no responde, usa el índice propio en Python como respaldo."""
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

sys.path.insert(0, str(config.RAIZ))


class Buscador:
    def __init__(self):
        self._manual = None
        self._cerrojo = threading.Lock()

    # --- Lucene -----------------------------------------------------------------------------------
    def _lucene(self, consulta: str, k: int) -> dict:
        url = f"{config.LUCENE_URL}/buscar?" + urllib.parse.urlencode({"q": consulta, "k": k})
        with urllib.request.urlopen(url, timeout=10) as respuesta:
            datos = json.load(respuesta)
        datos["motor"] = "lucene"
        return datos

    def lucene_disponible(self) -> bool:
        try:
            with urllib.request.urlopen(f"{config.LUCENE_URL}/salud", timeout=2) as respuesta:
                return bool(json.load(respuesta).get("ok"))
        except (urllib.error.URLError, OSError, ValueError):
            return False

    # --- Índice propio (respaldo) -----------------------------------------------------------------
    def _cargar_manual(self):
        with self._cerrojo:
            if self._manual is None:
                from indexacion.indexador_manual.buscar import Indice
                from indexacion.indexador_manual.config import cargar
                from indexacion.indexador_manual.normalizacion import Normalizador
                politica = cargar(config.POLITICA)
                self._manual = (Indice(str(politica.salida)), Normalizador(politica))
        return self._manual

    def _propio(self, consulta: str, k: int) -> dict:
        indice, normalizador = self._cargar_manual()
        t0 = time.perf_counter()
        terminos = normalizador(consulta)
        resultados = []
        for puesto, (doc_id, puntaje) in enumerate(indice.buscar(terminos, k), 1):
            resultados.append({"puesto": puesto, "host": indice.hosts[int(indice.docs[doc_id]["host"])],
                               "hash": indice.hash_hex(doc_id), "puntaje": puntaje})
        return {"consulta": consulta, "terminos": terminos, "resultados": resultados, "motor": "manual",
                "tiempo_ms": (time.perf_counter() - t0) * 1000}

    # --- Interfaz pública -------------------------------------------------------------------------
    def buscar(self, consulta: str, k: int = config.K_BUSQUEDA) -> dict:
        """{'consulta', 'terminos', 'resultados': [{puesto, host, hash, puntaje}], 'tiempo_ms', 'motor'}"""
        consulta = " ".join(consulta.split())
        if not consulta:
            return {"consulta": "", "terminos": [], "resultados": [], "tiempo_ms": 0.0, "motor": "none"}
        try:
            return self._lucene(consulta, k)
        except (urllib.error.URLError, OSError, ValueError):
            return self._propio(consulta, k)
