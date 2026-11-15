package thepremarchive.lucene;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;
import java.util.List;

import org.apache.lucene.document.Document;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.LeafReaderContext;
import org.apache.lucene.index.SegmentReader;
import org.apache.lucene.index.Term;
import org.apache.lucene.search.BooleanClause;
import org.apache.lucene.search.BooleanQuery;
import org.apache.lucene.search.IndexSearcher;
import org.apache.lucene.search.ScoreDoc;
import org.apache.lucene.search.TermQuery;
import org.apache.lucene.search.similarities.ClassicSimilarity;
import org.apache.lucene.store.Directory;
import org.apache.lucene.store.FSDirectory;

/** Consultas sobre el índice Lucene (modelo vectorial con ClassicSimilarity) e información del índice. */
final class Buscar {
    private Buscar() {
    }

    static void buscar(String rutaConf, String consulta, int k) throws IOException {
        Politica p = Politica.cargar(rutaConf);
        List<String> terminos;
        try (Analizador a = new Analizador(p)) {
            terminos = a.terminos(consulta);
        }
        System.out.println("Términos de la consulta: " + terminos);
        if (terminos.isEmpty()) {
            return;
        }
        BooleanQuery.Builder q = new BooleanQuery.Builder();
        for (String t : terminos) {  // un término repetido suma su peso otra vez, como el tf de la consulta
            q.add(new TermQuery(new Term(Construir.CAMPO, t)), BooleanClause.Occur.SHOULD);
        }
        try (Directory dir = FSDirectory.open(p.salida); DirectoryReader r = DirectoryReader.open(dir)) {
            IndexSearcher s = new IndexSearcher(r);
            s.setSimilarity(new ClassicSimilarity());
            int puesto = 0;
            for (ScoreDoc sd : s.search(q.build(), k).scoreDocs) {
                Document d = s.storedFields().document(sd.doc);
                String hash = HexFormat.of().formatHex(d.getBinaryValue("hash").bytes);
                String host = d.get("host");
                Path ruta = p.repo.resolve(host).resolve(hash.substring(0, 2)).resolve(hash + ".txt");
                String titulo;
                try (BufferedReader br = Files.newBufferedReader(ruta, StandardCharsets.UTF_8)) {
                    titulo = String.valueOf(br.readLine()).strip();
                } catch (IOException e) {
                    titulo = "(archivo no disponible)";
                }
                System.out.printf("%2d. %.4f  %s  %s%n", ++puesto, sd.score, host,
                        titulo.substring(0, Math.min(80, titulo.length())));
            }
        }
    }

    /**
     * Corre todas las consultas de un archivo (formato "id | consulta | nota", como consultas.txt) y
     * escribe "id<TAB>puesto<TAB>host<TAB>hash<TAB>puntaje" por resultado. La usa
     * indexacion/herramientas/evaluar.py para comparar con el indexador propio abriendo el índice una sola vez.
     */
    static void lote(String rutaConf, String archivoConsultas, int k) throws IOException {
        Politica p = Politica.cargar(rutaConf);
        try (Analizador a = new Analizador(p);
             Directory dir = FSDirectory.open(p.salida);
             DirectoryReader r = DirectoryReader.open(dir)) {
            IndexSearcher s = new IndexSearcher(r);
            s.setSimilarity(new ClassicSimilarity());
            for (String linea : Files.readAllLines(Path.of(archivoConsultas), StandardCharsets.UTF_8)) {
                if (linea.isBlank() || linea.startsWith("#")) {
                    continue;
                }
                String[] campos = linea.split("\\|");
                String id = campos[0].strip();
                BooleanQuery.Builder q = new BooleanQuery.Builder();
                List<String> terminos = a.terminos(campos[1].strip());
                for (String t : terminos) {
                    q.add(new TermQuery(new Term(Construir.CAMPO, t)), BooleanClause.Occur.SHOULD);
                }
                if (terminos.isEmpty()) {
                    continue;
                }
                int puesto = 0;
                for (ScoreDoc sd : s.search(q.build(), k).scoreDocs) {
                    Document d = s.storedFields().document(sd.doc);
                    String hash = HexFormat.of().formatHex(d.getBinaryValue("hash").bytes);
                    System.out.printf(java.util.Locale.ROOT, "%s\t%d\t%s\t%s\t%.6f%n", id, ++puesto, d.get("host"), hash, sd.score);
                }
            }
        }
    }

    /**
     * Mide cuánto tarda en abrirse el índice y cuánto en responder cada consulta de un archivo (analizar la
     * consulta, buscar los k mejores y leer su hash). Cada consulta se repite `repeticiones` veces después de
     * una pasada de calentamiento y se informa la mediana. Salida: "apertura_ms<TAB>x" y "id<TAB>mediana_ms".
     * La usa indexacion/herramientas/medir_consultas.py para compararlo con el indexador propio.
     */
    static void tiempos(String rutaConf, String archivoConsultas, int k, int repeticiones) throws IOException {
        Politica p = Politica.cargar(rutaConf);
        List<String[]> consultas = new java.util.ArrayList<>();
        for (String linea : Files.readAllLines(Path.of(archivoConsultas), StandardCharsets.UTF_8)) {
            if (!linea.isBlank() && !linea.startsWith("#")) {
                String[] c = linea.split("\\|");
                consultas.add(new String[] {c[0].strip(), c[1].strip()});
            }
        }
        java.util.Map<String, List<Double>> medidas = new java.util.HashMap<>();
        try (Analizador a = new Analizador(p)) {
            // El índice se abre dos veces y se informa la segunda, para que el sistema de archivos ya lo tenga en caché,
            // igual que se hace con el indexador propio.
            long apertura = 0;
            IndexSearcher s = null;
            for (int vez = 0; vez < 2; vez++) {
                long t0 = System.nanoTime();
                Directory dir = FSDirectory.open(p.salida);
                DirectoryReader r = DirectoryReader.open(dir);
                s = new IndexSearcher(r);
                s.setSimilarity(new ClassicSimilarity());
                apertura = System.nanoTime() - t0;
                if (vez == 0) {
                    r.close();
                    dir.close();
                }
            }
            System.out.printf(java.util.Locale.ROOT, "apertura_ms\t%.2f%n", apertura / 1e6);
            for (int pasada = -1; pasada < repeticiones; pasada++) {   // la pasada -1 es de calentamiento
                for (String[] c : consultas) {
                    long t0 = System.nanoTime();
                    BooleanQuery.Builder q = new BooleanQuery.Builder();
                    for (String t : a.terminos(c[1])) {
                        q.add(new TermQuery(new Term(Construir.CAMPO, t)), BooleanClause.Occur.SHOULD);
                    }
                    for (ScoreDoc sd : s.search(q.build(), k).scoreDocs) {
                        s.storedFields().document(sd.doc).getBinaryValue("hash");
                    }
                    double ms = (System.nanoTime() - t0) / 1e6;
                    if (pasada >= 0) {
                        medidas.computeIfAbsent(c[0], x -> new java.util.ArrayList<>()).add(ms);
                    }
                }
            }
            for (String[] c : consultas) {
                List<Double> v = medidas.get(c[0]);
                java.util.Collections.sort(v);
                System.out.printf(java.util.Locale.ROOT, "%s\t%.3f%n", c[0], v.get(v.size() / 2));
            }
            s.getIndexReader().close();
        }
    }

    static void info(String rutaIndice) throws IOException {
        Path ruta = Path.of(rutaIndice);
        try (Directory dir = FSDirectory.open(ruta); DirectoryReader r = DirectoryReader.open(dir)) {
            System.out.printf("Índice     : %s%n", ruta.toAbsolutePath());
            System.out.printf("Documentos : %,d%n", r.numDocs());
            System.out.printf("Segmentos  : %d%n", r.leaves().size());
            for (LeafReaderContext hoja : r.leaves()) {
                if (hoja.reader() instanceof SegmentReader sr) {
                    System.out.printf("  %s: %,d docs, códec %s%n", sr.getSegmentName(), sr.maxDoc(),
                            sr.getSegmentInfo().info.getCodec().getName());
                }
            }
            System.out.println("Archivos:");
            long total = 0;
            for (String a : dir.listAll()) {
                long largo = dir.fileLength(a);
                total += largo;
                System.out.printf("  %-28s %,15d bytes  %s%n", a, largo, describir(a));
            }
            System.out.printf("  %-28s %,15d bytes%n", "TOTAL", total);
        }
    }

    /** Qué guarda cada archivo, según la documentación de los formatos de Lucene 9.12. */
    static String describir(String archivo) {
        String ext = archivo.contains(".") ? archivo.substring(archivo.lastIndexOf('.')) : archivo;
        switch (ext) {
            case ".tim": return "diccionario de términos (bloques con prefijos compartidos)";
            case ".tip": return "índice del diccionario (FST en memoria)";
            case ".tmd": return "metadatos del diccionario";
            case ".doc": return "postings: doc_id (deltas) y frecuencias, en bloques de 128";
            case ".psm": return "metadatos de las postings";
            case ".pos": return "posiciones";
            case ".nvd": return "normas (largo de cada documento, 1 byte)";
            case ".nvm": return "metadatos de las normas";
            case ".fdt": return "campos guardados (hash y host), comprimidos";
            case ".fdx": return "índice de los campos guardados";
            case ".fdm": return "metadatos de los campos guardados";
            case ".fnm": return "definición de los campos";
            case ".si": return "información del segmento";
            default: return archivo.startsWith("segments_") ? "punto de commit (lista de segmentos)" : "";
        }
    }
}
