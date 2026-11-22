"""The Prem Archive: aplicación web de búsqueda, evaluación y métricas sobre la colección de la Premier League.

Es un programa aparte de la araña y de los indexadores: solo lee el índice (a través del servicio de Lucene o, si
no está, del índice propio), data/crawl.db y repo/, y guarda lo que hacen las personas en su propia base (uso.db).
"""
import uuid
from urllib.parse import quote

from flask import Flask, Response, abort, g, redirect, render_template, request

from . import catalogo, config, db, metricas
from .buscador import Buscador

def _sugerencias():
    """Las consultas de prueba del Proyecto 2: así varias personas califican las mismas y se pueden comparar."""
    try:
        lineas = (config.RAIZ / "indexacion" / "config" / "datos" / "consultas.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [l.split("|")[1].strip() for l in lineas if l.strip() and not l.startswith("#") and "|" in l]


EJEMPLOS = ["arsenal transfer news", "man city vs man utd", "premier league title race", "haaland goals",
            "liverpool injury news", "relegation battle"]


def crear_app() -> Flask:
    app = Flask(__name__)
    db.iniciar()
    buscador = Buscador()

    # --- sesión anónima: un identificador en una cookie, para contar personas distintas sin pedir datos --------
    @app.before_request
    def _sesion():
        g.sesion = request.cookies.get("sid") or uuid.uuid4().hex
        g.sesion_nueva = "sid" not in request.cookies

    @app.after_request
    def _cookie(respuesta):
        if g.get("sesion_nueva"):
            respuesta.set_cookie("sid", g.sesion, max_age=365 * 24 * 3600, httponly=True, samesite="Lax")
        return respuesta

    @app.context_processor
    def _comunes():
        return {"ejemplos": EJEMPLOS, "politica": config.POLITICA.stem.replace("politica_", "")}

    # --- páginas -----------------------------------------------------------------------------------------------
    @app.get("/")
    def inicio():
        return render_template("home.html")

    @app.get("/search")
    def buscar():
        consulta = " ".join(request.args.get("q", "").split())
        if not consulta:
            return redirect("/")
        try:
            pagina = max(1, int(request.args.get("page", 1)))
        except ValueError:
            pagina = 1
        try:
            datos = buscador.buscar(consulta)
        except Exception as error:   # los dos buscadores fallaron
            return render_template("error.html", mensaje=str(error)), 503

        # La consulta se registra una sola vez (en la página 1); las demás páginas reutilizan su número.
        consulta_id = request.args.get("qid", type=int)
        if pagina == 1 or consulta_id is None:
            consulta_id = db.registrar_consulta(g.sesion, consulta, "search", datos["motor"], datos["terminos"],
                                                datos["tiempo_ms"], len(datos["resultados"]))

        por_pagina = config.RESULTADOS_POR_PAGINA
        total = len(datos["resultados"])
        paginas = max(1, -(-total // por_pagina))
        pagina = min(pagina, paginas)
        visibles = datos["resultados"][(pagina - 1) * por_pagina: pagina * por_pagina]
        info = catalogo.detalles([r["hash"] for r in visibles])
        resultados = []
        for r in visibles:
            d = info.get(r["hash"])
            if d is None:
                continue
            resultados.append({
                "puesto": r["puesto"], "titulo": d["titulo"], "url": d["url"], "fecha": d["fecha"],
                "sitio": catalogo.sitio_legible(d["host"]),
                "fragmento": catalogo.fragmento(r["hash"], d["host"], consulta),
                "enlace": f"/go/{consulta_id}/{r['hash']}?p={r['puesto']}",
            })
        return render_template("results.html", consulta=consulta, resultados=resultados, total=total,
                               tiempo=datos["tiempo_ms"], motor=datos["motor"], terminos=datos["terminos"],
                               pagina=pagina, paginas=paginas, consulta_id=consulta_id)

    @app.get("/go/<int:consulta_id>/<hash_doc>")
    def abrir(consulta_id, hash_doc):
        """Registra el clic y manda a la página original (no al archivo de texto)."""
        url = catalogo.url_original(hash_doc)
        if not url:
            abort(404)
        db.registrar_clic(consulta_id, hash_doc, request.args.get("p", 0, type=int))
        return redirect(url)

    # --- modo de evaluación: la persona marca qué resultados son relevantes (aparte del modo de solo búsqueda) -----
    @app.get("/evaluate")
    def evaluar():
        consulta = " ".join(request.args.get("q", "").split())
        hechas = db.contar_evaluadas(g.sesion)
        if not consulta:
            return render_template("evaluate_home.html", sugerencias=_sugerencias(), hechas=hechas)
        try:
            datos = buscador.buscar(consulta, config.K_EVALUACION)
        except Exception as error:
            return render_template("error.html", mensaje=str(error)), 503
        consulta_id = db.registrar_consulta(g.sesion, consulta, "evaluate", datos["motor"], datos["terminos"],
                                            datos["tiempo_ms"], len(datos["resultados"]))
        info = catalogo.detalles([r["hash"] for r in datos["resultados"]])
        resultados = []
        for r in datos["resultados"]:
            d = info.get(r["hash"])
            if d is None:
                continue
            resultados.append({
                "hash": r["hash"], "puesto": r["puesto"], "titulo": d["titulo"], "url": d["url"], "fecha": d["fecha"],
                "sitio": catalogo.sitio_legible(d["host"]),
                "fragmento": catalogo.fragmento(r["hash"], d["host"], consulta),
                "enlace": f"/go/{consulta_id}/{r['hash']}?p={r['puesto']}",
            })
        db.registrar_mostrados(consulta_id, [(r["puesto"], r["hash"]) for r in resultados])
        return render_template("evaluate.html", consulta=consulta, resultados=resultados, consulta_id=consulta_id,
                               hechas=hechas)

    @app.post("/evaluate/submit")
    def enviar_evaluacion():
        consulta_id = request.form.get("qid", type=int)
        consulta = db.consulta_de(g.sesion, consulta_id) if consulta_id else None
        if consulta is None:
            abort(400)
        marcas = {}
        for campo, valor in request.form.items():
            if campo.startswith("r_") and valor in ("1", "0", "-1"):
                marcas[campo[2:]] = int(valor)
        if not marcas:
            return redirect("/evaluate?q=" + quote(consulta["texto"]))
        db.guardar_juicios(consulta_id, g.sesion, marcas)
        db.guardar_satisfaccion(consulta_id, request.form.get("sat", type=int, default=-1))
        return redirect("/evaluate/thanks")

    @app.get("/evaluate/thanks")
    def gracias():
        return render_template("thanks.html", hechas=db.contar_evaluadas(g.sesion))

    # --- métricas -----------------------------------------------------------------------------------------------
    @app.get("/metrics")
    def metricas_pagina():
        return render_template("metrics.html", datos=metricas.calcular())

    @app.get("/metrics/export/<que>.csv")
    def exportar(que):
        """Datos en bruto para analizarlos aparte. Solo desde la propia máquina: si la petición llegó por un túnel
        (trae cabeceras de reenvío), no se entrega, porque incluye los identificadores de sesión."""
        if any(h in request.headers for h in ("X-Forwarded-For", "Cf-Connecting-Ip", "Cf-Ray", "Forwarded")):
            abort(403)
        try:
            cuerpo = metricas.exportar_csv(que)
        except KeyError:
            abort(404)
        return Response(cuerpo, mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={que}.csv"})

    return app
