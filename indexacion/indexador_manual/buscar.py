"""Lectura del índice binario y búsqueda por modelo vectorial (tf-idf, similitud coseno)."""
import math
import mmap
import os
import struct
from collections import Counter

import numpy as np

from . import formato as fmt
from .config import cargar
from .normalizacion import Normalizador


class Indice:
    def __init__(self, ruta: str):
        self.ruta = ruta
        self._f = open(ruta, "rb")
        self.mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        campos = fmt.HEADER.unpack_from(self.mm, 0)
        if campos[0] != fmt.MAGIC:
            raise ValueError(f"{ruta} no es un índice PREMIDX")
        (_, self.version, _, self.n_docs, self.n_terminos, self.n_postings, self.tokens_totales,
         self.off_meta, self.off_hosts, self.off_docs, self.off_dict, self.off_post,
         self.tamano) = campos
        n, = struct.unpack_from(">I", self.mm, self.off_meta)
        self.meta = bytes(self.mm[self.off_meta + 4:self.off_meta + 4 + n]).decode("utf-8")
        self.hosts = self._leer_hosts()
        self.docs = np.frombuffer(self.mm, dtype=fmt.DOC_DTYPE, count=self.n_docs,
                                  offset=self.off_docs)
        self.diccionario = self._leer_diccionario()

    def _leer_hosts(self):
        n, = struct.unpack_from(">I", self.mm, self.off_hosts)
        pos, hosts = self.off_hosts + 4, []
        for _ in range(n):
            largo, = struct.unpack_from(">H", self.mm, pos)
            hosts.append(bytes(self.mm[pos + 2:pos + 2 + largo]).decode())
            pos += 2 + largo
        return hosts

    def _leer_diccionario(self):
        """término -> (df, offset absoluto de sus postings, longitud)."""
        mm, pos = self.mm, self.off_dict
        offset, d = self.off_post, {}
        for _ in range(self.n_terminos):
            largo = mm[pos]
            termino = bytes(mm[pos + 1:pos + 1 + largo]).decode("utf-8")
            df, pos = fmt.leer_varint(mm, pos + 1 + largo)
            plen, pos = fmt.leer_varint(mm, pos)
            d[termino] = (df, offset, plen)
            offset += plen
        return d

    def postings(self, termino: str):
        """(doc_ids, tfs) del término, o None si no está en el índice."""
        entrada = self.diccionario.get(termino)
        if entrada is None:
            return None
        _, offset, plen = entrada
        valores = fmt.decodificar_varints(self.mm[offset:offset + plen])
        return np.cumsum(valores[0::2]), valores[1::2]

    def hash_hex(self, doc_id: int) -> str:
        """Hash del documento (64 caracteres). Se lee del arreglo y no del escalar: numpy le quita al
        escalar los bytes finales iguales a cero, y eso rompería 1 de cada 256 hashes."""
        return self.docs["hash"][doc_id:doc_id + 1].tobytes().hex()

    def ruta_documento(self, doc_id: int, repo: str) -> str:
        hash_hex = self.hash_hex(doc_id)
        return os.path.join(repo, self.hosts[int(self.docs[doc_id]["host"])], hash_hex[:2], hash_hex + ".txt")

    def buscar(self, terminos, k: int = 10):
        """Devuelve [(doc_id, similitud coseno)] de los k mejores documentos."""
        consulta = Counter(t for t in terminos if t in self.diccionario)
        if not consulta:
            return []
        puntaje = np.zeros(self.n_docs, dtype=np.float64)
        norma_q2 = 0.0
        for termino, tfq in consulta.items():
            df = self.diccionario[termino][0]
            idf = math.log10(self.n_docs / df)
            wq = (1.0 + math.log10(tfq)) * idf
            norma_q2 += wq * wq
            docs, tfs = self.postings(termino)
            puntaje[docs] += wq * (1.0 + np.log10(tfs)) * idf
        if norma_q2 == 0.0:
            return []
        puntaje /= self.docs["norma"].astype(np.float64) * math.sqrt(norma_q2)
        k = min(k, self.n_docs)
        mejores = np.argpartition(-puntaje, k - 1)[:k]
        mejores = mejores[np.argsort(-puntaje[mejores])]
        return [(int(d), float(puntaje[d])) for d in mejores if puntaje[d] > 0]

    def cerrar(self):
        self.docs = None
        self.mm.close()
        self._f.close()


def buscar(ruta_conf: str, consulta: str, ruta_indice: str = "", k: int = 10):
    politica = cargar(ruta_conf)
    indice = Indice(ruta_indice or politica.salida)
    terminos = Normalizador(politica)(consulta)
    print(f"Términos de la consulta: {terminos}")
    for puesto, (doc_id, sim) in enumerate(indice.buscar(terminos, k), 1):
        ruta = indice.ruta_documento(doc_id, politica.repo)
        try:
            with open(ruta, encoding="utf-8", errors="replace") as f:
                titulo = f.readline().strip()
        except OSError:
            titulo = "(archivo no disponible)"
        host = indice.hosts[int(indice.docs[doc_id]["host"])]
        print(f"{puesto:2d}. {sim:.4f}  {host}  {titulo[:80]}")


def informacion(ruta_indice: str):
    ind = Indice(ruta_indice)
    print(f"Archivo        : {ind.ruta} ({ind.tamano:,} bytes)")
    print(f"Versión        : {ind.version}")
    print(f"Documentos     : {ind.n_docs:,}")
    print(f"Términos       : {ind.n_terminos:,}")
    print(f"Postings       : {ind.n_postings:,}")
    print(f"Tokens totales : {ind.tokens_totales:,}")
    print(f"Hosts          : {len(ind.hosts)}")
    print(f"Secciones      : meta@{ind.off_meta} hosts@{ind.off_hosts} docs@{ind.off_docs} "
          f"diccionario@{ind.off_dict} postings@{ind.off_post}")
    print("Política embebida:")
    print("\n".join("  " + linea for linea in ind.meta.splitlines()))
