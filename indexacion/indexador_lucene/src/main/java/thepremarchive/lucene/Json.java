package thepremarchive.lucene;

import java.util.Map;

/** JSON mínimo para el archivo de resultados (mapas, textos, números y booleanos). */
final class Json {
    private Json() {
    }

    static String escribir(Map<String, ?> m) {
        StringBuilder sb = new StringBuilder();
        valor(sb, m, "");
        return sb.append('\n').toString();
    }

    private static void valor(StringBuilder sb, Object v, String sangria) {
        if (v instanceof Map<?, ?> m) {
            sb.append("{\n");
            int i = 0;
            for (Map.Entry<?, ?> e : m.entrySet()) {
                sb.append(sangria).append("  ");
                texto(sb, e.getKey().toString());
                sb.append(": ");
                valor(sb, e.getValue(), sangria + "  ");
                sb.append(++i < m.size() ? ",\n" : "\n");
            }
            sb.append(sangria).append('}');
        } else if (v instanceof Number || v instanceof Boolean) {
            sb.append(v);
        } else {
            texto(sb, String.valueOf(v));
        }
    }

    private static void texto(StringBuilder sb, String s) {
        sb.append('"');
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        sb.append('"');
    }
}
