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
