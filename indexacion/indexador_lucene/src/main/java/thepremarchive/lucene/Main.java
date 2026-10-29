package thepremarchive.lucene;

import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Uso (desde la raíz del repo):
 *
 *   java -jar indexacion/indexador_lucene/target/indexador-lucene.jar build    --config indexacion/config/politica_A.conf [--limit N] [-t HILOS]
 *   java -jar indexacion/indexador_lucene/target/indexador-lucene.jar buscar   --config indexacion/config/politica_A.conf [-k 10] consulta...
 *   java -jar indexacion/indexador_lucene/target/indexador-lucene.jar info     indices/lucene_A
 *   java -jar indexacion/indexador_lucene/target/indexador-lucene.jar terminos --config indexacion/config/politica_A.conf archivo.txt...
 *
 * "terminos" imprime, por archivo, una línea "ruta<TAB>término término ...": la usa
 * indexacion/herramientas/comparar_normalizacion.py para verificar que Lucene normaliza igual que el indexador propio.
 */
public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        System.setOut(new PrintStream(System.out, true, StandardCharsets.UTF_8));
        if (args.length == 0) {
            uso();
        }
        String config = null;
        int limite = 0, hilos = 0, k = 10;
        List<String> resto = new ArrayList<>();
        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--config": config = args[++i]; break;
                case "--limit": limite = Integer.parseInt(args[++i]); break;
                case "-t": case "--hilos": hilos = Integer.parseInt(args[++i]); break;
                case "-k": k = Integer.parseInt(args[++i]); break;
                default: resto.add(args[i]);
            }
        }
        switch (args[0]) {
            case "build":
                Construir.construir(requerir(config), limite, hilos);
                break;
            case "buscar":
                Buscar.buscar(requerir(config), String.join(" ", resto), k);
                break;
            case "info":
                if (resto.size() != 1) {
                    uso();
                }
                Buscar.info(resto.get(0));
                break;
            case "terminos":
                try (Analizador a = new Analizador(Politica.cargar(requerir(config)))) {
                    for (String ruta : resto) {
                        String texto = new String(Files.readAllBytes(Path.of(ruta)), StandardCharsets.UTF_8);
                        System.out.println(ruta + "\t" + String.join(" ", a.terminos(texto)));
                    }
                }
                break;
            default:
                uso();
        }
    }

    private static String requerir(String config) {
        if (config == null) {
            uso();
        }
        return config;
    }

    private static void uso() {
        System.err.println("uso: indexador-lucene build|buscar|info|terminos ... (ver Main.java)");
        System.exit(2);
    }
}
