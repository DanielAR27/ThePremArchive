package thepremarchive.lucene;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import org.sqlite.SQLiteConfig;

/**
 * Qué documentos se indexan: el listado de repo/ y la depuración con data/crawl.db. Es la misma selección
 * que listar_documentos() y depurar() de indexacion/indexador_manual/construir.py, para que los dos
 * índices tengan exactamente los mismos documentos.
 */
final class Coleccion {
    record Doc(String host, String hash, Path ruta) {
    }

    private Coleccion() {
    }

    /** [(host, hash, ruta)] ordenado por (host, hash); con `limite`, una muestra equiespaciada. */
    static List<Doc> listar(Path repo, int limite) throws IOException {
        List<Doc> docs = new ArrayList<>();
        List<Path> hosts;
        try (Stream<Path> s = Files.list(repo)) {
            hosts = s.filter(Files::isDirectory).sorted(Comparator.comparing(x -> x.getFileName().toString()))
                    .collect(Collectors.toList());
        }
        for (Path dirHost : hosts) {
            String host = dirHost.getFileName().toString();
            try (Stream<Path> s = Files.walk(dirHost)) {
                s.filter(Files::isRegularFile).forEach(f -> {
                    String nombre = f.getFileName().toString();
                    if (nombre.endsWith(".txt") && nombre.length() == 64 + 4) {
                        docs.add(new Doc(host, nombre.substring(0, 64), f));
                    }
                });
            }
        }
        docs.sort(Comparator.comparing(Doc::host).thenComparing(Doc::hash));
        if (limite > 0 && docs.size() > limite) {
            double paso = (double) docs.size() / limite;
            List<Doc> muestra = new ArrayList<>(limite);
            for (int i = 0; i < limite; i++) {
                muestra.add(docs.get((int) (i * paso)));
            }
            return muestra;
        }
        return docs;
    }

    /** Conserva los documentos que cumplen alguna regla de depuracion.txt (host, URL o título). */
    static List<Doc> depurar(List<Doc> docs, Path baseDatos, Path reglas) throws IOException {
        if (baseDatos == null || !Files.exists(baseDatos) || reglas == null) {
            throw new IOException("depuracion requiere base_datos y reglas_depuracion: " + baseDatos + " " + reglas);
        }
        Set<String> hosts = new HashSet<>(), sinPaginaTema = new HashSet<>();
        List<String> urls = new ArrayList<>(), titulos = new ArrayList<>();
        int minHits = -1;
        Pattern paginaTema = null;
        for (String linea : Listas.lineas(reglas)) {
            int igual = linea.indexOf('=');
            String clave = linea.substring(0, Math.max(igual, 0)).strip(), valor = linea.substring(igual + 1).strip();
            switch (clave) {
                case "host": hosts.add(valor); break;
                case "url": urls.add(valor); break;
                case "titulo": titulos.add(valor); break;
                case "titulo_hits": {  // "<min_hits> :: <regex>"
                    int sep = valor.indexOf("::");
                    minHits = Integer.parseInt(valor.substring(0, sep).strip());
                    paginaTema = Pattern.compile(valor.substring(sep + 2).strip(), TransformacionTexto.I | TransformacionTexto.U);
                    break;
                }
                case "titulo_hits_excluir_host": sinPaginaTema.add(valor); break;
                default: throw new IOException(reglas + ": regla desconocida " + clave);
            }
        }
        Pattern reUrl = union(urls), reTitulo = union(titulos);

        Set<String> pedidos = docs.stream().map(Doc::hash).collect(Collectors.toSet());
        Set<String> aceptados = new HashSet<>();
        SQLiteConfig cfg = new SQLiteConfig();
        cfg.setReadOnly(true);
        try (Connection con = cfg.createConnection("jdbc:sqlite:" + baseDatos);
             Statement st = con.createStatement();
             ResultSet rs = st.executeQuery("SELECT sha256, host, url, title, topic_hits FROM documents")) {
            while (rs.next()) {
                String sha = rs.getString(1);
                if (!pedidos.contains(sha)) {
                    continue;
                }
                String host = rs.getString(2), url = nulo(rs.getString(3)), titulo = nulo(rs.getString(4));
                int hits = rs.getInt(5);
                if (hosts.contains(host)
                        || (reUrl != null && reUrl.matcher(url).find())
                        || (reTitulo != null && reTitulo.matcher(titulo).find())
                        || (paginaTema != null && !sinPaginaTema.contains(host) && hits >= minHits
                            && paginaTema.matcher(titulo).find())) {
                    aceptados.add(sha);
                }
            }
        } catch (SQLException e) {
            throw new IOException("no se pudo leer " + baseDatos, e);
        }
        return docs.stream().filter(d -> aceptados.contains(d.hash())).collect(Collectors.toList());
    }

    /** tema_min_hits (experimento): descarta documentos con pocas palabras clave del dominio. */
    static List<Doc> filtrarPorTema(List<Doc> docs, Path baseDatos, int minHits) throws IOException {
        Set<String> aceptados = new HashSet<>();
        SQLiteConfig cfg = new SQLiteConfig();
        cfg.setReadOnly(true);
        try (Connection con = cfg.createConnection("jdbc:sqlite:" + baseDatos);
             Statement st = con.createStatement();
             ResultSet rs = st.executeQuery("SELECT sha256, topic_hits FROM documents")) {
            while (rs.next()) {
                if (rs.getInt(2) >= minHits) {
                    aceptados.add(rs.getString(1));
                }
            }
        } catch (SQLException e) {
            throw new IOException("no se pudo leer " + baseDatos, e);
        }
        return docs.stream().filter(d -> aceptados.contains(d.hash())).collect(Collectors.toList());
    }

    private static Pattern union(List<String> partes) {
        if (partes.isEmpty()) {
            return null;
        }
        return Pattern.compile(partes.stream().map(x -> "(?:" + x + ")").collect(Collectors.joining("|")),
                TransformacionTexto.I | TransformacionTexto.U);
    }

    private static String nulo(String s) {
        return s == null ? "" : s;
    }
}
