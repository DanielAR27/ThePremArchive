"""The Prem Archive: servidor de la aplicación web (búsqueda, evaluación y métricas) sobre la colección de la Premier League.

Es un programa aparte de la araña y de los indexadores: solo lee los índices (por el servicio de Lucene o el índice propio),
data/crawl.db y repo/, y guarda lo que hacen las personas en su propia base (web_app/datos/uso.db). Expone la API que
describe interfaz/API.md y sirve la interfaz en React ya compilada (web_app/ui).
"""
import functools
import json
import re
import uuid

from flask import Flask, Response, abort, g, jsonify, request, send_from_directory

from . import catalogo, config, db, metricas
from .buscador import Buscador, MotorNoDisponible

TAMANOS = (10, 20, 50)
JUICIOS = ("relevant", "not_relevant", "unsure")
_HASH = re.compile(r"^[0-9a-f]{64}$")
MOTORES = {"manual": "Own index", "lucene": "Apache Lucene"}


def crear_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.json.sort_keys = False
    db.iniciar()
    buscador = Buscador()

    def error(mensaje, codigo=400):
        return jsonify({"error": mensaje}), codigo

    # --- sesión anónima: un identificador en una cookie, para contar personas distintas sin pedir datos -----------
    @app.before_request
    def _sesion():
        g.sesion = request.cookies.get("sid") or uuid.uuid4().hex
        g.sesion_nueva = "sid" not in request.cookies

    @app.after_request
    def _cookie(respuesta):
        if g.get("sesion_nueva") and request.path.startswith("/api/"):
            respuesta.set_cookie("sid", g.sesion, max_age=365 * 24 * 3600, httponly=True, samesite="Lax")
        return respuesta

    # --- información de la colección ---------------------------------------------------------------------------
    @functools.lru_cache(maxsize=1)
    def _rastreados():
        return catalogo.total_rastreados()

    @functools.lru_cache(maxsize=1)
    def _estadisticas_indices():
        """Documentos y términos distintos de cada política, de indices/manual_X.idx.stats.json (los dos indexadores
        producen los mismos términos, así que sirve cualquiera de los dos)."""
        documentos, terminos = None, {}
        for p in config.POLITICAS:
            try:
                stats = json.loads((config.RAIZ / "indices" / f"manual_{p}.idx.stats.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            documentos = documentos or stats.get("documentos")
            terminos[p] = stats.get("terminos")
        return documentos, terminos

    def _opciones():
        """{motor: [políticas]} que se ofrecen. En modo normal solo Lucene con la política C (o el índice propio con la C
        si Lucene no está); con --dev, todo lo que haya."""
        lucene, propio = buscador.politicas_lucene(), buscador.politicas_propio()
        if config.MODO_DEV:
            opciones = {"manual": list(propio), "lucene": list(lucene)}
        else:
            c = config.POLITICA_POR_OMISION
            opciones = {"lucene": [c] if c in lucene else [], "manual": [c] if c in propio and c not in lucene else []}
        return {m: ps for m, ps in opciones.items() if ps}

    @app.get("/api/info")
    def info():
        opciones = _opciones()
        if not opciones:
            return error("No index is available. Build an index or start the Lucene service.", 503)
        motores = [m for m in ("manual", "lucene") if m in opciones]
        politicas = [p for p in config.POLITICAS if any(p in ps for ps in opciones.values())]
        motor = "lucene" if "lucene" in opciones else "manual"
        politica = config.POLITICA_POR_OMISION if config.POLITICA_POR_OMISION in politicas else politicas[0]
        return jsonify({
            "collection": {"documents": _estadisticas_indices()[0], "crawled": _rastreados(),
                           "hosts": buscador.sitios(), "termsByPolicy": _estadisticas_indices()[1],
                           "dates": buscador.info_fechas()},
            "engines": [{"id": m, "label": MOTORES[m]} for m in motores],
            "policies": [{"id": p, "label": config.DESCRIPCION_POLITICAS[p][0],
                          "description": config.DESCRIPCION_POLITICAS[p][1]} for p in politicas],
            "default": {"engine": motor, "policy": politica},
        })

    @app.get("/api/queries")
    def consultas():
        return jsonify(metricas.consultas_de_prueba())

    # --- búsqueda -----------------------------------------------------------------------------------------------
    @app.get("/api/search")
    def buscar():
        consulta = " ".join(request.args.get("q", "").split())
        if not consulta:
            return error("Type something to search for.")
        opciones = _opciones()
        motor = request.args.get("engine") or ("lucene" if "lucene" in opciones else "manual")
        politica = request.args.get("policy") or config.POLITICA_POR_OMISION
        sitio = request.args.get("site", "")
        desde = request.args.get("from", "")
        hasta = request.args.get("to", "")
        orden = request.args.get("sort", "relevance") or "relevance"
        pagina = max(1, request.args.get("page", 1, type=int))
        tamano = request.args.get("size", 10, type=int)
        tamano = tamano if tamano in TAMANOS else 10
        if motor not in MOTORES:
            return error(f"Unknown engine: {motor}")
        if politica not in config.POLITICAS:
            return error(f"Unknown policy: {politica}")
        if politica not in opciones.get(motor, []):
            return error("That engine or policy is only available in dev mode (python -m web_app --dev).", 403)
        pagina = min(pagina, max(1, config.MAX_K // tamano))

        try:
            datos = buscador.buscar(consulta, motor, politica, sitio, pagina * tamano, desde, hasta, orden)
        except ValueError as e:
            return error(f"Invalid date or order: {e}")
        except MotorNoDisponible as e:
            return error(str(e), 503)

        inicio = (pagina - 1) * tamano
        visibles = datos["results"][inicio:inicio + tamano]
        info_docs = catalogo.detalles([r["doc"] for r in visibles])
        resultados = []
        for posicion, r in enumerate(visibles, inicio + 1):
            d = info_docs.get(r["doc"])
            if d is None:
                continue
            resultados.append({
                "rank": posicion, "doc": r["doc"], "score": round(r["score"], 4), "url": d["url"], "title": d["titulo"],
                "host": d["host"], "publishedAt": d["fecha"],
                "snippet": catalogo.fragmento(r["doc"], d["host"], consulta),
            })
        db.registrar_busqueda(g.sesion, consulta, motor, politica, sitio, pagina, datos["total"], datos["tookMs"],
                              desde, hasta, orden)
        prueba = next((q["id"] for q in metricas.consultas_de_prueba()
                       if db.normalizar(q["text"]) == db.normalizar(consulta)), None)
        return jsonify({
            "query": consulta, "terms": datos["terms"], "engine": motor, "policy": politica, "site": sitio or None,
            "from": desde or None, "to": hasta or None, "sort": orden, "undatedHidden": datos["undated"],
            "total": datos["total"], "tookMs": round(datos["tookMs"], 1), "page": pagina, "size": tamano,
            "results": resultados, "testQueryId": prueba,
        })

    # --- juicios de relevancia ----------------------------------------------------------------------------------
    @app.get("/api/judgments")
    def juicios():
        return jsonify(db.listar_juicios(request.args.get("queryId") or None, request.args.get("evaluator") or None))

    @app.post("/api/judgments")
    def guardar_juicio():
        j = request.get_json(silent=True) or {}
        evaluador = str(j.get("evaluator", "")).strip()
        if not evaluador:
            return error("Write your name before judging.")
        if j.get("judgment") not in JUICIOS:
            return error("judgment must be relevant, not_relevant or unsure.")
        if not _HASH.match(str(j.get("doc", ""))):
            return error("doc must be the document hash.")
        if not str(j.get("query", "")).strip():
            return error("query is required.")
        try:
            guardado = db.guardar_juicio({
                "queryId": j.get("queryId") or None, "query": str(j["query"]).strip(), "doc": j["doc"],
                "engine": str(j.get("engine", "")), "policy": str(j.get("policy", "")),
                "rank": int(j.get("rank", 0)), "judgment": j["judgment"], "evaluator": evaluador})
        except (TypeError, ValueError):
            return error("rank must be a number.")
        return jsonify(guardado), 201

    @app.delete("/api/judgments")
    def borrar_juicios():
        evaluador = (request.args.get("evaluator") or "").strip()
        if not evaluador:
            return error("evaluator is required, so that nothing is deleted by accident.")
        return jsonify({"deleted": db.borrar_juicios(evaluador)})

    # --- métricas y uso -----------------------------------------------------------------------------------------
    @app.get("/api/metrics")
    def metricas_api():
        motor = request.args.get("engine") or "lucene"
        politica = request.args.get("policy") or config.POLITICA_POR_OMISION
        if f"{motor}:{politica}" not in metricas.rankings_p2():
            return error("No ranking is stored for that engine and policy.")
        incluir = request.args.get("includeBaseline", "true").lower() != "false"
        return jsonify(metricas.calcular_metricas(motor, politica, incluir))

    @app.get("/api/usage")
    def uso():
        return jsonify(metricas.estadisticas_de_uso())

    @app.get("/api/export/<que>.csv")
    def exportar(que):
        """Datos en bruto para analizarlos aparte. Solo desde la propia máquina: si la petición llegó por un túnel
        (trae cabeceras de reenvío) no se entrega, porque incluye los identificadores de sesión."""
        if any(h in request.headers for h in ("X-Forwarded-For", "Cf-Connecting-Ip", "Cf-Ray", "Forwarded")):
            abort(403)
        try:
            cuerpo = metricas.exportar_csv(que)
        except KeyError:
            abort(404)
        return Response(cuerpo, mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={que}.csv"})

    @app.errorhandler(404)
    @app.errorhandler(405)
    @app.errorhandler(403)
    def _error_api(e):
        if request.path.startswith("/api/"):
            return error(e.description, e.code)
        return e

    # --- la interfaz (React ya compilada) -----------------------------------------------------------------------
    @app.get("/", defaults={"ruta": ""})
    @app.get("/<path:ruta>")
    def interfaz(ruta):
        if ruta.startswith("api/"):
            abort(404)
        if not (config.UI_DIR / "index.html").exists():
            return Response("The interface has not been built yet. Run:  cd interfaz && npm install && npm run publicar",
                            status=503, mimetype="text/plain")
        if ruta and (config.UI_DIR / ruta).is_file():
            return send_from_directory(config.UI_DIR, ruta)
        return send_from_directory(config.UI_DIR, "index.html")   # el enrutador de React resuelve el resto

    return app
