package thepremarchive.lucene;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Pasos de normalización que trabajan sobre el texto completo, antes de separar en tokens:
 * entidades conocidas, nombres propios, fechas y separadores de miles. Es la misma lógica y las mismas
 * expresiones regulares que Normalizador.__call__ en indexacion/indexador_manual/normalizacion.py.
 *
 * En Java \w y \d solo reconocen ASCII salvo con UNICODE_CHARACTER_CLASS; en Python 3 son Unicode por
 * omisión. Por eso todas las expresiones llevan esa bandera y la clase de palabra se escribe explícita (W).
 */
final class TransformacionTexto {
    /** \w de Python: letras, números y guion bajo. */
    static final String W = "[\\p{L}\\p{N}_]";
    static final int U = Pattern.UNICODE_CHARACTER_CLASS;
    static final int I = Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE;

    private static final Map<String, Integer> MESES = new LinkedHashMap<>();
    static {
        Object[] m = {"january", 1, "jan", 1, "february", 2, "feb", 2, "march", 3, "mar", 3, "april", 4, "apr", 4,
                "may", 5, "june", 6, "jun", 6, "july", 7, "jul", 7, "august", 8, "aug", 8,
                "september", 9, "sep", 9, "sept", 9, "october", 10, "oct", 10, "november", 11, "nov", 11,
                "december", 12, "dec", 12};
        for (int i = 0; i < m.length; i += 2) {
            MESES.put((String) m[i], (Integer) m[i + 1]);
        }
    }
    // Mismo orden que Python: de la más larga a la más corta, estable entre iguales.
    private static final String MES = MESES.keySet().stream()
            .sorted((a, b) -> b.length() - a.length()).collect(Collectors.joining("|"));
    // "May 6, 2010", "May 6th 2010"
    private static final Pattern FECHA_MDY = Pattern.compile(
            "\\b(" + MES + ")\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?,?\\s+(\\d{4})\\b", U | I);
    // "6 May 2010", "6th of May, 2010"
    private static final Pattern FECHA_DMY = Pattern.compile(
            "\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+(?:of\\s+)?(" + MES + ")\\.?,?\\s+(\\d{4})\\b", U | I);
    // "06/05/2010" (día/mes/año: fuentes británicas)
    private static final Pattern FECHA_NUM = Pattern.compile("\\b(\\d{1,2})/(\\d{1,2})/(\\d{4})\\b", U);
    private static final Pattern MILES = Pattern.compile("(?<=\\d),(?=\\d{3}(?!\\d))", U);
    private static final Pattern ENTIDAD = Pattern.compile(
            "\\b[A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+(?:[ ][A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+)+", U);

    private final Politica p;
    private final Set<String> stop;
    private final Pattern conocidas;
    private final Map<String, String> canonico = new LinkedHashMap<>();
    private final String separadorFecha;

    TransformacionTexto(Politica p, Set<String> stop) throws IOException {
        this.p = p;
        this.stop = stop;
        this.separadorFecha = p.formatoFecha.contains("-") ? "-" : "";
        this.conocidas = p.entidades == null ? null : cargarEntidades();
    }

    /** Frases del archivo de entidades en una sola expresión, de la más larga a la más corta. */
    private Pattern cargarEntidades() throws IOException {
        for (String linea : Listas.lineas(p.entidades)) {
            List<String> campos = Arrays.stream(linea.split("\\|")).map(String::strip)
                    .filter(c -> !c.isEmpty()).collect(Collectors.toList());
            for (String frase : campos.subList(1, campos.size())) {
                canonico.put(clave(frase), campos.get(0));
            }
        }
        List<String> frases = new ArrayList<>(canonico.keySet());
        frases.sort((a, b) -> b.length() - a.length());
        String alternativas = frases.stream()
                .map(f -> Arrays.stream(f.split(" ")).map(Pattern::quote).collect(Collectors.joining("\\s+")))
                .collect(Collectors.joining("|"));
        return Pattern.compile("(?<!" + W + ")(?:" + alternativas + ")(?!" + W + ")", U | I);
    }

    private static final Pattern ESPACIOS = Pattern.compile("\\s+", U);

    /** " ".join(frase.lower().split()) de Python. */
    private static String clave(String frase) {
        return String.join(" ", ESPACIOS.split(frase.toLowerCase(Locale.ROOT).strip()));
    }

    String aplicar(String texto) {
        if (conocidas != null) {
            texto = reemplazar(conocidas, texto, m -> " " + canonico.get(clave(m.group())) + " ");
        }
        if (p.nombres.equals("entidad")) {
            texto = reemplazar(ENTIDAD, texto, this::unirNombres);
        }
        if (p.normalizarFechas) {
            texto = reemplazar(FECHA_MDY, texto, m -> fechaIso(m.group(3), MESES.get(m.group(1).toLowerCase(Locale.ROOT)),
                    m.group(2), m.group()));
            texto = reemplazar(FECHA_DMY, texto, m -> fechaIso(m.group(3), MESES.get(m.group(2).toLowerCase(Locale.ROOT)),
                    m.group(1), m.group()));
            texto = reemplazar(FECHA_NUM, texto, m -> fechaIso(m.group(3), Integer.parseInt(m.group(2)),
                    m.group(1), m.group()));
        }
        if (p.normalizarNumeros) {
            texto = MILES.matcher(texto).replaceAll("");
        }
        return texto;
    }

    private String fechaIso(String anio, int mes, String dia, String original) {
        int d = Integer.parseInt(dia);
        if (mes < 1 || mes > 12 || d < 1 || d > 31) {
            return original;
        }
        return String.format(Locale.ROOT, " %04d%s%02d%s%02d ", Integer.parseInt(anio), separadorFecha, mes,
                separadorFecha, d);
    }

    /** Nombres propios consecutivos ("Kaizer Chiefs") -> un solo término ("Kaizer_Chiefs"). */
    private String unirNombres(Matcher m) {
        List<String> palabras = new ArrayList<>(Arrays.asList(m.group().split(" ")));
        while (!palabras.isEmpty() && stop.contains(palabras.get(0).toLowerCase(Locale.ROOT))) {
            palabras.remove(0);
        }
        if (!palabras.isEmpty()) {
            String ultima = palabras.get(palabras.size() - 1);
            if (ultima.endsWith("'s") || ultima.endsWith("’s")) {
                palabras.set(palabras.size() - 1, ultima.substring(0, ultima.length() - 2));
            }
        }
        return palabras.size() > 1 ? " " + String.join("_", palabras) + " " : String.join(" ", palabras);
    }

    private static String reemplazar(Pattern patron, String texto, java.util.function.Function<Matcher, String> f) {
        Matcher m = patron.matcher(texto);
        if (!m.find()) {
            return texto;
        }
        StringBuilder sb = new StringBuilder(texto.length() + 16);
        int fin = 0;
        do {
            sb.append(texto, fin, m.start()).append(f.apply(m));
            fin = m.end();
        } while (m.find());
        return sb.append(texto, fin, texto.length()).toString();
    }
}
