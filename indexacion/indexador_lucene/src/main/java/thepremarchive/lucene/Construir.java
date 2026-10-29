package thepremarchive.lucene;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.lucene.codecs.lucene912.Lucene912Codec;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.document.FieldType;
import org.apache.lucene.document.StoredField;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.IndexOptions;
import org.apache.lucene.index.IndexWriter;
import org.apache.lucene.index.IndexWriterConfig;
import org.apache.lucene.index.MultiTerms;
import org.apache.lucene.index.Terms;
import org.apache.lucene.index.TermsEnum;
import org.apache.lucene.index.TieredMergePolicy;
import org.apache.lucene.search.similarities.ClassicSimilarity;
import org.apache.lucene.store.Directory;
import org.apache.lucene.store.FSDirectory;
import org.apache.lucene.util.BytesRef;
import org.apache.lucene.util.Version;

/** Construcción del índice Lucene de una política y su archivo de resultados (lucene_X.stats.json). */
final class Construir {
    static final String CAMPO = "contenido";

    /**
     * El texto se indexa con DOCS_AND_FREQS: solo documento y frecuencia, sin posiciones ni offsets, que es
     * lo mismo que guarda el indexador propio. Con posiciones el índice crecería y permitiría búsquedas por
     * frase, que no son parte del modelo vectorial. Las normas sí se guardan: ClassicSimilarity las usa para
     * normalizar por el largo del documento.
     */
    static final FieldType TIPO_CONTENIDO = new FieldType();
    static {
        TIPO_CONTENIDO.setTokenized(true);
        TIPO_CONTENIDO.setStored(false);
        TIPO_CONTENIDO.setIndexOptions(IndexOptions.DOCS_AND_FREQS);
        TIPO_CONTENIDO.setOmitNorms(false);
        TIPO_CONTENIDO.freeze();
    }

    private Construir() {
    }

    static void construir(String rutaConf, int limite, int hilos) throws IOException {
        Politica p = Politica.cargar(rutaConf);
        int nHilos = hilos > 0 ? hilos : p.hilos;
        long t0 = System.nanoTime();

        System.out.println("Listando documentos en " + p.repo + " ...");
        List<Coleccion.Doc> docs = Coleccion.listar(p.repo, limite);
        int sinDepurar = docs.size();
        if (p.depuracion) {
            docs = Coleccion.depurar(docs, p.baseDatos, p.reglasDepuracion);
            System.out.printf("Depuración: %,d de %,d documentos (%.0f%%)%n", docs.size(), sinDepurar,
                    100.0 * docs.size() / sinDepurar);
        }
        if (p.temaMinHits > 0) {
            docs = Coleccion.filtrarPorTema(docs, p.baseDatos, p.temaMinHits);
        }
        if (docs.isEmpty()) {
            throw new IOException("No se encontraron documentos .txt en el repo");
        }
        double segListado = segundos(t0);
        System.out.printf("%,d documentos (%.1f s). Hilos: %d%n", docs.size(), segListado, nHilos);

        Files.createDirectories(p.salida);
        Analizador analizador = new Analizador(p);
        IndexWriterConfig cfg = new IndexWriterConfig(analizador)
                .setOpenMode(IndexWriterConfig.OpenMode.CREATE)
                .setSimilarity(new ClassicSimilarity())
                .setRAMBufferSizeMB(p.ramBufferMb)
                .setUseCompoundFile(false)
                .setCodec(new Lucene912Codec(Lucene912Codec.Mode.valueOf(p.compresion)));
        TieredMergePolicy mp = new TieredMergePolicy();
        mp.setNoCFSRatio(0.0);  // sin archivos compuestos: así se ve el tamaño de cada estructura por separado
        cfg.setMergePolicy(mp);

        long t1 = System.nanoTime();
        int segmentosAntes;
        double segIndexacion, segFusion = 0;
        try (Directory dir = FSDirectory.open(p.salida); IndexWriter w = new IndexWriter(dir, cfg)) {
            indexar(w, docs, nHilos);
            w.commit();
            segIndexacion = segundos(t1);
            try (DirectoryReader r = DirectoryReader.open(dir)) {
                segmentosAntes = r.leaves().size();
            }
            if (p.fusionar) {
                System.out.printf("Fusionando %d segmentos en uno ...%n", segmentosAntes);
                long t2 = System.nanoTime();
                w.forceMerge(1);
                w.commit();
                segFusion = segundos(t2);
            }
        }

        Map<String, Object> stats = estadisticas(p, rutaConf, docs.size(), sinDepurar, limite, nHilos);
        stats.put("segmentos_antes_de_fusionar", segmentosAntes);
        stats.put("segundos_listado", redondear(segListado));
        stats.put("segundos_indexacion", redondear(segIndexacion));
        stats.put("segundos_fusion", redondear(segFusion));
        stats.put("segundos_total", redondear(segundos(t0)));
        Path rutaStats = p.salida.resolveSibling(p.salida.getFileName() + ".stats.json");
        Files.writeString(rutaStats, Json.escribir(stats), StandardCharsets.UTF_8);
        System.out.printf("Índice: %s (%.1f MB, %,d términos, %s s)%n", p.salida,
                ((Number) stats.get("tamano_bytes")).longValue() / 1e6, stats.get("terminos"), stats.get("segundos_total"));
    }

    /** Varios hilos toman documentos de la lista y los agregan al mismo IndexWriter, que es seguro entre hilos. */
    private static void indexar(IndexWriter w, List<Coleccion.Doc> docs, int nHilos) throws IOException {
        AtomicInteger siguiente = new AtomicInteger(), hechos = new AtomicInteger();
        long t = System.nanoTime();
        List<Thread> hilos = new ArrayList<>();
        List<Throwable> errores = new ArrayList<>();
        HexFormat hex = HexFormat.of();
        for (int h = 0; h < nHilos; h++) {
            Thread th = new Thread(() -> {
                try {
                    for (int i; (i = siguiente.getAndIncrement()) < docs.size(); ) {
                        Coleccion.Doc d = docs.get(i);
                        String texto = new String(Files.readAllBytes(d.ruta()), StandardCharsets.UTF_8);
                        Document doc = new Document();
                        doc.add(new Field(CAMPO, texto, TIPO_CONTENIDO));
                        doc.add(new StoredField("hash", new BytesRef(hex.parseHex(d.hash()))));
                        doc.add(new StoredField("host", d.host()));
                        w.addDocument(doc);
                        int n = hechos.incrementAndGet();
                        if (n % 5000 == 0 || n == docs.size()) {
                            System.out.printf("\r  indexación: %,d/%,d docs (%.0f docs/s)", n, docs.size(),
                                    n / segundos(t));
                        }
                    }
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });
            th.setUncaughtExceptionHandler((x, e) -> {
                synchronized (errores) {
                    errores.add(e);
                }
            });
            hilos.add(th);
            th.start();
        }
        for (Thread th : hilos) {
            try {
                th.join();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IOException("interrumpido", e);
            }
        }
        System.out.println();
        if (!errores.isEmpty()) {
            throw new IOException("falló la indexación", errores.get(0));
        }
    }

    /** Mismos nombres de campo que manual_X.idx.stats.json, para que generar_tablas.py los lea igual. */
    static Map<String, Object> estadisticas(Politica p, String rutaConf, int nDocs, int sinDepurar, int limite,
                                            int hilos) throws IOException {
        Map<String, Object> s = new LinkedHashMap<>();
        Map<String, Long> porExtension = new TreeMap<>();
        long tam = 0;
        try (Directory dir = FSDirectory.open(p.salida); DirectoryReader r = DirectoryReader.open(dir)) {
            Terms terms = MultiTerms.getTerms(r, CAMPO);
            long nTerminos = 0;
            TermsEnum te = terms.iterator();
            while (te.next() != null) {
                nTerminos++;
            }
            for (String archivo : dir.listAll()) {
                if (archivo.equals("write.lock")) {
                    continue;
                }
                long largo = dir.fileLength(archivo);
                tam += largo;
                int punto = archivo.lastIndexOf('.');
                porExtension.merge(punto < 0 ? archivo.replaceAll("_\\w+$", "") : archivo.substring(punto), largo,
                        Long::sum);
            }
            s.put("politica", Path.of(rutaConf).getFileName().toString());
            s.put("indexador", "lucene " + Version.LATEST);
            s.put("documentos", r.numDocs());
            s.put("terminos", nTerminos);
            s.put("postings", terms.getSumDocFreq());
            s.put("tokens_totales", terms.getSumTotalTermFreq());
            s.put("tamano_bytes", tam);
            s.put("tamano_por_extension", porExtension);
            s.put("segmentos", r.leaves().size());
        }
        s.put("hilos", hilos);
        s.put("ram_buffer_mb", p.ramBufferMb);
        s.put("compresion", p.compresion);
        s.put("limite", limite);
        s.put("depuracion", p.depuracion);
        s.put("documentos_antes_de_depurar", sinDepurar);
        if (nDocs != ((Number) s.get("documentos")).intValue()) {
            throw new IOException("el índice tiene " + s.get("documentos") + " documentos y se esperaban " + nDocs);
        }
        return s;
    }

    static double segundos(long desde) {
        return (System.nanoTime() - desde) / 1e9;
    }

    static double redondear(double x) {
        return Math.round(x * 100) / 100.0;
    }
}
