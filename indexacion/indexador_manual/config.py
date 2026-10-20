"""Lectura de una política (.conf, formato INI de Linux). Las rutas son relativas al .conf."""
import configparser
import os
from dataclasses import dataclass
from typing import Optional

APOSTROFES = ("separar", "posesivo")
REDUCCIONES = ("ninguna", "lematizar", "stemming")
NOMBRES = ("ninguno", "entidad")
FORMATOS_FECHA = ("YYYY-MM-DD", "YYYYMMDD")


@dataclass(frozen=True)
class Politica:
    ruta_conf: str
    texto_conf: str
    repo: str
    base_datos: Optional[str]
    tema_min_hits: int
    depuracion: bool
    reglas_depuracion: Optional[str]
    salida: str
    minusculas: bool
    apostrofes: str
    quitar_acentos: bool
    stopwords: Optional[str]
    reduccion: str
    lemas: Optional[str]
    sinonimos: Optional[str]
    algoritmo_stemming: str
    normalizar_fechas: bool
    formato_fecha: str
    normalizar_numeros: bool
    nombres: str
    entidades: Optional[str]
    docs_por_bloque: int
    procesos: int


def _elegir(valor: str, validos: tuple, clave: str) -> str:
    if valor not in validos:
        raise ValueError(f"{clave} = {valor!r}: se esperaba uno de {validos}")
    return valor


def cargar(ruta_conf: str) -> Politica:
    ruta_conf = os.path.abspath(ruta_conf)
    base = os.path.dirname(ruta_conf)
    with open(ruta_conf, encoding="utf-8") as f:
        texto = f.read()
    cp = configparser.ConfigParser(inline_comment_prefixes=("#",))
    cp.read_string(texto)

    def ruta(valor: str) -> Optional[str]:
        valor = valor.strip()
        return os.path.normpath(os.path.join(base, valor)) if valor else None

    n, i = cp["normalizacion"], cp["indice"]
    reduccion = _elegir(n.get("reduccion", "ninguna"), REDUCCIONES, "reduccion")
    return Politica(
        ruta_conf=ruta_conf,
        texto_conf=texto,
        repo=ruta(cp["entrada"]["repo"]),
        base_datos=ruta(cp["entrada"].get("base_datos", "")),
        tema_min_hits=cp["entrada"].getint("tema_min_hits", 0),
        depuracion=cp["entrada"].getboolean("depuracion", False),
        reglas_depuracion=ruta(cp["entrada"].get("reglas_depuracion", "")),
        salida=ruta(i["salida"]),
        minusculas=n.getboolean("minusculas", True),
        apostrofes=_elegir(n.get("apostrofes", "separar"), APOSTROFES, "apostrofes"),
        quitar_acentos=n.getboolean("quitar_acentos", False),
        stopwords=ruta(n.get("stopwords", "")),
        reduccion=reduccion,
        lemas=ruta(n.get("lemas", "")),
        sinonimos=ruta(n.get("sinonimos", "")),
        algoritmo_stemming=n.get("algoritmo_stemming", "porter"),
        normalizar_fechas=n.getboolean("normalizar_fechas", False),
        formato_fecha=_elegir(n.get("formato_fecha", "YYYY-MM-DD"), FORMATOS_FECHA, "formato_fecha"),
        normalizar_numeros=n.getboolean("normalizar_numeros", False),
        nombres=_elegir(n.get("nombres", "ninguno"), NOMBRES, "nombres"),
        entidades=ruta(n.get("entidades", "")),
        docs_por_bloque=i.getint("docs_por_bloque", 2000),
        procesos=i.getint("procesos", 0) or (os.cpu_count() or 1),
    )
