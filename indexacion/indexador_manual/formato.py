"""Formato binario del índice (todo en big-endian, legible con `hexdump -C`).

    +-----------------------------+ 0
    | Cabecera (96 bytes)         |
    +-----------------------------+ off_meta
    | Metadatos: u32 n + texto    |   .conf de la política con que se construyó
    +-----------------------------+ off_hosts
    | Hosts: u32 n, n x (u16 len, bytes)
    +-----------------------------+ off_docs
    | Documentos: n_docs x 42 B   |   hash(32) host(u16) n_tokens(u32) norma(f32)
    +-----------------------------+ off_dict
    | Diccionario: n_terms entradas (ordenadas por bytes UTF-8)
    |   u8 len, término, varint df, varint longitud_postings
    +-----------------------------+ off_postings
    | Postings: por término (mismo orden), pares varint (salto_doc_id, tf)
    +-----------------------------+ file_size

Los varint son LEB128 (7 bits por byte, bit alto = continúa). El offset de las postings de cada
término no se guarda: es la suma de las longitudes de los términos anteriores.
"""
import struct

MAGIC = b"PREMIDX1"
VERSION = 1
HEADER = struct.Struct(">8sHHIIQQQQQQQQ")  # 84 bytes + 12 de relleno
HEADER_SIZE = 96
DOC_DTYPE = [("hash", "S32"), ("host", ">u2"), ("n_tokens", ">u4"), ("norma", ">f4")]
DOC_SIZE = 42


def codificar_varint(n: int) -> bytes:
    if n < 0x80:
        return bytes((n,))
    out = bytearray()
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def leer_varint(buf, pos: int):
    resultado = 0
    desplazamiento = 0
    while True:
        b = buf[pos]
        pos += 1
        resultado |= (b & 0x7F) << desplazamiento
        if b < 0x80:
            return resultado, pos
        desplazamiento += 7


def decodificar_varints(payload):
    """Decodifica todos los varint de `payload` a un arreglo numpy (vectorizado)."""
    import numpy as np
    a = np.frombuffer(payload, dtype=np.uint8)
    fin = (a & 0x80) == 0
    indice = np.cumsum(fin) - fin                      # a qué varint pertenece cada byte
    inicios = np.concatenate(([0], np.flatnonzero(fin)[:-1] + 1))
    posicion = np.arange(len(a)) - inicios[indice]     # posición del byte dentro de su varint
    valores = (a & 0x7F).astype(np.float64) * (128.0 ** posicion)
    return np.bincount(indice, weights=valores).astype(np.int64)


def empaquetar_cabecera(n_docs, n_terms, n_postings, total_tokens, off_meta, off_hosts,
                        off_docs, off_dict, off_postings, tam_archivo) -> bytes:
    cab = HEADER.pack(MAGIC, VERSION, 0, n_docs, n_terms, n_postings, total_tokens,
                      off_meta, off_hosts, off_docs, off_dict, off_postings, tam_archivo)
    return cab.ljust(HEADER_SIZE, b"\x00")
