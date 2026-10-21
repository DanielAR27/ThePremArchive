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
| **C** | B, más lematización, sinónimos y reconocer clubes y competiciones como una sola unidad. |
| **D** | A más stopwords. Sirve para ver cuánto pesan en el tamaño del índice. |
| **E** | Igual que C, pero con stemming en vez de lematización. |
| **F** | B más sinónimos. Sirve para ver si ayudan o meten ruido. |

Estas son las decisiones y por qué las tomamos:

- **Posesivos.** Si se separa en el apóstrofe, `Arsenal's` deja una `s` suelta, y por eso la `s` aparecía entre las palabras más frecuentes de toda la colección. En B y C se elimina el posesivo y `Arsenal's` queda como `arsenal`.
- **Stopwords.** Partimos de la lista en inglés de NLTK [4], porque la colección está en inglés, y le hicimos varios ajustes. Le quitamos `won` (aparece ahí por venir de "won't", pero en fútbol es una palabra clave) y también `will` y `can`, que además de verbos son nombres de jugadores (Will Hughes, Will Keane, Emre Can): con la lista original, buscar `Will Keane goals` se reducía a `keane goals` y el primer resultado era Michael Keane. Tampoco incluimos `may`, que es el verbo pero también el mes de mayo. Conservar estas tres palabras casi no cuesta nada, porque juntas son el 0.41 % de los postings del índice. En cambio, agregamos los fragmentos que deja separar apóstrofes (`s`, `t`, …) y unos cuantos verbos modales (`could`, `would`, `might`, `must`, `shall`) y el adverbio `also`. Al final son 159 palabras. Revisamos además que ningún país esté en la lista.
- **Lematización y stemming.** Para lematizar usamos WordNet [3] a través de NLTK, pero comete errores en este dominio: por ejemplo, reducía `boss` a `bos` y `wedding` a `wed`. Por eso solo aceptamos reducciones por sufijos regulares, excluimos unas pocas palabras problemáticas y protegimos nombres de clubes escritos en minúscula (`united`, `wolves`, `spurs`). Solo lematizamos palabras que aparecen al menos 20 veces, lo que deja 21 591 reglas. En la política E comparamos contra el algoritmo de Porter [2].
- **Sinónimos.** Mantuvimos la lista corta a propósito: `soccer` con `football`, `goalie` con `goalkeeper`, `ref` con `referee` y poco más. Descartamos pares como `manager` y `coach`, o `loss` y `defeat`, porque en estas noticias no significan lo mismo.
- **Fechas y números.** Las fechas en formatos como `May 6, 2010` o `6/5/2010` pasan a `2010-05-06`. A los números se les quitan los separadores de miles (`1,234` queda en `1234`), para que cuenten como un solo término. Tiene límites que conocemos: no convertimos las fechas con puntos (`11.03.2023`) ni con año de dos dígitos (`09/05/26`), ni las que no traen año (`June 10`), y las del tipo `03/05/2025` las leemos como día/mes (el uso británico), que en fuentes estadounidenses podría significar marzo 5.
- **Clubes y competiciones.** Un archivo con los clubes de la Premier League y las competiciones principales, con sus alias, hace que `Man City`, `man city` y `Manchester City` terminen siendo un solo término (`manchester_city`), y lo mismo con `Premier League` o `World Cup`. Lo importante es que esto funciona igual escrito en mayúsculas o en minúsculas, porque la gente busca en minúsculas. Dejamos afuera a propósito apodos ambiguos como `Citizens` o `Magpies`, que también significan otras cosas. Nuestra primera versión unía cualquier secuencia de palabras con mayúscula (`Kaizer Chiefs`, `Harry Kane`), pero la descartamos al evaluarla: se explica en la sección de evaluación.

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

## 5. ¿Qué tan buenos son los resultados?

El tamaño y el tiempo no lo dicen todo: un índice pequeño no sirve de nada si no encuentra lo que uno busca. Para medir la calidad armamos 12 consultas de fútbol, cada una pensada para poner a prueba una de nuestras decisiones (`man city vs man utd` para los alias de clubes, `soccer transfer deadline day` para los sinónimos, `premier league results 5 May 2012` para las fechas, y así). Corrimos cada consulta en los seis índices y juntamos los 10 primeros resultados de cada política, sin repetir documentos, que es el método del *pool* [1]. Quedaron 247 documentos distintos para marcar como relevantes o no.

Las marcas las propuso una IA con un único criterio, *¿le serviría este artículo a quien escribió esa búsqueda?*, y Daniel las revisó [confirmar tras la revisión]. Los 28 casos donde el criterio era discutible quedaron señalados aparte para revisarlos con más cuidado. Con eso calculamos, para cada política, qué parte de sus 10 primeros resultados era relevante.

Una aclaración sobre las versiones: la primera medición (5.1) se hizo con una lista de stopwords que todavía incluía `will`, `can` y `may`. Después las quitamos (ver la sección 3), reconstruimos los índices y repetimos la evaluación: los promedios casi no se movieron (B subió de 0.52 a 0.53 y F de 0.50 a 0.51; las demás políticas quedaron igual), así que las conclusiones no cambian. Los números que se citan a partir de 5.2 ya son los de la lista nueva.

### 5.1 Primera medición

| Política | Acierto promedio en los 10 primeros resultados |
|---|:---:|
| A | 0.50 |
| B | 0.52 |
| C | 0.40 |
| D | 0.53 |
| E | 0.38 |
| F | 0.50 |

Las políticas simples (A, B, D y F) quedaron parecidas, y las dos más elaboradas (C y E) salieron claramente peores, lo contrario de lo que esperábamos. En `players scoring goals this season`, por ejemplo, pasaron de 0.8 a 0.2, y en `world cup england squad` de 0.5 a 0.0.

Al revisar la causa, el problema era nuestro. En C y E uníamos en un solo término cualquier secuencia de palabras con mayúscula, así que un documento que decía "World Cup" quedaba indexado como `world_cup`. Pero las personas escriben sus búsquedas en minúsculas, y `world cup` en una consulta se convertía en dos términos, `world` y `cup`, que no aparecían tal cual en ese documento. Los índices tenían la información, pero la consulta no podía encontrarla. En el mismo documento "England's World Cup" llegó a quedar como `englands_world_cup`, otro síntoma de lo mismo.

Hubo algo que sí salió bien: la consulta de fechas tiene un único documento relevante (*Arsenal 3-3 Norwich City, 5 de mayo de 2012*), y lo encontraron en el primer puesto las políticas que normalizan fechas (B, C, E y F) pero no las que no lo hacen (A y D).

### 5.2 Corrección y segunda medición

Para arreglarlo cambiamos la regla: en vez de unir cualquier secuencia con mayúscula, C y E solo unen los nombres de una lista de clubes y competiciones, y esa lista se reconoce igual en mayúsculas y en minúsculas. Así la consulta y el documento producen el mismo término (`world_cup`, `premier_league`, `manchester_city`). Reconstruimos los índices C y E y repetimos la evaluación, reutilizando las marcas anteriores y juzgando solo los 30 documentos nuevos.

| Política | Antes | Después |
|---|:---:|:---:|
| C | 0.40 | 0.42 |
| E | 0.38 | 0.41 |

El arreglo ayudó, pero poco: C y E siguen por debajo de B y D (ambas 0.53). Lo que sí cambió mucho es el índice: el vocabulario de C bajó de 1 951 097 a 895 077 términos (el tamaño casi no cambió, de 656 MB a 655 MB), porque ya no se crean cientos de miles de nombres que aparecían una sola vez.

Para entender lo que quedaba miramos la consulta `liverpool injury news`, donde B acierta 0.3 y C 0.0. La consulta se normaliza igual en las dos, pero C sube a los primeros puestos unas páginas de partido de Goal.com ("Liverpool v Chelsea | Goal.com"). Al abrirlas, lo único que dicen sobre lesiones es el encabezado de su plantilla: *"Injuries and Suspensions: No sidelined players"*, es decir, que no hay ninguna. Como C lematiza, `injuries` pasa a ser `injury` y esas páginas, que son cortas y repetitivas, empiezan a coincidir con la búsqueda. B no las encuentra porque no une `injuries` con `injury`.

Es un resultado que no esperábamos y que nos pareció valioso: la lematización une formas de una palabra, que en general ayuda, pero también hace coincidir texto de plantilla de páginas que no tratan del tema. En este corpus, con muchas páginas automáticas y cortas, esa ventaja no alcanza a compensar. La lección que nos dejó el episodio es que cualquier transformación aplicada al texto de los documentos debe aplicarse igual a la consulta, y que una mejora de normalización solo se puede dar por buena si se mide con búsquedas reales.

## 6. Estadísticas de los índices

Como son seis políticas y dos indexadores, organizamos las estadísticas en cuatro tablas: dos que describen cada indexador por separado, una que los compara, y una que mide qué cambia cada decisión de normalización. Todas las cifras son sobre la colección ya depurada (1 010 827 documentos); la política A no usa stopwords, así que no cambia con los ajustes de la lista.

**Tabla 1. Indexador propio**

| Política | Documentos | Tokens | Términos | Postings | Tamaño | Bytes/posting | Tiempo |
|---|---|---|---|---|---|---|---|
| A (base) | 1 010 827 | 900 360 645 | 847 186 | 353 851 101 | 796.6 MB | 2.25 | 4 min 47 s |
| B | 1 010 827 | 602 639 609 | 914 776 | 301 803 452 | 695.4 MB | 2.30 | 9 min 26 s |
| C | 1 010 827 | 591 966 960 | 895 077 | 284 645 213 | 655.2 MB | 2.30 | 11 min 20 s |
| D (A + stopwords) | 1 010 827 | 609 442 978 | 847 027 | 300 254 717 | 689.3 MB | 2.30 | 6 min 47 s |
| E (C con stemming) | 1 010 827 | 591 966 960 | 830 404 | 281 240 444 | 645.0 MB | 2.29 | 11 min 54 s |
| F (B + sinónimos) | 1 010 827 | 602 639 609 | 914 769 | 301 555 105 | 694.9 MB | 2.30 | 9 min 53 s |

Los tiempos de esta tabla son una primera medición: hubo ruido (por ejemplo, D salió bastante más lenta que A aunque hace casi el mismo trabajo), así que los vamos a repetir con el equipo en reposo y en el mismo orden antes de usarlos para comparar.

**Tabla 2. Indexador con Lucene.** Mismas columnas que la Tabla 1. Pendiente, junto con el indexador de Lucene.

**Tabla 3. Indexador propio contra Lucene.** Tamaño y tiempo de cada uno, y cuántas veces más grande o lento es uno que el otro. Pendiente.

**Tabla 4. Efecto de cada decisión (indexador propio, cambio respecto a la segunda política de cada fila)**

| Comparación | Qué se mide | Términos | Postings | Tamaño | Tiempo |
|---|---|---|---|---|---|
| D contra A | efecto de las stopwords | ≈ 0 % | -15 % | -13 % | pendiente |
| E contra C | stemming contra lematización | -7 % | -1 % | -2 % | pendiente |
| F contra B | efecto de los sinónimos | ≈ 0 % | ≈ 0 % | ≈ 0 % | pendiente |
| A contra sin depuración | efecto de depurar la colección | -35 % | -64 % | -62 % | -65 % |

Lo que se puede leer de las cifras que ya tenemos:

- **Las stopwords** son la decisión que más ahorra por sí sola: quitarlas baja un 15 % los postings y un 13 % el tamaño del índice, sin cambiar el vocabulario.
- **La lematización y el reconocimiento de clubes (C)** dejan el índice más pequeño que B (655 MB contra 695 MB) y con menos postings, aunque la política C no resultó mejor al evaluar la calidad (sección 5).
- **Stemming contra lematización (E contra C):** el stemming reduce más el vocabulario (7 % menos de términos), pero casi no cambia el tamaño.
- **Los sinónimos (F contra B)** casi no cambian nada, porque la lista es corta a propósito.
- **La depuración de la colección** es, con diferencia, la decisión de mayor efecto: el índice pasa de 2.10 GB a 0.80 GB (un 62 % menos) y el tiempo de indexación de 13.7 a 4.8 minutos (un 65 % menos).

## 7. Indexador con Apache Lucene

Todavía en desarrollo. Va a procesar la misma colección depurada y aplicar las mismas políticas de normalización, con las mismas listas de stopwords, lemas y sinónimos, para que la comparación con el indexador propio sea justa.

## 8. Comparación entre los dos indexadores

Pendiente, hasta que existan los dos. Vamos a comparar el tamaño de los índices, el tiempo de indexación, la memoria que usa cada uno y cómo guardan por dentro las listas de documentos.

## Referencias

1. Manning, C. D., Raghavan, P. y Schütze, H. (2008). *Introduction to Information Retrieval*. Cambridge University Press.
2. Porter, M. F. (1980). An algorithm for suffix stripping. *Program, 14*(3), 130–137.
3. Fellbaum, C. (ed.) (1998). *WordNet: An Electronic Lexical Database*. MIT Press.
4. Bird, S., Klein, E. y Loper, E. (2009). *Natural Language Processing with Python*. O'Reilly.
5. Heinz, S. y Zobel, J. (2003). Efficient single-pass index construction for text databases. *Journal of the American Society for Information Science and Technology, 54*(8), 713–729.
