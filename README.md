# ThePremArchive

Sistema de recolección e indexación de noticias y documentos sobre la Premier League.

> **Documentación formal del proyecto**
> - **Proyecto 1 – Arañadores:** [`documentacion/01_crawler/documentacion_crawler.md`](documentacion/01_crawler/documentacion_crawler.md)
> - **Proyecto 2 – Indexadores:** [`documentacion/02_indexador/documentacion_indexador.md`](documentacion/02_indexador/documentacion_indexador.md)

Este archivo reúne únicamente las instrucciones rápidas para instalar y ejecutar el código.

---

## Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| [`common/`](common/) | Módulos compartidos por los arañadores (políticas, extracción, deduplicación y almacenamiento). |
| [`vanilla_spider_premierleague/`](vanilla_spider_premierleague/) | Arañador propio en Python (hilos y cola propia). |
| [`scrapy_premierleague/`](scrapy_premierleague/) | Arañador con Scrapy usando las políticas de `common/`. |
| [`indexacion/indexador_manual/`](indexacion/indexador_manual/) | Indexador TF-IDF propio en Python (genera un archivo binario `.idx`). |
| [`indexacion/indexador_lucene/`](indexacion/indexador_lucene/) | Indexador en Java usando Apache Lucene 9.12.3. |
| [`indexacion/config/`](indexacion/config/) | Políticas de normalización (`politica_A..F.conf`) y listas de datos (`datos/`). |
| [`indexacion/herramientas/`](indexacion/herramientas/) | Scripts para construir índices en lote, verificar equivalencia y sacar estadísticas. |
| `repo/` y `data/crawl.db` | Colección de texto plano descargado (`.txt`) y base de datos de metadatos. |
| `indices/` | Índices generados y sus archivos de métricas (`*.stats.json`). |
| [`interfaz/`](interfaz/) | Interfaz web del Proyecto 3 (React + Vite): búsqueda, evaluación y métricas. Ver su [README](interfaz/README.md) y el [contrato de la API](interfaz/API.md). |

---

## Requisitos e instalación

1. **Python** (desde la raíz del repositorio):
   ```bash
   pip install -r requirements.txt
   ```
2. **Java 17+ y Maven** (solo para el indexador con Apache Lucene):
   ```bash
   cd indexacion/indexador_lucene && mvn -q package
   ```
   Esto genera `indexacion/indexador_lucene/target/indexador-lucene.jar`.
3. **Node.js 18+** (solo para la interfaz web):
   ```bash
   cd interfaz && npm install && npm run dev
   ```
   Abre `http://localhost:5173`. Mientras no exista el servidor de búsqueda, usa los resultados guardados de la entrega 2.

---

## 1. Indexador propio (Python)

Ejecutar **desde la raíz del repositorio** (una política a la vez, de `A` a `F`):

```bash
# Construir el índice completo (o usar --limit 3000 para una prueba rápida)
python -m indexacion.indexador_manual build --config indexacion/config/politica_A.conf
python -m indexacion.indexador_manual build --config indexacion/config/politica_A.conf --limit 3000

# Inspeccionar el archivo generado y su contenido binario
python -m indexacion.indexador_manual info indices/manual_A.idx
hexdump -C indices/manual_A.idx | head -20

# Ejecutar una búsqueda de prueba
python -m indexacion.indexador_manual buscar --config indexacion/config/politica_A.conf -k 10 manchester united goals
```

*En Git Bash de Windows, si no tiene `hexdump`, puede usar `xxd indices/manual_A.idx | head -20`.*

**Notas de ejecución:**
- Los índices completos se guardan en `indices/manual_X.idx` (junto con `manual_X.idx.stats.json`).
- Si el proceso se interrumpe, vuelve a correr el mismo comando para retomar desde `indices/manual_X.idx.tmp/`. Usa `--desde-cero` para reiniciar o `-p N` para ajustar el número de procesos.

---

## 2. Indexador con Apache Lucene (Java)

Ejecutar **desde la raíz del repositorio** (tras compilar el `.jar`):

```bash
# Construir el índice completo (o usar --limit 3000 para una prueba rápida)
java -jar indexacion/indexador_lucene/target/indexador-lucene.jar build --config indexacion/config/politica_A.conf
java -jar indexacion/indexador_lucene/target/indexador-lucene.jar build --config indexacion/config/politica_A.conf --limit 3000

# Ver archivos internos del índice
java -jar indexacion/indexador_lucene/target/indexador-lucene.jar info indices/lucene_A

# Buscar o correr todas las consultas de prueba
java -jar indexacion/indexador_lucene/target/indexador-lucene.jar buscar --config indexacion/config/politica_A.conf -k 10 manchester united goals
java -jar indexacion/indexador_lucene/target/indexador-lucene.jar consultas --config indexacion/config/politica_A.conf -k 10 indexacion/config/datos/consultas.txt
java -jar indexacion/indexador_lucene/target/indexador-lucene.jar tiempos --config indexacion/config/politica_A.conf indexacion/config/datos/consultas.txt
```

*Los índices quedan en `indices/lucene_X/` y sus métricas en `indices/lucene_X.stats.json`. A diferencia del manual, si se interrumpe vuelve a empezar desde cero.*

---

## 3. Scripts en lote y evaluación (`indexacion/herramientas/`)

### Construir varias políticas seguidas

```bash
python indexacion/herramientas/construir_indices.py                  # A..F con el indexador propio
python indexacion/herramientas/construir_indices.py B C              # solo políticas específicas
python indexacion/herramientas/construir_indices.py --motor lucene   # A..F con Lucene
python indexacion/herramientas/construir_indices.py --motor ambos    # ambos motores
python indexacion/herramientas/construir_indices.py --simular        # ver comandos sin ejecutar
```

### Verificación, evaluación y estadísticas del informe

| Script | Qué hace |
|---|---|
| `python indexacion/herramientas/comparar_normalizacion.py --config indexacion/config/politica_C.conf --muestra 500` | Verifica que el indexador propio y Lucene generen exactamente los mismos términos. |
| `python indexacion/herramientas/evaluar.py pool` | Reúne los top 10 resultados de todas las políticas en `estadisticas/evaluacion/pool_juzgado.csv`. |
| `python indexacion/herramientas/evaluar.py resultados` | Calcula el acierto (P@10) y coincidencia entre ambos indexadores. |
| `python indexacion/herramientas/generar_tablas.py` | Genera las tablas de estadísticas a partir de `indices/*.stats.json`. |
| `python indexacion/herramientas/medir_consultas.py` | Mide el tiempo de apertura y consulta de cada indexador. |
| `python indexacion/herramientas/estadisticas_extra.py` | Calcula largo de documentos, palabras frecuentes y gráficas en `estadisticas/`. |
| `python indexacion/herramientas/generar_listas.py` | Regenera `stopwords.txt` y `lemas.txt` (requiere descargar `stopwords` y `wordnet` de NLTK). |

---

## 4. Arañadores (Proyecto 1)

Ambos arañadores comparten la deduplicación y escriben en el mismo repositorio (`repo/` y `data/crawl.db`). El detalle de cada política está en [la sección 3 de `documentacion_crawler.md`](documentacion/01_crawler/documentacion_crawler.md#3-políticas-de-arañado).

**Arañador propio** (desde la raíz del repositorio):
```bash
python -m vanilla_spider_premierleague crawl --target-gb 10 -w 48 --delay 1 --per-domain 3 -d 6
python -m vanilla_spider_premierleague status   # progreso combinado de ambos arañadores
python -m vanilla_spider_premierleague reset    # devuelve URLs en vuelo tras un corte
```

**Scrapy:**
```bash
cd scrapy_premierleague
scrapy crawl premierleague
# Prueba corta:
scrapy crawl premierleague -s CLOSESPIDER_TIMEOUT=60 -s CLOSESPIDER_ITEMCOUNT=100
```

---

## Exportar documentación a PDF

Requiere `pip install markdown` y Edge o Chrome instalados. Ejecutar desde la raíz cada vez que se modifique un `.md`:

```bash
python documentacion/exportar_pdf.py documentacion/02_indexador/documentacion_indexador.md
```
