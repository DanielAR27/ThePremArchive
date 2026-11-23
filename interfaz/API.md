# Contrato de la API (borrador para el servidor de búsqueda)

La interfaz (`interfaz/`) habla con el servidor de búsqueda solo por HTTP + JSON. Mientras el servidor no exista, usa un adaptador de prueba (`src/api/mock.js`) que responde con los resultados reales de la entrega 2 y guarda los juicios en el navegador.

- **Conexión:** en desarrollo, Vite redirige `/api/*` a `http://localhost:8000` (se cambia en `vite.config.js`). Para usar el servidor real: `VITE_API=real npm run dev`.
- **Producción:** `npm run build` genera `interfaz/dist/`. El servidor puede servir esa carpeta como archivos estáticos en `/` y la API en `/api`.
- **Modo normal y modo `--dev`:** el servidor se arranca con `python -m web_app` (modo normal, público: solo Lucene con la política C) o con `python -m web_app --dev` (los dos indexadores y las seis políticas). `GET /api/info` devuelve solo lo que el modo ofrece, y la interfaz oculta los selectores cuando hay una sola opción. En modo normal, pedir otro motor o política en `/api/search` responde `403`.
- **Convenciones:** nombres de campos en inglés y `camelCase`. Fechas en ISO 8601. Los errores devuelven `{"error": "mensaje legible"}` con el código HTTP correspondiente.

---

## `GET /api/info`

Lo que la interfaz necesita para armar los filtros de la búsqueda avanzada.

```json
{
  "collection": { "documents": 1010827, "crawled": 1440556, "hosts": ["www.bbc.com", "www.theguardian.com"],
                  "termsByPolicy": { "A": 847186, "C": 895060 },
                  "dates": { "minima": "2000-02-02", "maxima": "2026-09-30", "conFecha": 0.7285 } },
  "engines":  [ { "id": "manual", "label": "Own index" }, { "id": "lucene", "label": "Apache Lucene" } ],
  "policies": [ { "id": "C", "label": "Full", "description": "B plus lemmatization, synonyms and known entities." } ],
  "default":  { "engine": "lucene", "policy": "C" }
}
```

Si solo se carga un motor o una política, se envía solo esa. La interfaz oculta los selectores que tengan una única opción.

- `termsByPolicy`: términos distintos de cada política (el panel "The archive").
- `dates`: rango de fechas de publicación de los documentos indexados y la proporción que tiene fecha (`conFecha`, de 0 a 1). Es `null` si no hay fechas preparadas (`python -m web_app.preparar_fechas`); en ese caso la interfaz oculta los controles de fecha.

## `GET /api/search`

| Parámetro | Tipo | Por defecto | Nota |
|---|---|---|---|
| `q` | texto | (obligatorio) | Consulta tal como la escribió la persona. |
| `engine` | `manual` \| `lucene` | `default.engine` | |
| `policy` | `A`..`F` | `default.policy` | |
| `site` | host | (todos) | Filtro por sitio. El índice ya guarda el host de cada documento. |
| `from` | AAAA-MM-DD | (sin límite) | Solo páginas publicadas desde ese día. |
| `to` | AAAA-MM-DD | (sin límite) | Solo páginas publicadas hasta ese día (incluido). |
| `sort` | `relevance` \| `newest` \| `recent` | `relevance` | Orden de los resultados, ver "Búsqueda por fecha". |
| `page` | entero ≥ 1 | 1 | |
| `size` | 10 \| 20 \| 50 | 10 | |

```json
{
  "query": "haaland goals",
  "terms": ["haaland", "goal"],
  "engine": "lucene",
  "policy": "C",
  "site": null,
  "from": null,
  "to": null,
  "sort": "relevance",
  "undatedHidden": 0,
  "total": 18432,
  "tookMs": 12.4,
  "page": 1,
  "size": 10,
  "results": [
    {
      "rank": 1,
      "doc": "3798494ab985e14e…",
      "score": 0.4123,
      "url": "https://www.bbc.com/sport/football/…",
      "title": "FA Cup: Manchester City 4-0 Liverpool - BBC Sport",
      "host": "www.bbc.com",
      "publishedAt": "2026-04-18",
      "snippet": "Manchester City's Erling Haaland says Pep Guardiola's record…"
    }
  ]
}
```

- `terms`: los términos después de normalizar. La interfaz los muestra para explicar qué se buscó.
- `url`, `title` y `publishedAt` salen de `data/crawl.db` (tabla `documents`), cruzando por `sha256`. `publishedAt` puede ser `null`.
- `snippet`: unos 300 caracteres del texto del documento, idealmente alrededor de la primera aparición de algún término. La interfaz resalta las palabras de `q` y de `terms`.
- `total`: cantidad exacta de documentos con puntaje > 0 que pasan los filtros, para la paginación.
- `testQueryId`: el id (`q01`...) si el texto coincide con una consulta de prueba; si no, `null`.

### Búsqueda por fecha

La fecha de cada documento sale de `published_at` en `crawl.db`, que viene en más de 60 formatos; `python -m web_app.preparar_fechas` los convierte a un número de día y los deja en `web_app/datos/fechas.bin`. Un 73 % de los documentos indexados tiene fecha.

- `from` / `to` filtran por fecha de publicación. Un documento **sin fecha no puede cumplir** el filtro, así que queda fuera; `undatedHidden` dice cuántos documentos que coincidían con la consulta se dejaron fuera por eso (0 si no hay filtro de fecha), para que la interfaz lo muestre.
- `sort=newest`: los más recientes primero (a igual fecha, por puntaje). Los sin fecha van al final.
- `sort=recent`: el puntaje de TF-IDF multiplicado por un factor de frescura `0.3 + 0.7 · 2^(−edad / 180 días)`. La edad se mide desde el documento más reciente de la colección (no desde hoy, porque la colección es una foto). Así un documento muy relevante pero viejo todavía puede ganarle a uno nuevo poco relevante. Es una versión simple de ordenar con una distribución previa a favor de lo reciente (Li y Croft, 2003).
- Una fecha mal escrita o un `sort` desconocido responden `400`.

## `GET /api/queries`

Las consultas de prueba para el modo de evaluación (`indexacion/config/datos/consultas.txt`).

```json
[ { "id": "q01", "text": "haaland goals" } ]
```

## `GET /api/judgments?queryId=q01&evaluator=Sebastián`

Devuelve los juicios guardados. Ambos filtros son opcionales.

```json
[
  {
    "id": 17,
    "queryId": "q01",
    "query": "haaland goals",
    "doc": "3798494ab985e14e…",
    "engine": "lucene",
    "policy": "C",
    "rank": 3,
    "judgment": "relevant",
    "evaluator": "Sebastián",
    "judgedAt": "2026-11-22T15:04:11Z"
  }
]
```

## `POST /api/judgments`

Guarda o reemplaza un juicio. La clave es `(queryId, doc, evaluator)`, así que juzgar de nuevo el mismo documento actualiza el registro en lugar de duplicarlo.

```json
{
  "queryId": "q01",
  "query": "haaland goals",
  "doc": "3798494ab985e14e…",
  "engine": "lucene",
  "policy": "C",
  "rank": 3,
  "judgment": "relevant",
  "evaluator": "Sebastián"
}
```

- `judgment`: `relevant`, `not_relevant` o `unsure`.
- Para consultas libres, que no son de prueba, `queryId` es `null` y el servidor agrupa por `query` normalizada. La interfaz de evaluación las usa cuando la persona escribe una búsqueda propia; `/api/metrics` solo usa las consultas de prueba, porque necesita los mismos 10 resultados de referencia de cada motor y política.
- Responde `201` con el juicio guardado, incluyendo `id` y `judgedAt`.

Se sugiere una tabla SQLite `judgments`, aparte de `crawl.db`, con esas columnas más un índice único sobre `(query_id, doc, evaluator)`.

## `DELETE /api/judgments?evaluator=Sebastián`

Borra todos los juicios de un evaluador. La interfaz lo usa en el botón "Clear my judgments" para que cada persona pueda limpiar sus pruebas. Responde `{"deleted": 4}`. Sin `evaluator`, responde `400`, para no borrar todo por accidente.

## `GET /api/metrics?engine=lucene&policy=C`

Métricas calculadas en el servidor a partir de los juicios y del ranking que devuelve ese motor y esa política para cada consulta. `src/lib/metricas.js` tiene la implementación de referencia, que es la que usa el modo de prueba, por si sirve para portarla.

```json
{
  "engine": "lucene",
  "policy": "C",
  "summary": { "queries": 12, "judged": 427, "evaluators": 3, "p5": 0.62, "p10": 0.55, "mrr": 0.81, "map": 0.58, "ndcg10": 0.66 },
  "perQuery": [
    { "id": "q01", "text": "haaland goals", "judged": 10, "p5": 0.6, "p10": 0.5, "rr": 1.0, "ap": 0.61, "ndcg10": 0.7, "relevantAtRank": [1, 0, 1, 1, 0, 0, 1, 0, 0, 1] }
  ],
  "byConfig": [ { "engine": "manual", "policy": "A", "p10": 0.41, "map": 0.39, "ndcg10": 0.47 } ],
  "activity": [ { "date": "2026-11-21", "judgments": 54 } ],
  "baseline": { "label": "Project 2 pool", "judgments": 427, "relevant": 180, "date": "2026-11-14" }
}
```

`baseline` es opcional. Si el servidor importa los juicios de `estadisticas/evaluacion/pool_juzgado.csv`, los describe aquí y la tabla "Who judged" los muestra como una fila aparte. Si no, va `null`.

Definiciones (Manning, Raghavan y Schütze, 2008, cap. 8). Se calculan sobre el top 10 y los documentos sin juicio cuentan como no relevantes:

- **P@k:** proporción de relevantes entre los primeros k.
- **RR / MRR:** 1 / posición del primer relevante, promediado entre consultas.
- **AP / MAP:** promedio de la precisión en cada posición donde aparece un relevante, dividido entre los relevantes conocidos de la consulta (de todo el pool, con tope de 10) y promediado entre consultas.
- **nDCG@10:** ganancia binaria con descuento log2(posición + 1), normalizada por el ranking ideal.
- `unsure` no cuenta como relevante, pero sí como juzgado.
- `relevantAtRank`: 1, 0 o `null` (sin juicio) por posición, para dibujar la tira de resultados.

## `GET /api/export/judgments.csv` y `GET /api/export/searches.csv`

Los datos en bruto (juicios y búsquedas), para analizarlos aparte, por ejemplo para las conclusiones del documento. Solo se entregan cuando la petición llega desde la propia máquina: si viene por un túnel (trae cabeceras de reenvío como `X-Forwarded-For` o `Cf-Connecting-Ip`) responde `403`, porque incluyen los identificadores de sesión.

## `GET /api/usage`

Estadísticas de uso para el documento (no las usa la interfaz): búsquedas, personas (sesiones por cookie anónima), tiempos, cuántas usaron filtro de sitio o de fecha y qué orden, consultas más frecuentes y búsquedas por día.

## Referencias de la búsqueda por fecha

- Li, X. y Croft, W. B. (2003). Time-based language models. *Proceedings of the 12th International Conference on Information and Knowledge Management (CIKM '03)*, 469–475.
