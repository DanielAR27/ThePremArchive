package thepremarchive.lucene;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Lectura de las listas de indexacion/config/datos/, con las mismas reglas que normalizacion.py. */
final class Listas {
    private Listas() {
    }

    /** Líneas no vacías y que no empiezan con #, sin espacios a los lados. */
    static List<String> lineas(Path ruta) throws IOException {
        List<String> out = new ArrayList<>();
        for (String linea : Files.readAllLines(ruta, StandardCharsets.UTF_8)) {
            linea = linea.strip();
            if (!linea.isEmpty() && !linea.startsWith("#")) {
                out.add(linea);
            }
        }
        return out;
    }

    static Set<String> stopwords(Path ruta) throws IOException {
        return ruta == null ? Set.of() : new LinkedHashSet<>(lineas(ruta));
    }

    /** forma<TAB>lema */
    static Map<String, String> lemas(Path ruta) throws IOException {
        Map<String, String> mapa = new LinkedHashMap<>();
        for (String linea : lineas(ruta)) {
            int tab = linea.indexOf('\t');
            if (tab < 0) {
                continue;
            }
            String lema = linea.substring(tab + 1).strip();
            if (!lema.isEmpty()) {
                mapa.put(linea.substring(0, tab).strip(), lema);
            }
        }
        return mapa;
    }
}
