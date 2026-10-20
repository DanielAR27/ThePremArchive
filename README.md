# ThePremArchive — arañadores Premier League

Documentación de cada parte:
- Arañador (portada, necesidad de información, políticas, estadísticas, URLs semilla):
  [`documentacion/01_crawler/documentacion_crawler.md`](documentacion/01_crawler/documentacion_crawler.md).
- Indexador (requisitos, reparto y plan):
  [`documentacion/02_indexador/documentacion_indexador.md`](documentacion/02_indexador/documentacion_indexador.md).

Este archivo es solo instrucciones técnicas para correr el código.

## Estructura

- [`common/`](common/) — módulos compartidos por ambos arañadores: políticas
  (`config.py`, `urls.py`, `extract.py`, `dedup.py`) y almacenamiento
  (`store.py`, `bitacora.py`). Define qué se descarga y por qué.
- [`vanilla_spider_premierleague/`](vanilla_spider_premierleague/) — arañador propio en Python
  (hilos, cola propia, descarga con `requests`). Define cómo se arma el motor de arañado.
- [`scrapy_premierleague/`](scrapy_premierleague/) — arañador con Scrapy.
  Reusa `common/` tal cual; solo cambia el motor de arañado.
- [`indexacion/`](indexacion/) — indexadores (manual en Python y Lucene en Java), políticas de
  normalización (`config/`) y benchmark. Pendientes de implementar.

## Instalación

```bash
pip install -r requirements.txt
```

## Arañador propio (Python desde cero, hilos)

Correr **desde la raíz del repo**:

```bash
python -m vanilla_spider_premierleague crawl --target-gb 10 -w 48 --delay 1 --per-domain 3 -d 6
python -m vanilla_spider_premierleague status   # progreso y estadísticas
python -m vanilla_spider_premierleague reset    # tras un corte, devuelve a la cola las URLs en vuelo
```

Detalle de cada política y dónde vive en el código: ver
[`documentacion_crawler.md`](documentacion/01_crawler/documentacion_crawler.md#políticas-de-arañado).

## Arañador con biblioteca (Scrapy)

Correr desde cualquier carpeta (las rutas de salida están ancladas a la raíz
del repo, no a la CWD):

```bash
cd scrapy_premierleague
scrapy crawl premierleague
```

Para una prueba corta antes de dejarlo corriendo horas:

```bash
scrapy crawl premierleague -s CLOSESPIDER_TIMEOUT=60 -s CLOSESPIDER_ITEMCOUNT=100
```

La diferencia real entre ambas implementaciones es el motor de arañado
(hilos propios vs. el scheduler asíncrono de Scrapy) — la lógica de qué
descargar, filtrar y deduplicar es literalmente el mismo código (`common/`).

## Repositorio compartido

**Ambos arañadores escriben al mismo lugar**, sin importar cuál corras:

- `repo/` — el repositorio de texto plano final (`.txt` por documento,
  nombrado por hash de contenido)
- `data/crawl.db` — SQLite con metadatos y el índice de deduplicación
- `logs/bitacora.jsonl` (propio) y `logs/bitacora_scrapy.jsonl` (Scrapy) —
  bitácora de cada URL visitada

Como el nombre de archivo es el hash del contenido, si los dos arañadores
bajan la misma noticia, no se duplica en el repositorio — y el pipeline de
Scrapy consulta la misma base de datos para descartar duplicados y
casi-duplicados contra lo que ya bajó el arañador propio (y viceversa).

```bash
python -m vanilla_spider_premierleague status   # sirve para ver el total combinado de ambos
```

## Indexador manual (Python, archivo binario propio)

Programa aparte de la araña: lee `repo/` y escribe un índice TF-IDF binario en `indices/`.
Correr **desde la raíz del repo**; cada política (`indexacion/config/politica_A..F.conf`) genera un índice:

```bash
python -m indexacion.indexador_manual build --config indexacion/config/politica_A.conf
python -m indexacion.indexador_manual build --config indexacion/config/politica_A.conf --limit 3000   # muestra para probar
python -m indexacion.indexador_manual info indices/manual_A.idx
python -m indexacion.indexador_manual buscar --config indexacion/config/politica_A.conf -k 10 manchester united goals
hexdump -C indices/manual_A.idx | head -20      # el formato está descrito en indexacion/indexador_manual/formato.py
```

Además del `.idx` se escribe `indices/manual_X.idx.stats.json` con tiempos y tamaños.

**Si se interrumpe** (Ctrl+C, corte de luz, cierre del equipo), no se pierde el trabajo: lo ya hecho queda en
`indices/manual_X.idx.tmp/` y basta con volver a ejecutar **el mismo comando** para continuar donde se cortó.
El `.idx` final solo aparece cuando está completo. Si cambia algo que afecta al resultado (el `.conf`, las listas de
`indexacion/config/datos/`, el código de normalización o los documentos), el avance se descarta solo y empieza de cero y
también se puede forzar con `--desde-cero`. Para cambiar la cantidad de procesos al continuar basta con `-p N`
(por ejemplo en un equipo con menos núcleos).

### Estadísticas y tablas del documento

Cada indexador deja un archivo de resultados por índice en `indices/` (`manual_A.idx.stats.json`, `lucene_A.stats.json`…)
con estos campos: `documentos`, `tokens_totales`, `terminos`, `postings`, `tamano_bytes` y `segundos_total`.
El indexador de Lucene debe escribir el suyo con los mismos nombres. Con ellos se arman las tablas del documento:

```bash
python indexacion/herramientas/generar_tablas.py
```
