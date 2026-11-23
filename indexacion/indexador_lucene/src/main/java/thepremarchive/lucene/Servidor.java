package thepremarchive.lucene;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.lucene.document.Document;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.LeafReaderContext;
import org.apache.lucene.index.StoredFields;
import org.apache.lucene.index.Term;
import org.apache.lucene.search.BooleanClause;
import org.apache.lucene.search.BooleanQuery;
import org.apache.lucene.search.IndexSearcher;
import org.apache.lucene.search.Scorable;
import org.apache.lucene.search.ScoreMode;
import org.apache.lucene.search.SimpleCollector;
import org.apache.lucene.search.TermQuery;
import org.apache.lucene.search.similarities.ClassicSimilarity;
import org.apache.lucene.store.FSDirectory;
import org.apache.lucene.util.BytesRef;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

/**
 * Servicio de búsqueda para la aplicación web: abre los índices una sola vez y responde por HTTP. Puede tener varias
 * políticas cargadas a la vez (una por cada --config); la aplicación elige cuál usar en cada consulta.
 *
 *   java -jar indexador-lucene.jar servir --config politica_A.conf --config politica_C.conf [--fechas fechas.bin] [--puerto 8081]
 *
 *   GET /buscar?q=man+city+goals&k=50&policy=C&site=www.bbc.com&from=2026-01-01&to=2026-06-30&sort=newest
 *       -> {"consulta", "terminos", "total", "sin_fecha", "resultados": [{puesto, host, hash, puntaje}], "tiempo_ms"}
 *   GET /salud
 *       -> {"ok": true, "politicas": ["A", "C"], "documentos": N, "fechas": true}
 *
 * Filtros: site (sitio web) y from / to (fecha de publicación, AAAA-MM-DD). Ordenes (sort):
 *   relevance  por puntaje de TF-IDF (por omisión)
 *   newest     por fecha de publicación, de la más reciente a la más antigua (a igual fecha, por puntaje)
 *   recent     por puntaje multiplicado por un factor de frescura que baja a la mitad cada 180 días: un documento
 *              muy relevante pero viejo todavía puede ganarle a uno reciente poco relevante
 * "total" es la cantidad exacta de documentos con puntaje mayor que cero que pasan los filtros. Si se filtra por
 * fecha, los documentos sin fecha conocida no pasan, y "sin_fecha" dice cuántos se dejaron fuera por eso.
 *
 * Solo atiende a la propia máquina (127.0.0.1): la aplicación web es la que se abre al público. Devuelve el hash y el
 * sitio de cada documento; los títulos, las direcciones originales y los fragmentos los agrega la aplicación desde
 * data/crawl.db. Usa la misma cadena de análisis y la misma fórmula de puntaje que el comando "buscar".
 */
final class Servidor {
    private static final int K_MAXIMO = 1000;
    private static final LocalDate BASE_DIAS = LocalDate.of(2000, 1, 1);
    /** Cada cuántos días baja a la mitad el peso de un documento en el orden "recent". */
    private static final double VIDA_MEDIA_DIAS = 180.0;
    /** Factor de frescura de un documento sin fecha: ni premiado ni castigado del todo. */
    private static final double FRESCURA_SIN_FECHA = 0.5;

    private enum Orden { RELEVANCIA, RECIENTES, PONDERADO }

    /** Día de publicación de cada documento (tabla preparada por web_app/preparar_fechas.py), buscada por hash. */
    private static final class Fechas {
        final long[] claves;     // primeros 8 bytes del hash, con signo, ordenados
        final char[] dias;       // días desde 2000-01-01, más 1
        final int masReciente;

        private Fechas(long[] claves, char[] dias) {
            this.claves = claves;
            this.dias = dias;
            int max = 0;
            for (char d : dias) {
                max = Math.max(max, d);
            }
            this.masReciente = max;
        }

        static Fechas cargar(Path ruta) throws IOException {
            ByteBuffer b = ByteBuffer.wrap(Files.readAllBytes(ruta)).order(ByteOrder.LITTLE_ENDIAN);
            byte[] marca = new byte[4];
            b.get(marca);
            if (!new String(marca, StandardCharsets.US_ASCII).equals("PFEC")) {
                throw new IOException(ruta + " no es un archivo de fechas (falta la marca PFEC)");
            }
            b.getInt();                       // versión
            int n = b.getInt();
            long[] claves = new long[n];
            char[] dias = new char[n];
            for (int i = 0; i < n; i++) {
                claves[i] = b.getLong();
                dias[i] = (char) (b.getShort() & 0xFFFF);
            }
            return new Fechas(claves, dias);
        }

        char de(BytesRef hash) {
            long clave = ByteBuffer.wrap(hash.bytes, hash.offset, 8).getLong();   // big-endian, igual que en Python
            int i = Arrays.binarySearch(claves, clave);
            return i < 0 ? 0 : dias[i];
        }
    }

    /** Un índice abierto, con su analizador y (cuando se necesitan) el sitio y la fecha de cada documento. */
    private static final class Abierto {
        final String id;
        final Analizador analizador;
        final DirectoryReader lector;
        final IndexSearcher buscador;
        private volatile short[] sitioDeCadaDoc;
        private volatile char[] diaDeCadaDoc;
        private final Map<String, Short> numeroDeSitio = new ConcurrentHashMap<>();

        Abierto(Politica p) throws IOException {
            String nombre = p.rutaConf.getFileName().toString();           // politica_C.conf
            this.id = nombre.replaceAll("^politica_|\\.conf$", "");
            this.analizador = new Analizador(p);
            this.lector = DirectoryReader.open(FSDirectory.open(p.salida));
            this.buscador = new IndexSearcher(lector);
            this.buscador.setSimilarity(new ClassicSimilarity());
        }

        /**
         * Recorre una vez los campos guardados y recuerda el sitio y el día de publicación de cada documento, para
         * poder filtrar y ordenar. Se reparte entre varios hilos (cada uno con su propio lector de campos guardados)
         * porque son un millón de documentos.
         */
        synchronized void preparar(Fechas fechas) throws IOException {
            if (sitioDeCadaDoc != null) {
                return;
            }
            int total = lector.maxDoc();
            short[] sitios = new short[total];
            char[] dias = new char[total];
            AtomicInteger siguiente = new AtomicInteger();
            int trozos = Math.max(1, Runtime.getRuntime().availableProcessors());
            try {
                java.util.stream.IntStream.range(0, trozos).parallel().forEach(t -> {
                    try {
                        StoredFields campos = lector.storedFields();
                        for (int d = (int) ((long) total * t / trozos); d < (int) ((long) total * (t + 1) / trozos); d++) {
                            Document doc = campos.document(d, Set.of("host", "hash"));
                            sitios[d] = numeroDeSitio.computeIfAbsent(doc.get("host"), h -> (short) siguiente.getAndIncrement());
                            if (fechas != null) {
                                dias[d] = fechas.de(doc.getBinaryValue("hash"));
                            }
                        }
                    } catch (IOException e) {
                        throw new java.io.UncheckedIOException(e);
                    }
                });
            } catch (java.io.UncheckedIOException e) {
                throw e.getCause();
            }
            diaDeCadaDoc = fechas != null ? dias : null;
            sitioDeCadaDoc = sitios;
        }

        int numeroDe(String host) {
            Short n = numeroDeSitio.get(host);
            return n == null ? -1 : n;
        }
    }

    /** Junta los mejores resultados aplicando los filtros de sitio y de fecha, y cuenta todos los que los pasan. */
    private static final class Recolector extends SimpleCollector {
        final int k;
        final Orden orden;
        final short[] sitio;
        final int sitioQuerido;
        final char[] dia;
        final int desde, hasta;
        final boolean filtraFecha;
        final int referencia;
        long total = 0, sinFecha = 0;
        /** Cada entrada: {clave de orden, documento, puntaje}. Es un montículo mínimo: la peor queda arriba. */
        final PriorityQueue<double[]> monton = new PriorityQueue<>(Comparator.comparingDouble((double[] a) -> a[0]));
        private int base;
        private Scorable puntaje;

        Recolector(int k, Orden orden, short[] sitio, int sitioQuerido, char[] dia, int desde, int hasta, int referencia) {
            this.k = k;
            this.orden = orden;
            this.sitio = sitio;
            this.sitioQuerido = sitioQuerido;
            this.dia = dia;
            this.desde = desde;
            this.hasta = hasta;
            this.filtraFecha = desde > 0 || hasta < Integer.MAX_VALUE;
            this.referencia = referencia;
        }

        @Override
        public ScoreMode scoreMode() {
            return ScoreMode.COMPLETE;
        }

        @Override
        protected void doSetNextReader(LeafReaderContext contexto) {
            base = contexto.docBase;
        }

        @Override
        public void setScorer(Scorable s) {
            puntaje = s;
        }

        @Override
        public void collect(int doc) throws IOException {
            int global = base + doc;
            if (sitio != null && sitio[global] != sitioQuerido) {
                return;
            }
            int d = dia == null ? 0 : dia[global];
            if (filtraFecha) {
                if (d == 0) {
                    sinFecha++;
                    return;
                }
                if (d < desde || d > hasta) {
                    return;
                }
            }
            float p = puntaje.score();
            total++;
            double clave;
            switch (orden) {
                case RECIENTES:
                    clave = d + Math.min(p, 999f) / 10000.0;                 // primero la fecha; el puntaje solo desempata
                    break;
                case PONDERADO:
                    clave = p * frescura(d, referencia);
                    break;
                default:
                    clave = p;
            }
            if (monton.size() < k) {
                monton.add(new double[] {clave, global, p});
            } else if (clave > monton.peek()[0]) {
                monton.poll();
                monton.add(new double[] {clave, global, p});
            }
        }
    }

    /** 1 para lo más reciente de la colección, 0.5 a los 180 días, ...; con un piso, para que lo viejo no desaparezca. */
    private static double frescura(int dia, int referencia) {
        if (dia == 0) {
            return FRESCURA_SIN_FECHA;
        }
        double edad = Math.max(0, referencia - dia);
        return 0.3 + 0.7 * Math.pow(2.0, -edad / VIDA_MEDIA_DIAS);
    }

    private Servidor() {
    }

    static void servir(List<String> rutasConf, int puerto, String rutaFechas) throws IOException {
        Map<String, Abierto> abiertos = new LinkedHashMap<>();
        for (String ruta : rutasConf) {
            Abierto a = new Abierto(Politica.cargar(ruta));
            abiertos.put(a.id, a);
        }
        Abierto primero = abiertos.values().iterator().next();
        Fechas fechas = rutaFechas != null && Files.exists(Path.of(rutaFechas)) ? Fechas.cargar(Path.of(rutaFechas)) : null;

        HttpServer http = HttpServer.create(new InetSocketAddress(java.net.InetAddress.getLoopbackAddress(), puerto), 0);
        http.setExecutor(Executors.newFixedThreadPool(Math.max(2, Runtime.getRuntime().availableProcessors())));
        http.createContext("/salud", ex -> {
            StringBuilder sb = new StringBuilder("{\"ok\": true, \"politicas\": [");
            int i = 0;
            for (String id : abiertos.keySet()) {
                sb.append(i++ > 0 ? ", " : "").append(comillas(id));
            }
            responder(ex, 200, sb.append("], \"documentos\": ").append(primero.lector.numDocs())
                    .append(", \"fechas\": ").append(fechas != null).append('}').toString());
        });
        http.createContext("/buscar", ex -> {
            try {
                String q = parametro(ex, "q", "");
                int k = Math.min(K_MAXIMO, Math.max(1, Integer.parseInt(parametro(ex, "k", "10"))));
                Abierto indice = abiertos.get(parametro(ex, "policy", primero.id));
                if (indice == null) {
                    responder(ex, 400, "{\"error\": \"política desconocida\"}");
                    return;
                }
                Orden orden = switch (parametro(ex, "sort", "relevance")) {
                    case "newest" -> Orden.RECIENTES;
                    case "recent" -> Orden.PONDERADO;
                    default -> Orden.RELEVANCIA;
                };
                int desde = dia(parametro(ex, "from", ""), 0);
                int hasta = dia(parametro(ex, "to", ""), Integer.MAX_VALUE);
                if (fechas == null && (orden != Orden.RELEVANCIA || desde > 0 || hasta < Integer.MAX_VALUE)) {
                    responder(ex, 400, "{\"error\": \"las fechas no están cargadas (falta fechas.bin)\"}");
                    return;
                }
                responder(ex, 200, buscar(indice, fechas, q, k, parametro(ex, "site", ""), orden, desde, hasta));
            } catch (NumberFormatException e) {
                responder(ex, 400, "{\"error\": \"k debe ser un número\"}");
            } catch (DateTimeParseException e) {
                responder(ex, 400, "{\"error\": \"las fechas deben ser AAAA-MM-DD\"}");
            } catch (Exception e) {
                responder(ex, 500, "{\"error\": " + comillas(String.valueOf(e.getMessage())) + "}");
            }
        });
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            http.stop(0);
            for (Abierto a : abiertos.values()) {
                try {
                    a.lector.close();
                    a.analizador.close();
                } catch (IOException ignorada) {
                    // se está cerrando el programa
                }
            }
        }));
        http.start();
        // El mapa de sitios y fechas de cada documento se arma en segundo plano, sin hacer esperar la primera búsqueda.
        Thread precalculo = new Thread(() -> {
            for (Abierto a : abiertos.values()) {
                try {
                    a.preparar(fechas);
                } catch (IOException e) {
                    System.err.println("No se pudo preparar el filtro de la política " + a.id + ": " + e.getMessage());
                }
            }
        }, "mapa-de-sitios-y-fechas");
        precalculo.setDaemon(true);
        precalculo.start();
        System.out.println("Servicio de búsqueda listo en http://127.0.0.1:" + puerto + "  (políticas: " + abiertos.keySet()
                + ", " + primero.lector.numDocs() + " documentos" + (fechas != null ? ", con fechas" : ", sin fechas") + ")");
    }

    /** AAAA-MM-DD -> días desde 2000-01-01 más 1 (como en fechas.bin); vacío -> el valor por omisión. */
    private static int dia(String texto, int omision) {
        if (texto.isEmpty()) {
            return omision;
        }
        return (int) ChronoUnit.DAYS.between(BASE_DIAS, LocalDate.parse(texto)) + 1;
    }

    private static String buscar(Abierto indice, Fechas fechas, String consulta, int k, String sitio, Orden orden,
                                 int desde, int hasta) throws IOException {
        long t0 = System.nanoTime();
        List<String> terminos = indice.analizador.terminos(consulta);
        StringBuilder sb = new StringBuilder("{\"consulta\": ").append(comillas(consulta)).append(", \"terminos\": [");
        for (int i = 0; i < terminos.size(); i++) {
            sb.append(i > 0 ? ", " : "").append(comillas(terminos.get(i)));
        }
        sb.append("], ");
        long total = 0, sinFecha = 0;
        StringBuilder filas = new StringBuilder();
        if (!terminos.isEmpty()) {
            BooleanQuery.Builder q = new BooleanQuery.Builder();
            for (String t : terminos) {  // un término repetido suma otra vez, como el tf de la consulta
                q.add(new TermQuery(new Term(Construir.CAMPO, t)), BooleanClause.Occur.SHOULD);
            }
            boolean filtraSitio = !sitio.isEmpty();
            boolean usaFechas = fechas != null && (orden != Orden.RELEVANCIA || desde > 0 || hasta < Integer.MAX_VALUE);
            if (filtraSitio || usaFechas) {
                indice.preparar(fechas);       // la primera vez recorre el índice; casi siempre ya está listo
            }
            Recolector recolector = new Recolector(k, orden, filtraSitio ? indice.sitioDeCadaDoc : null,
                    filtraSitio ? indice.numeroDe(sitio) : -1, usaFechas ? indice.diaDeCadaDoc : null, desde, hasta,
                    fechas != null ? fechas.masReciente : 0);
            indice.buscador.search(q.build(), recolector);
            total = recolector.total;
            sinFecha = recolector.sinFecha;

            List<double[]> mejores = new ArrayList<>(recolector.monton);
            mejores.sort(Comparator.comparingDouble((double[] a) -> a[0]).reversed());
            StoredFields campos = indice.lector.storedFields();
            int puesto = 0;
            for (double[] m : mejores) {
                Document d = campos.document((int) m[1]);
                String hash = HexFormat.of().formatHex(d.getBinaryValue("hash").bytes);
                filas.append(puesto > 0 ? ", " : "").append("{\"puesto\": ").append(++puesto)
                        .append(", \"host\": ").append(comillas(d.get("host")))
                        .append(", \"hash\": \"").append(hash)
                        .append("\", \"puntaje\": ").append(String.format(java.util.Locale.ROOT, "%.6f", m[2])).append('}');
            }
        }
        double ms = (System.nanoTime() - t0) / 1e6;
        return sb.append("\"total\": ").append(total).append(", \"sin_fecha\": ").append(sinFecha)
                .append(", \"resultados\": [").append(filas)
                .append("], \"tiempo_ms\": ").append(String.format(java.util.Locale.ROOT, "%.2f", ms)).append('}').toString();
    }

    private static String parametro(HttpExchange ex, String nombre, String omision) {
        String consulta = ex.getRequestURI().getRawQuery();
        if (consulta != null) {
            for (String par : consulta.split("&")) {
                int igual = par.indexOf('=');
                String clave = igual < 0 ? par : par.substring(0, igual);
                if (clave.equals(nombre)) {
                    return igual < 0 ? "" : URLDecoder.decode(par.substring(igual + 1), StandardCharsets.UTF_8);
                }
            }
        }
        return omision;
    }

    private static void responder(HttpExchange ex, int codigo, String json) throws IOException {
        byte[] cuerpo = json.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        ex.sendResponseHeaders(codigo, cuerpo.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(cuerpo);
        }
    }

    private static String comillas(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (char c : String.valueOf(s).toCharArray()) {
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        return sb.append('"').toString();
    }
}
