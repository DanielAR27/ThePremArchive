package thepremarchive.lucene;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Lectura de una política (.conf, formato INI de Linux). Es el mismo archivo que usa el indexador propio
 * (indexacion/indexador_manual/config.py), con las mismas claves y los mismos valores por omisión, para que
 * las dos implementaciones normalicen igual. Las rutas son relativas a la ubicación del .conf.
 *
 * Además lee una sección opcional [lucene] que el indexador propio ignora:
 *   salida          carpeta del índice (por omisión indices/lucene_X junto a indices/manual_X.idx)
 *   hilos           hilos de indexación (0 = todos los núcleos)
 *   ram_buffer_mb   memoria del IndexWriter antes de volcar un segmento a disco
 *   compresion      BEST_SPEED | BEST_COMPRESSION (campos guardados: hash y host)
 *   fusionar        true = forceMerge(1) al final, deja un único segmento
 */
final class Politica {
    final Path rutaConf;
    final String textoConf;
    final Path repo;
    final Path baseDatos;
    final int temaMinHits;
    final boolean depuracion;
    final Path reglasDepuracion;
    final Path salidaManual;
    final boolean minusculas;
    final String apostrofes;
    final boolean quitarAcentos;
    final Path stopwords;
    final String reduccion;
    final Path lemas;
    final Path sinonimos;
    final String algoritmoStemming;
    final boolean normalizarFechas;
    final String formatoFecha;
    final boolean normalizarNumeros;
    final String nombres;
    final Path entidades;
    final Path salida;
    final int hilos;
    final int ramBufferMb;
    final String compresion;
    final boolean fusionar;

    private Politica(Path rutaConf, String texto, Map<String, Map<String, String>> s) {
        this.rutaConf = rutaConf;
        this.textoConf = texto;
        Path base = rutaConf.getParent();
        Map<String, String> e = seccion(s, "entrada"), n = seccion(s, "normalizacion"),
                i = seccion(s, "indice"), l = s.getOrDefault("lucene", Map.of());

        repo = ruta(base, obligatoria(e, "repo", "entrada"));
        baseDatos = ruta(base, e.getOrDefault("base_datos", ""));
        temaMinHits = Integer.parseInt(e.getOrDefault("tema_min_hits", "0"));
        depuracion = booleano(e.getOrDefault("depuracion", "false"));
        reglasDepuracion = ruta(base, e.getOrDefault("reglas_depuracion", ""));
        salidaManual = ruta(base, obligatoria(i, "salida", "indice"));

        minusculas = booleano(n.getOrDefault("minusculas", "true"));
        apostrofes = elegir(n.getOrDefault("apostrofes", "separar"), "apostrofes", "separar", "posesivo");
        quitarAcentos = booleano(n.getOrDefault("quitar_acentos", "false"));
        stopwords = ruta(base, n.getOrDefault("stopwords", ""));
        reduccion = elegir(n.getOrDefault("reduccion", "ninguna"), "reduccion", "ninguna", "lematizar", "stemming");
        lemas = ruta(base, n.getOrDefault("lemas", ""));
        sinonimos = ruta(base, n.getOrDefault("sinonimos", ""));
        algoritmoStemming = n.getOrDefault("algoritmo_stemming", "porter");
        normalizarFechas = booleano(n.getOrDefault("normalizar_fechas", "false"));
        formatoFecha = elegir(n.getOrDefault("formato_fecha", "YYYY-MM-DD"), "formato_fecha", "YYYY-MM-DD", "YYYYMMDD");
        normalizarNumeros = booleano(n.getOrDefault("normalizar_numeros", "false"));
        nombres = elegir(n.getOrDefault("nombres", "ninguno"), "nombres", "ninguno", "entidad");
        entidades = ruta(base, n.getOrDefault("entidades", ""));
        if (reduccion.equals("stemming") && !algoritmoStemming.equals("porter")) {
            throw new IllegalArgumentException("algoritmo_stemming no soportado: " + algoritmoStemming);
        }

        String nombreManual = salidaManual.getFileName().toString().replaceFirst("\\.idx$", "");
        Path porOmision = salidaManual.resolveSibling(nombreManual.replaceFirst("^manual_", "lucene_"));
        Path s1 = ruta(base, l.getOrDefault("salida", ""));
        salida = s1 != null ? s1 : porOmision;
        int h = Integer.parseInt(l.getOrDefault("hilos", "0"));
        hilos = h > 0 ? h : Runtime.getRuntime().availableProcessors();
        ramBufferMb = Integer.parseInt(l.getOrDefault("ram_buffer_mb", "512"));
        compresion = elegir(l.getOrDefault("compresion", "BEST_COMPRESSION").toUpperCase(Locale.ROOT),
                "compresion", "BEST_SPEED", "BEST_COMPRESSION");
        fusionar = booleano(l.getOrDefault("fusionar", "true"));
    }

    static Politica cargar(String ruta) throws IOException {
        Path p = Path.of(ruta).toAbsolutePath().normalize();
        String texto = Files.readString(p, StandardCharsets.UTF_8);
        return new Politica(p, texto, leerIni(texto));
    }

    /** INI como el configparser de Python: [sección], clave = valor, comentarios con # o ; al inicio
     *  de la línea y con " #" al final; las claves no distinguen mayúsculas. */
    static Map<String, Map<String, String>> leerIni(String texto) {
        Map<String, Map<String, String>> secciones = new HashMap<>();
        Map<String, String> actual = null;
        for (String linea : texto.split("\\R")) {
            String t = linea.strip();
            if (t.isEmpty() || t.startsWith("#") || t.startsWith(";")) {
                continue;
            }
            if (t.startsWith("[") && t.endsWith("]")) {
                actual = secciones.computeIfAbsent(t.substring(1, t.length() - 1).strip(), k -> new HashMap<>());
                continue;
            }
            int igual = t.indexOf('=');
            if (actual == null || igual < 0) {
                throw new IllegalArgumentException("línea inválida en el .conf: " + linea);
            }
            String valor = t.substring(igual + 1);
            int comentario = valor.indexOf(" #");
            if (comentario >= 0) {
                valor = valor.substring(0, comentario);
            }
            actual.put(t.substring(0, igual).strip().toLowerCase(Locale.ROOT), valor.strip());
        }
        return secciones;
    }

    private static Map<String, String> seccion(Map<String, Map<String, String>> s, String nombre) {
        Map<String, String> m = s.get(nombre);
        if (m == null) {
            throw new IllegalArgumentException("falta la sección [" + nombre + "] en el .conf");
        }
        return m;
    }

    private static String obligatoria(Map<String, String> m, String clave, String seccion) {
        String v = m.get(clave);
        if (v == null || v.isEmpty()) {
            throw new IllegalArgumentException("falta " + clave + " en [" + seccion + "]");
        }
        return v;
    }

    private static Path ruta(Path base, String valor) {
        valor = valor.strip();
        return valor.isEmpty() ? null : base.resolve(valor).normalize();
    }

    private static boolean booleano(String v) {
        switch (v.toLowerCase(Locale.ROOT)) {
            case "1": case "yes": case "true": case "on": return true;
            case "0": case "no": case "false": case "off": return false;
            default: throw new IllegalArgumentException("valor booleano inválido: " + v);
        }
    }

    private static String elegir(String valor, String clave, String... validos) {
        if (!List.of(validos).contains(valor)) {
            throw new IllegalArgumentException(clave + " = " + valor + ": se esperaba uno de " + List.of(validos));
        }
        return valor;
    }
}
