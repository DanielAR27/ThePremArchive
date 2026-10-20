<div align="center">

**Instituto Tecnológico de Costa Rica**  
Escuela de Ingeniería en Computación  
IC8060 – Recuperación de Información Textual  
II Semestre, 2026

# ThePremArchive
### Sistema de Recuperación de Información sobre la Premier League
**Proyecto 2 – Construcción de Índices de Búsqueda**

<img src="../../imagenes/logo.png" alt="Logo ThePremArchive" width="160">

**Profesor:** Aurelio Sanabria Rodríguez

**Integrantes:**  
Daniel de Jesús Alemán Ruiz – 2023051957  
Sebastián Rodríguez Sánchez – 2023074446  

**Fecha de entrega:** Octubre, 2026

</div>

---

## 1. Introducción

Con el arañador del primer proyecto juntamos 1 440 556 documentos de texto plano sobre la Premier League, unos 16 GB. Ahora toca poder buscar en ellos: construir un índice TF-IDF para encontrar los documentos más parecidos a una consulta sin tener que leer toda la colección cada vez.

Lo hacemos de dos maneras, como pide el enunciado. Una es un indexador escrito por nosotros, que guarda el índice en un archivo binario con un formato propio. La otra es con Apache Lucene, usando las mismas políticas de normalización para poder comparar los dos. Las prioridades del enunciado son un índice pequeño y un tiempo de indexación corto, así que cada vez que tuvimos que elegir entre dos opciones nos fijamos en eso y, cuando se pudo, decidimos con datos de nuestra propia colección.

Este documento cuenta lo que ya terminamos, que es el indexador propio y sus decisiones, y deja marcado lo que sigue en desarrollo.

## 2. Primero, mirar qué teníamos

Antes de normalizar nada revisamos la colección, y lo que vimos nos hizo cambiar el plan. Daily Mail es el 13 % de los documentos, pero sus páginas son muy largas y ocupan el **62 % de todo el texto**. Además, solo el 7 % de esas páginas es de fútbol. El resto son sucesos, política y noticias generales. Algo parecido, aunque en menor medida, pasa con las secciones locales de otros diarios.

Lo primero que probamos para limpiar fue usar el conteo de palabras clave de fútbol que la araña dejó guardado en cada documento (`topic_hits`). No funcionó. Las páginas del Daily Mail traen titulares de fútbol en los costados, así que sacan buen puntaje aunque el artículo sea de otra cosa, y al revés, notas cortas y buenas sobre un partido quedaban por debajo del mínimo. Lo probamos en una muestra, vimos que se equivocaba para los dos lados y lo dejamos como un experimento descartado.

Lo que sí funcionó fue una regla más simple, basada en el sitio y en la URL. Los sitios especializados en fútbol (Goal, Transfermarkt, Football365 y otros) entran completos. En los sitios generalistas solo entran las páginas cuya URL o título indican que son de fútbol. Las reglas están en un archivo de texto aparte y son las mismas para todas las políticas, así que la comparación entre ellas sigue siendo justa.

Con esto nos quedamos con 1 010 827 documentos (el 70 %), pero con solo 5.1 GB de texto de los 16.2 GB (el 31 %). En una muestra de 3 000 documentos, el índice de la política más simple pasó de 4.9 MB a 2.0 MB.

Tiene un costo que preferimos decir claro. Probamos 15 consultas de fútbol y 6 de los 150 resultados del top 10 del índice sin depurar quedaron fuera. Son páginas de jugadoras y jugadores poco conocidos, sobre todo del fútbol femenino, que casi no mencionan palabras clave del dominio. Es un sesgo real de la regla. Decidimos aceptarlo a cambio de un índice mucho más pequeño, aunque todavía no medimos cuánto baja el tiempo de indexación.

## 3. Políticas de normalización

Armamos seis políticas. Tres son las que entregamos (A, B y C), y cada una agrega más cuidado a la anterior. Las otras tres cambian **una sola cosa** respecto a alguna de las anteriores, para ver qué efecto tiene esa decisión sin que se mezcle con otras.

| Política | Qué hace |
|---|---|
| **A** | Solo minúsculas y separar en palabras. Es la línea base. |
| **B** | A, más posesivos, quitar acentos, quitar stopwords y unificar fechas y números. |
| **C** | B, más lematización, sinónimos y reconocer nombres propios como una sola unidad. |
| **D** | A más stopwords. Sirve para ver cuánto pesan en el tamaño del índice. |
| **E** | Igual que C, pero con stemming en vez de lematización. |
| **F** | B más sinónimos. Sirve para ver si ayudan o meten ruido. |

Estas son las decisiones y por qué las tomamos:

- **Posesivos.** Si se separa en el apóstrofe, `Arsenal's` deja una `s` suelta, y por eso la `s` aparecía entre las palabras más frecuentes de toda la colección. En B y C se elimina el posesivo y `Arsenal's` queda como `arsenal`.
- **Stopwords.** Partimos de la lista en inglés de NLTK [4], porque la colección está en inglés. Le quitamos `won`, que aparece ahí por venir de "won't", pero en fútbol es una palabra clave. También le agregamos los fragmentos que deja separar apóstrofes y unos cuantos verbos modales (`could`, `would`). Al final son 162 palabras.
- **Lematización y stemming.** Para lematizar usamos WordNet [3] a través de NLTK, pero comete errores en este dominio: por ejemplo, reducía `boss` a `bos` y `wedding` a `wed`. Por eso solo aceptamos reducciones por sufijos regulares, excluimos unas pocas palabras problemáticas y protegimos nombres de clubes escritos en minúscula (`united`, `wolves`, `spurs`). Solo lematizamos palabras que aparecen al menos 20 veces, lo que deja 21 591 reglas. En la política E comparamos contra el algoritmo de Porter [2].
- **Sinónimos.** Mantuvimos la lista corta a propósito: `soccer` con `football`, `goalie` con `goalkeeper`, `ref` con `referee` y poco más. Descartamos pares como `manager` y `coach`, o `loss` y `defeat`, porque en estas noticias no significan lo mismo.
- **Fechas y números.** Las fechas en formatos como `May 6, 2010` o `6/5/2010` pasan a `2010-05-06`. A los números se les quitan los separadores de miles (`1,234` queda en `1234`), para que cuenten como un solo término.
- **Nombres propios.** Los nombres propios con mayúscula seguidos (`Kaizer Chiefs`) se tratan como un solo término. Además, un archivo con los clubes de la Premier League y sus alias hace que `Man City`, `man city` y `Manchester City` terminen siendo lo mismo. Dejamos afuera a propósito apodos ambiguos como `Citizens` o `Magpies`, que también significan otras cosas.

## 4. El índice propio

El índice sigue el modelo vectorial. Cada documento es una lista de pesos, uno por término. El peso sube con las veces que el término aparece en el documento (tf) y baja cuanto más documentos lo contienen (idf). La consulta se convierte en una lista igual, y se compara con cada documento usando el coseno [1].

Para no cargar toda la colección en memoria, usamos la idea de SPIMI [5]. Varios procesos leen y normalizan los documentos en paralelo, cada uno guarda pequeños índices ordenados en bloques, y al final los bloques se mezclan en uno solo. Como construir la colección completa lleva horas, el proceso guarda su avance: cada bloque se escribe primero con un nombre temporal y se renombra solo cuando está completo, así que si se corta la luz o se cierra el programa, al volver a ejecutarlo continúa donde se quedó. Lo comprobamos matando el proceso a la fuerza varias veces y verificando que el índice final sale idéntico byte a byte al de una ejecución sin interrupciones.

### 4.1 Cómo está organizado el archivo

Todo queda en un único archivo, con las partes una detrás de otra:

```text
+----------+-----------+--------+------------+-------------+------------+
| Cabecera | Metadatos | Hosts  | Documentos | Diccionario | Postings   |
| 96 bytes | config    | sitios | uno por    | términos    | documentos |
|          |           |        | documento  | ordenados   | por término|
+----------+-----------+--------+------------+-------------+------------+
```

| Parte | Qué guarda |
|---|---|
| **Cabecera** | Una marca de formato (`PREMIDX1`), la versión, cuántos documentos y términos hay, y en qué posición del archivo empieza cada parte. |
| **Metadatos** | El archivo de configuración con que se construyó el índice, para que el propio archivo diga de qué política viene. |
| **Hosts** | La lista de sitios de origen, para no repetir su nombre en cada documento. |
| **Documentos** | Un registro de tamaño fijo por documento (42 bytes): su hash, su sitio, cuántas palabras tiene y su norma, que se usa para calcular el coseno. |
| **Diccionario** | Todos los términos en orden. Cada uno guarda en cuántos documentos aparece y cuánto ocupan sus postings. |
| **Postings** | Para cada término, los documentos donde aparece y cuántas veces. |

Para que el archivo ocupe poco, en las postings no se guarda el número de cada documento completo sino la diferencia con el anterior, y los enteros se escriben con los bytes justos (los menores de 128 ocupan uno solo). Los números de tamaño fijo van en *big-endian*, que es el orden en que uno los lee de corrido en un volcado hexadecimal. Así empieza un índice de prueba de 3 000 documentos visto con `hexdump -C`:

```text
00000000  50 52 45 4d 49 44 58 31  00 01 00 00 00 00 0b b8  |PREMIDX1........|
00000010  00 01 69 00 00 00 00 00  00 1c 61 40 00 00 00 00  |..i.......a@....|
```

- `50 52 45 4d 49 44 58 31` es la marca `PREMIDX1`.
- `00 01` es la versión del formato (1), seguida de dos bytes reservados en cero.
- `00 00 0b b8` es el número de documentos: 3 000.
- `00 01 69 00` es el número de términos distintos: 92 416.

## 5. Estadísticas de los índices

Pendiente de completar cuando terminemos de construir la colección completa. Como son seis políticas y dos indexadores, organizamos las estadísticas en cuatro tablas. Las dos primeras describen cada indexador por separado, la tercera los pone lado a lado, y la cuarta mide qué cambia cada decisión de normalización.

**Tabla 1. Indexador propio**

| Política | Documentos | Tokens | Términos | Postings | Tamaño | Bytes/posting | Tiempo |
|---|---|---|---|---|---|---|---|
| A (base) | — | — | — | — | — | — | — |
| B | — | — | — | — | — | — | — |
| C | — | — | — | — | — | — | — |
| D (A + stopwords) | — | — | — | — | — | — | — |
| E (C con stemming) | — | — | — | — | — | — | — |
| F (B + sinónimos) | — | — | — | — | — | — | — |

**Tabla 2. Indexador con Lucene.** Mismas columnas que la Tabla 1.

**Tabla 3. Indexador propio contra Lucene**

| Política | Tamaño propio | Tamaño Lucene | Razón | Tiempo propio | Tiempo Lucene | Razón |
|---|---|---|---|---|---|---|
| A a F | — | — | — | — | — | — |

**Tabla 4. Efecto de cada decisión** (indexador propio, cambio respecto a la segunda política de cada fila)

| Comparación | Qué se mide | Términos | Postings | Tamaño | Tiempo |
|---|---|---|---|---|---|
| D contra A | efecto de las stopwords | — | — | — | — |
| E contra C | stemming contra lematización | — | — | — | — |
| F contra B | efecto de los sinónimos | — | — | — | — |
| A contra sin depuración | efecto de depurar la colección | — | — | — | — |

## 6. Indexador con Apache Lucene

Todavía en desarrollo. Va a procesar la misma colección depurada y aplicar las mismas políticas de normalización, con las mismas listas de stopwords, lemas y sinónimos, para que la comparación con el indexador propio sea justa.

## 7. Comparación entre los dos indexadores

Pendiente, hasta que existan los dos. Vamos a comparar el tamaño de los índices, el tiempo de indexación, la memoria que usa cada uno y cómo guardan por dentro las listas de documentos.

## Referencias

1. Manning, C. D., Raghavan, P. y Schütze, H. (2008). *Introduction to Information Retrieval*. Cambridge University Press.
2. Porter, M. F. (1980). An algorithm for suffix stripping. *Program, 14*(3), 130–137.
3. Fellbaum, C. (ed.) (1998). *WordNet: An Electronic Lexical Database*. MIT Press.
4. Bird, S., Klein, E. y Loper, E. (2009). *Natural Language Processing with Python*. O'Reilly.
5. Heinz, S. y Zobel, J. (2003). Efficient single-pass index construction for text databases. *Journal of the American Society for Information Science and Technology, 54*(8), 713–729.
