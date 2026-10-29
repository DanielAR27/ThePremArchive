package thepremarchive.lucene;

import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.text.ParseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

import org.apache.lucene.analysis.Analyzer;
import org.apache.lucene.analysis.CharArraySet;
import org.apache.lucene.analysis.StopFilter;
import org.apache.lucene.analysis.TokenStream;
import org.apache.lucene.analysis.Tokenizer;
import org.apache.lucene.analysis.core.FlattenGraphFilter;
import org.apache.lucene.analysis.core.WhitespaceAnalyzer;
import org.apache.lucene.analysis.en.PorterStemFilter;
import org.apache.lucene.analysis.miscellaneous.CodepointCountFilter;
import org.apache.lucene.analysis.miscellaneous.PatternKeywordMarkerFilter;
import org.apache.lucene.analysis.miscellaneous.StemmerOverrideFilter;
import org.apache.lucene.analysis.pattern.PatternTokenizer;
import org.apache.lucene.analysis.synonym.SolrSynonymParser;
import org.apache.lucene.analysis.synonym.SynonymGraphFilter;
import org.apache.lucene.analysis.synonym.SynonymMap;
import org.apache.lucene.analysis.tokenattributes.CharTermAttribute;

/**
 * Analizador de Lucene armado a partir de una política. Reproduce, en el mismo orden, los pasos de
 * Normalizador en indexacion/indexador_manual/normalizacion.py:
 *
 *   texto completo : entidades conocidas, nombres propios, fechas, miles   (Filtros.Transformacion)
 *   tokenizador    : misma expresión regular que Python                    (PatternTokenizer)
 *   por token      : posesivo -> minúsculas -> acentos -> largo <= 40 -> stopwords -> sinónimos
 *                    -> lema o stem, solo si el token es todo letras
 */
final class Analizador extends Analyzer {
    static final int MAX_LONG_TERMINO = 40;

    private final Politica p;
    private final TransformacionTexto transformacion;
    private final Pattern token;
    private final CharArraySet stop;
    private final SynonymMap sinonimos;
    private final StemmerOverrideFilter.StemmerOverrideMap lemas;
    // isalpha() de Python: un token con algo que no sea letra no se lematiza ni se reduce.
    private static final Pattern NO_SOLO_LETRAS = Pattern.compile(".*[^\\p{L}].*", Pattern.DOTALL);

    Analizador(Politica p) throws IOException {
        this.p = p;
        Set<String> listaStop = Listas.stopwords(p.stopwords);
        this.stop = listaStop.isEmpty() ? null : new CharArraySet(listaStop, false);
        this.transformacion = new TransformacionTexto(p, listaStop);
        this.token = Pattern.compile(patronToken(p), TransformacionTexto.U);
        this.sinonimos = p.sinonimos == null ? null : cargarSinonimos(p);
        this.lemas = p.reduccion.equals("lematizar") && p.lemas != null ? cargarLemas(p) : null;
    }

    static String patronToken(Politica p) {
        List<String> alternativas = new ArrayList<>();
        if (p.normalizarFechas && p.formatoFecha.contains("-")) {
            alternativas.add("\\d{4}-\\d{2}-\\d{2}");
        }
        if (p.normalizarNumeros) {
            alternativas.add("\\d+\\.\\d+");
        }
        String w = TransformacionTexto.W;
        alternativas.add(p.apostrofes.equals("posesivo") ? w + "+(?:['’]" + w + "+)*" : w + "+");
        return String.join("|", alternativas);
    }

    /** Formato de sinonimos.txt: "canónico, sinónimo, ...". Con expand=false SolrSynonymParser reemplaza
     *  cada palabra del grupo por la primera, que es lo mismo que hace el indexador propio. */
    private static SynonymMap cargarSinonimos(Politica p) throws IOException {
        StringBuilder reglas = new StringBuilder();
        for (String linea : Listas.lineas(p.sinonimos)) {
            reglas.append(linea).append('\n');
        }
        try (Analyzer a = new WhitespaceAnalyzer()) {
            SolrSynonymParser parser = new SolrSynonymParser(true, false, a);
            parser.parse(new StringReader(reglas.toString()));
            return parser.build();
        } catch (ParseException e) {
            throw new IOException("sinonimos inválidos: " + p.sinonimos, e);
        }
    }

    private static StemmerOverrideFilter.StemmerOverrideMap cargarLemas(Politica p) throws IOException {
        StemmerOverrideFilter.Builder b = new StemmerOverrideFilter.Builder(false);
        for (Map.Entry<String, String> e : Listas.lemas(p.lemas).entrySet()) {
            b.add(e.getKey(), e.getValue());
        }
        return b.build();
    }

    @Override
    protected Reader initReader(String campo, Reader reader) {
        return new Filtros.Transformacion(reader, transformacion);
    }

    @Override
    protected TokenStreamComponents createComponents(String campo) {
        Tokenizer fuente = new PatternTokenizer(token, 0);
        TokenStream t = fuente;
        if (p.apostrofes.equals("posesivo")) {
            t = new Filtros.Posesivo(t);
        }
        if (p.minusculas) {
            t = new Filtros.Minusculas(t);
        }
        if (p.quitarAcentos) {
            t = new Filtros.QuitarAcentos(t);
        }
        t = new CodepointCountFilter(t, 1, MAX_LONG_TERMINO);
        if (stop != null) {
            t = new StopFilter(t, stop);
        }
        if (sinonimos != null) {
            // En indexación, SynonymGraphFilter debe ir seguido de FlattenGraphFilter.
            t = new FlattenGraphFilter(new SynonymGraphFilter(t, sinonimos, false));
        }
        if (!p.reduccion.equals("ninguna")) {
            t = new PatternKeywordMarkerFilter(t, NO_SOLO_LETRAS);
            if (lemas != null) {
                t = new StemmerOverrideFilter(t, lemas);
            } else if (p.reduccion.equals("stemming")) {
                t = new PorterStemFilter(t);
            }
        }
        return new TokenStreamComponents(fuente, t);
    }

    /** Términos de un texto, en orden (para comparar con el indexador propio y para las consultas). */
    List<String> terminos(String texto) throws IOException {
        List<String> out = new ArrayList<>();
        try (TokenStream ts = tokenStream(Construir.CAMPO, texto)) {
            CharTermAttribute term = ts.addAttribute(CharTermAttribute.class);
            ts.reset();
            while (ts.incrementToken()) {
                out.add(term.toString());
            }
            ts.end();
        }
        return out;
    }
}
