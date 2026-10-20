"""Normalización de texto según una Politica: texto -> lista de términos."""
import re
import unicodedata
from typing import Dict, Optional, Set

from .config import Politica

MAX_LONG_TERMINO = 40
MAX_CACHE = 2_000_000

_MESES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MES = "|".join(sorted(_MESES, key=len, reverse=True))
# "May 6, 2010", "May 6th 2010"
_FECHA_MDY = re.compile(rf"\b({_MES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
# "6 May 2010", "6th of May, 2010"
_FECHA_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MES})\.?,?\s+(\d{{4}})\b", re.I)
# "06/05/2010" (día/mes/año: fuentes británicas)
_FECHA_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MILES = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_ENTIDAD = re.compile(r"\b[A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+(?:[ ][A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+)+")


def _leer_lineas(ruta: str):
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea and not linea.startswith("#"):
                yield linea


def _cargar_stopwords(ruta: Optional[str]) -> Set[str]:
    return set(_leer_lineas(ruta)) if ruta else set()


def _cargar_lemas(ruta: Optional[str]) -> Dict[str, str]:
    mapa = {}
    if ruta:
        for linea in _leer_lineas(ruta):
            forma, _, lema = linea.partition("\t")
            if lema:
                mapa[forma.strip()] = lema.strip()
    return mapa


def _cargar_sinonimos(ruta: Optional[str]) -> Dict[str, str]:
    mapa = {}
    if ruta:
        for linea in _leer_lineas(ruta):
            grupo = [t.strip() for t in linea.split(",") if t.strip()]
            for sinonimo in grupo[1:]:
                mapa[sinonimo] = grupo[0]
    return mapa


def _cargar_entidades(ruta: Optional[str]):
    """Regex de todas las frases conocidas y mapa frase(minúsculas) -> término canónico."""
    if not ruta:
        return None, {}
    canonico = {}
    for linea in _leer_lineas(ruta):
        campos = [c.strip() for c in linea.split("|") if c.strip()]
        for frase in campos[1:]:
            canonico[" ".join(frase.lower().split())] = campos[0]
    frases = sorted(canonico, key=len, reverse=True)
    patron = r"(?<!\w)(?:" + "|".join(r"\s+".join(map(re.escape, f.split())) for f in frases) + r")(?!\w)"
    return re.compile(patron, re.I), canonico


class Normalizador:
    def __init__(self, politica: Politica):
        self.p = politica
        self.stop = _cargar_stopwords(politica.stopwords)
        self.sinonimos = _cargar_sinonimos(politica.sinonimos)
        self.lemas = _cargar_lemas(politica.lemas) if politica.reduccion == "lematizar" else {}
        self._entidades_conocidas, self._canonico = _cargar_entidades(politica.entidades)
        self.stemmer = None
        if politica.reduccion == "stemming":
            if politica.algoritmo_stemming != "porter":
                raise ValueError(f"algoritmo_stemming no soportado: {politica.algoritmo_stemming}")
            from nltk.stem import PorterStemmer
            self.stemmer = PorterStemmer()

        alternativas = []
        if politica.normalizar_fechas and "-" in politica.formato_fecha:
            alternativas.append(r"\d{4}-\d{2}-\d{2}")
        if politica.normalizar_numeros:
            alternativas.append(r"\d+\.\d+")
        alternativas.append(r"\w+(?:['’]\w+)*" if politica.apostrofes == "posesivo" else r"\w+")
        self._token = re.compile("|".join(alternativas))
        self._cache: Dict[str, Optional[str]] = {}

    # --- pasos sobre el texto completo -------------------------------------------------

    def _fecha_iso(self, anio: int, mes: int, dia: int, original: str) -> str:
        if not (1 <= mes <= 12 and 1 <= dia <= 31):
            return original
        sep = "-" if "-" in self.p.formato_fecha else ""
        return f" {anio:04d}{sep}{mes:02d}{sep}{dia:02d} "

    def _fechas(self, texto: str) -> str:
        texto = _FECHA_MDY.sub(
            lambda m: self._fecha_iso(int(m[3]), _MESES[m[1].lower()], int(m[2]), m[0]), texto)
        texto = _FECHA_DMY.sub(
            lambda m: self._fecha_iso(int(m[3]), _MESES[m[2].lower()], int(m[1]), m[0]), texto)
        return _FECHA_NUM.sub(lambda m: self._fecha_iso(int(m[3]), int(m[2]), int(m[1]), m[0]), texto)

    def _conocidas(self, texto: str) -> str:
        """Frases del archivo de entidades (clubes y alias) -> su término canónico."""
        return self._entidades_conocidas.sub(
            lambda m: " " + self._canonico[" ".join(m[0].lower().split())] + " ", texto)

    def _entidades(self, texto: str) -> str:
        """Nombres propios consecutivos ("Kaizer Chiefs") -> un solo término ("Kaizer_Chiefs")."""
        def unir(m):
            palabras = m[0].split(" ")
            while palabras and palabras[0].lower() in self.stop:
                palabras.pop(0)
            if palabras:
                ultima = palabras[-1]
                if ultima.endswith(("'s", "’s")):
                    palabras[-1] = ultima[:-2]
            return " " + "_".join(palabras) + " " if len(palabras) > 1 else " ".join(palabras)
        return _ENTIDAD.sub(unir, texto)

    # --- pasos sobre un token ----------------------------------------------------------

    def _termino(self, crudo: str) -> Optional[str]:
        t = crudo
        if self.p.apostrofes == "posesivo" and ("'" in t or "’" in t):
            if t.endswith(("'s", "’s")):
                t = t[:-2]
            t = t.replace("'", "").replace("’", "")
        if self.p.minusculas:
            t = t.lower()
        if self.p.quitar_acentos and not t.isascii():
            t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
        if not t or len(t) > MAX_LONG_TERMINO or t in self.stop:
            return None
        t = self.sinonimos.get(t, t)
        if self.p.reduccion != "ninguna" and t.isalpha():
            if self.stemmer:
                t = self.stemmer.stem(t)
            else:
                t = self.lemas.get(t, t)
        return t

    def __call__(self, texto: str) -> list:
        p = self.p
        if self._entidades_conocidas:
            texto = self._conocidas(texto)
        if p.nombres == "entidad":
            texto = self._entidades(texto)
        if p.normalizar_fechas:
            texto = self._fechas(texto)
        if p.normalizar_numeros:
            texto = _MILES.sub("", texto)
        cache = self._cache
        if len(cache) > MAX_CACHE:
            cache.clear()
        terminos = []
        for crudo in self._token.findall(texto):
            try:
                t = cache[crudo]
            except KeyError:
                t = cache[crudo] = self._termino(crudo)
            if t is not None:
                terminos.append(t)
        return terminos
