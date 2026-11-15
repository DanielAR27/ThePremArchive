"""Convierte un documento Markdown de documentacion/ en PDF, sin encabezados del navegador.

Uso (desde la raíz del repo):
    python documentacion/exportar_pdf.py documentacion/02_indexador/documentacion_indexador.md

Deja el PDF junto al .md. Necesita `pip install markdown` y Microsoft Edge o Google Chrome instalados:
el PDF lo imprime el navegador en modo sin pantalla, con --no-pdf-header-footer, que es lo que quita
el encabezado con el nombre del archivo y la fecha que aparecen al exportar desde Obsidian o el navegador.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

NAVEGADORES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

CSS = """
@page { size: A4; margin: 22mm 20mm 22mm 20mm;
        @bottom-center { content: counter(page); font: 9pt 'Segoe UI', Arial, sans-serif; color: #666; } }
@page :first { @bottom-center { content: ''; } }
html { font-size: 10.5pt; }
body { font-family: 'Segoe UI', Calibri, Arial, sans-serif; line-height: 1.5; color: #1a1a1a; }
h1, h2, h3 { font-family: 'Segoe UI', Calibri, Arial, sans-serif; color: #12304f; line-height: 1.25; }
h2 { font-size: 1.45em; margin-top: 1.6em; border-bottom: 1px solid #c9d3de; padding-bottom: .2em; page-break-after: avoid; }
h3 { font-size: 1.15em; margin-top: 1.3em; page-break-after: avoid; }
p, li { text-align: left; orphans: 3; widows: 3; }
img { max-width: 100%; height: auto; display: block; margin: .8em auto; }
table { border-collapse: collapse; margin: 1em 0; width: 100%; font-size: .85em; page-break-inside: auto; }
th, td { border: 1px solid #c9d3de; padding: 4px 7px; vertical-align: top; }
th { background: #eaf0f6; }
tr { page-break-inside: avoid; }
code { font-family: Consolas, 'Courier New', monospace; font-size: .9em; background: #f1f3f5; padding: 0 3px; border-radius: 3px; }
pre { background: #f1f3f5; padding: 8px 10px; border-radius: 4px; font-size: .8em; line-height: 1.35; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
em { color: #333; }
.portada, .portada p { text-align: center; }
.portada { page-break-after: always; padding-top: 12mm; }
.portada h1 { font-size: 2.4em; margin-bottom: .1em; border: none; }
.portada h3 { font-weight: normal; margin-top: 0; }
.portada img { width: 160px; }
hr { display: none; }  /* los '---' entre secciones: cada título ya trae su propia línea */
"""


# Una dirección web que no está ya dentro de un enlace (<a href="...">) ni de un atributo; sin el punto o coma final.
URL_SUELTA = re.compile(r'(?<![">=/\w])https?://[^\s<>"\')]*[^\s<>"\')\.,;:]')


def buscar_navegador() -> str:
    for ruta in NAVEGADORES:
        if Path(ruta).exists():
            return ruta
    raise SystemExit("No encontré Edge ni Chrome; instala uno o agrega su ruta a NAVEGADORES.")


def a_html(texto: str) -> str:
    # El bloque de la portada va dentro de un <div align="center">; se marca para que Markdown lo procese.
    texto = texto.replace('<div align="center">', '<div class="portada" markdown="1">')
    cuerpo = markdown.markdown(texto, extensions=["tables", "fenced_code", "md_in_html", "sane_lists"])
    cuerpo = URL_SUELTA.sub(lambda m: f'<a href="{m[0]}">{m[0]}</a>', cuerpo)  # Markdown no enlaza las URL sueltas
    return f'<!doctype html><html lang="es"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{cuerpo}</body></html>'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("documento", help="archivo .md")
    args = ap.parse_args()
    md = Path(args.documento).resolve()
    pdf = md.with_suffix(".pdf")
    html = md.with_name(f"_{md.stem}_temporal.html")  # junto al .md, para que las rutas de las imágenes sigan valiendo
    html.write_text(a_html(md.read_text(encoding="utf-8")), encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory() as perfil:
            subprocess.run([buscar_navegador(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={perfil}", f"--print-to-pdf={pdf}", html.as_uri()],
                           check=True, capture_output=True, timeout=180)
    finally:
        html.unlink(missing_ok=True)
    print(f"PDF generado: {pdf}")


if __name__ == "__main__":
    sys.exit(main())
