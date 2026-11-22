package thepremarchive.lucene;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.List;
import java.util.concurrent.Executors;

import org.apache.lucene.document.Document;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.Term;
import org.apache.lucene.search.BooleanClause;
import org.apache.lucene.search.BooleanQuery;
import org.apache.lucene.search.IndexSearcher;
import org.apache.lucene.search.ScoreDoc;
import org.apache.lucene.search.TermQuery;
import org.apache.lucene.search.similarities.ClassicSimilarity;
import org.apache.lucene.store.FSDirectory;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

/**
 * Servicio de búsqueda para la aplicación web: abre el índice una sola vez y responde por HTTP.
 *
 *   java -jar indexador-lucene.jar servir --config indexacion/config/politica_C.conf [--puerto 8081]
 *
 *   GET /buscar?q=man+city+goals&k=50  ->  {"consulta", "terminos", "resultados": [{puesto, host, hash, puntaje}], "tiempo_ms"}
 *   GET /salud                         ->  {"ok": true, "documentos": N}
 *
 * Solo atiende a la propia máquina (127.0.0.1): la aplicación web es la que se abre al público. Devuelve el
 * identificador de cada documento (hash y sitio); los títulos, las direcciones originales y los fragmentos los
 * agrega la aplicación desde data/crawl.db. Usa la misma cadena de análisis y la misma fórmula de puntaje que
 * el comando "buscar", así que da los mismos resultados.
 */
final class Servidor {
    private static final int K_MAXIMO = 1000;

    private Servidor() {
    }

    static void servir(String rutaConf, int puerto) throws IOException {
        Politica p = Politica.cargar(rutaConf);
        Analizador analizador = new Analizador(p);
        DirectoryReader lector = DirectoryReader.open(FSDirectory.open(p.salida));
        IndexSearcher buscador = new IndexSearcher(lector);
        buscador.setSimilarity(new ClassicSimilarity());

        HttpServer http = HttpServer.create(new InetSocketAddress(java.net.InetAddress.getLoopbackAddress(), puerto), 0);
        http.setExecutor(Executors.newFixedThreadPool(Math.max(2, Runtime.getRuntime().availableProcessors())));
        http.createContext("/salud", ex -> responder(ex, 200, "{\"ok\": true, \"documentos\": " + lector.numDocs()
                + ", \"politica\": " + comillas(p.rutaConf.getFileName().toString()) + "}"));
        http.createContext("/buscar", ex -> {
            try {
                String q = parametro(ex, "q", "");
                int k = Math.min(K_MAXIMO, Math.max(1, Integer.parseInt(parametro(ex, "k", "10"))));
                responder(ex, 200, buscar(buscador, analizador, q, k));
            } catch (NumberFormatException e) {
                responder(ex, 400, "{\"error\": \"k debe ser un número\"}");
            } catch (Exception e) {
                responder(ex, 500, "{\"error\": " + comillas(String.valueOf(e.getMessage())) + "}");
            }
        });
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            http.stop(0);
            try {
                lector.close();
                analizador.close();
            } catch (IOException ignorada) {
                // se está cerrando el programa
            }
        }));
        http.start();
        System.out.println("Servicio de búsqueda listo en http://127.0.0.1:" + puerto + "  (índice: " + p.salida
                + ", " + lector.numDocs() + " documentos)");
    }

    private static String buscar(IndexSearcher s, Analizador a, String consulta, int k) throws IOException {
        long t0 = System.nanoTime();
        List<String> terminos = a.terminos(consulta);
        StringBuilder sb = new StringBuilder("{\"consulta\": ").append(comillas(consulta)).append(", \"terminos\": [");
        for (int i = 0; i < terminos.size(); i++) {
            sb.append(i > 0 ? ", " : "").append(comillas(terminos.get(i)));
        }
        sb.append("], \"resultados\": [");
        if (!terminos.isEmpty()) {
            BooleanQuery.Builder q = new BooleanQuery.Builder();
            for (String t : terminos) {  // un término repetido suma otra vez, como el tf de la consulta
                q.add(new TermQuery(new Term(Construir.CAMPO, t)), BooleanClause.Occur.SHOULD);
            }
            int puesto = 0;
            for (ScoreDoc sd : s.search(q.build(), k).scoreDocs) {
                Document d = s.storedFields().document(sd.doc);
                String hash = HexFormat.of().formatHex(d.getBinaryValue("hash").bytes);
                sb.append(puesto > 0 ? ", " : "").append("{\"puesto\": ").append(++puesto)
                        .append(", \"host\": ").append(comillas(d.get("host")))
                        .append(", \"hash\": \"").append(hash)
                        .append("\", \"puntaje\": ").append(String.format(java.util.Locale.ROOT, "%.6f", sd.score)).append('}');
            }
        }
        double ms = (System.nanoTime() - t0) / 1e6;
        return sb.append("], \"tiempo_ms\": ").append(String.format(java.util.Locale.ROOT, "%.2f", ms)).append('}').toString();
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
