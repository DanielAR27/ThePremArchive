package thepremarchive.lucene;

import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.text.Normalizer;
import java.util.Locale;

import org.apache.lucene.analysis.CharFilter;
import org.apache.lucene.analysis.TokenFilter;
import org.apache.lucene.analysis.TokenStream;
import org.apache.lucene.analysis.tokenattributes.CharTermAttribute;

/** Piezas de análisis propias, para los pasos que Lucene no trae con el mismo comportamiento. */
final class Filtros {
    private Filtros() {
    }

    /**
     * Aplica TransformacionTexto al documento completo antes del tokenizador. Lee todo el texto de una vez
     * (los documentos son páginas, no archivos gigantes) y no corrige offsets: el índice no guarda
     * posiciones ni offsets, así que no se usan.
     */
    static final class Transformacion extends CharFilter {
        private final TransformacionTexto t;
        private Reader salida;

        Transformacion(Reader entrada, TransformacionTexto t) {
            super(entrada);
            this.t = t;
        }

        @Override
        public int read(char[] buf, int off, int len) throws IOException {
            if (salida == null) {
                StringBuilder sb = new StringBuilder();
                char[] tmp = new char[8192];
                for (int n; (n = input.read(tmp)) != -1; ) {
                    sb.append(tmp, 0, n);
                }
                salida = new StringReader(t.aplicar(sb.toString()));
            }
            return salida.read(buf, off, len);
        }

        @Override
        protected int correct(int offset) {
            return offset;
        }
    }

    /**
     * apostrofes = posesivo: "Arsenal's" -> "Arsenal" y luego quita los apóstrofes internos ("O'Neil" ->
     * "ONeil"). Se aplica antes de pasar a minúsculas, como en Python. No se usa EnglishPossessiveFilter
     * porque ese deja los apóstrofes internos.
     */
    static final class Posesivo extends TokenFilter {
        private final CharTermAttribute term = addAttribute(CharTermAttribute.class);

        Posesivo(TokenStream in) {
            super(in);
        }

        @Override
        public boolean incrementToken() throws IOException {
            if (!input.incrementToken()) {
                return false;
            }
            char[] b = term.buffer();
            int n = term.length();
            boolean tiene = false;
            for (int i = 0; i < n && !tiene; i++) {
                tiene = b[i] == '\'' || b[i] == '’';
            }
            if (tiene) {
                if (n >= 2 && b[n - 1] == 's' && (b[n - 2] == '\'' || b[n - 2] == '’')) {
                    n -= 2;
                }
                int j = 0;
                for (int i = 0; i < n; i++) {
                    if (b[i] != '\'' && b[i] != '’') {
                        b[j++] = b[i];
                    }
                }
                term.setLength(j);
            }
            return true;
        }
    }

    /**
     * minusculas: como str.lower() de Python, que aplica las reglas especiales de Unicode ("İ" -> "i̇").
     * LowerCaseFilter de Lucene convierte carácter por carácter ("İ" -> "i") y los términos no coincidirían.
     */
    static final class Minusculas extends TokenFilter {
        private final CharTermAttribute term = addAttribute(CharTermAttribute.class);

        Minusculas(TokenStream in) {
            super(in);
        }

        @Override
        public boolean incrementToken() throws IOException {
            if (!input.incrementToken()) {
                return false;
            }
            char[] b = term.buffer();
            int n = term.length();
            boolean ascii = true;
            for (int i = 0; i < n; i++) {
                char c = b[i];
                if (c >= 0x80) {
                    ascii = false;
                    break;
                }
                if (c >= 'A' && c <= 'Z') {
                    b[i] = (char) (c + 32);
                }
            }
            if (!ascii) {
                String t = term.toString().toLowerCase(Locale.ROOT);
                term.setEmpty().append(t);
            }
            return true;
        }
    }

    /**
     * quitar_acentos: descomposición NFKD y se quitan las marcas combinantes, igual que
     * unicodedata.normalize("NFKD") + unicodedata.combining() en Python. No se usa ASCIIFoldingFilter porque
     * hace más cosas (ß -> ss, æ -> ae, ø -> o) y los dos índices dejarían de tener los mismos términos.
     */
    static final class QuitarAcentos extends TokenFilter {
        private final CharTermAttribute term = addAttribute(CharTermAttribute.class);

        QuitarAcentos(TokenStream in) {
            super(in);
        }

        @Override
        public boolean incrementToken() throws IOException {
            if (!input.incrementToken()) {
                return false;
            }
            char[] b = term.buffer();
            int n = term.length();
            boolean ascii = true;
            for (int i = 0; i < n && ascii; i++) {
                ascii = b[i] < 0x80;
            }
            if (!ascii) {
                String d = Normalizer.normalize(term, Normalizer.Form.NFKD);
                StringBuilder sb = new StringBuilder(d.length());
                d.codePoints().filter(c -> Character.getType(c) != Character.NON_SPACING_MARK)
                        .forEach(sb::appendCodePoint);
                term.setEmpty().append(sb);
            }
            return true;
        }
    }
}
