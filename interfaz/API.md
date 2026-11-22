# Contrato de la API (borrador para el servidor de búsqueda)

La interfaz (`interfaz/`) habla con el servidor de búsqueda solo por HTTP + JSON. Mientras el servidor no exista, usa un adaptador de prueba (`src/api/mock.js`) que responde con los resultados reales de la entrega 2 y guarda los juicios en el navegador.

- **Conexión:** en desarrollo, Vite redirige `/api/*` a `http://localhost:8000` (se cambia en `vite.config.js`). Para usar el servidor real: `VITE_API=real npm run dev`.
- **Producción:** `npm run build` genera `interfaz/dist/`. El servidor puede servir esa carpeta como archivos estáticos en `/` y la API en `/api`.
- **Convenciones:** nombres de campos en inglés y `camelCase`. Fechas en ISO 8601. Los errores devuelven `{"error": "mensaje legible"}` con el código HTTP correspondiente.

---

## `GET /api/info`

Lo que la interfaz necesita para armar los filtros de la búsqueda avanzada.

```json
{
  "collection": { "documents": 1010827, "crawled": 1440556, "hosts": ["www.bbc.com", "www.theguardian.com"] },
  "engines":  [ { "id": "manual", "label": "Own index" }, { "id": "lucene", "label": "Apache Lucene" } ],
  "policies": [ { "id": "C", "label": "Full", "description": "B plus lemmatization, synonyms and known entities." } ],
  "default":  { "engine": "lucene", "policy": "C" }
}
```

Si solo se carga un motor o una política, se envía solo esa. La interfaz oculta los selectores que tengan una única opción.

## `GET /api/search`

| Parámetro | Tipo | Por defecto | Nota |
|---|---|---|---|
| `q` | texto | (obligatorio) | Consulta tal como la escribió la persona. |
| `engine` | `manual` \| `lucene` | `default.engine` | |
| `policy` | `A`..`F` | `default.policy` | |
| `site` | host | (todos) | Filtro por sitio. El índice ya guarda el host de cada documento. |
| `page` | entero ≥ 1 | 1 | |
| `size` | 10 \| 20 \| 50 | 10 | |

```json
{
  "query": "haaland goals",
  "terms": ["haaland", "goal"],
  "engine": "lucene",
  "policy": "C",
  "site": null,
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
- `total`: cantidad de documentos con puntaje > 0, para la paginación.

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
- Para consultas libres, que no son de prueba, `queryId` es `null` y el servidor agrupa por `query` normalizada.
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
