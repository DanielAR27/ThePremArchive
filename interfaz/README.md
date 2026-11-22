# Interfaz web (Proyecto 3)

Aplicación en React + Vite con tres modos: **Search** (búsqueda y resultados), **Evaluate** (juicios de relevancia) y **Metrics** (MAP, MRR, P@5, P@10 y nDCG@10 con gráficos). El sitio está en inglés porque la colección está en inglés. Es independiente de la araña y de los indexadores: solo habla con el servidor de búsqueda por HTTP, según el contrato de [API.md](API.md).

## Correr

```bash
cd interfaz
npm install
npm run dev                 # http://localhost:5173 con datos de prueba
VITE_API=real npm run dev   # usa el servidor real en http://localhost:8000
npm run build               # genera dist/ para que el servidor la sirva
```

## Datos de prueba

Mientras el servidor no exista, `src/api/mock.js` responde con los resultados reales de la entrega 2: el top 10 de cada motor y política para las 12 consultas de prueba, y los 427 juicios del pool. Los juicios nuevos se guardan en el navegador (`localStorage`). En el encabezado aparece la etiqueta **Demo data** para que quede claro.

Para regenerar los datos si cambian los resultados de la entrega 2:

```bash
python interfaz/herramientas/generar_mock.py
```

Limitaciones del modo de prueba: los enlaces apuntan a la portada de cada sitio, porque el pool no guarda la URL exacta; las fechas no se muestran; y las consultas libres solo buscan dentro de los 418 documentos del pool.

## Estructura

| Ruta | Qué hay |
|---|---|
| `src/api/` | `client.js` elige entre el servidor real y el de prueba. |
| `src/lib/metricas.js` | Implementación de referencia de las métricas. |
| `src/pages/` | Las tres páginas. |
| `src/components/` | Fila de resultado, carga, gráficos. |
| `src/assets/` | Logo recortado de `imagenes/logo.png` (a color y en crema para el encabezado). |
| `src/styles/` | `tokens.css` (paleta oliva, burdeos y crema; tipografías) y `app.css`. |

Tipografías (autoalojadas con `@fontsource`): Source Serif 4 para títulos, números y fragmentos, y Archivo para controles y datos. El logo del encabezado y de la portada sale de `imagenes/logo.png`. Los colores de los gráficos pasan el validador de daltonismo y contraste.
