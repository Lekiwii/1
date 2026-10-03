"""Serveur de l'application PC : interface web locale (http://localhost:8765) et API JSON."""
from pathlib import Path

from aiohttp import web

from .ebay import MARKET_CURRENCY
from .engine import Engine
from .grading import GRADERS, Grade

STATIC = Path(__file__).parent / "static"
LANGUAGES = {"EN", "JP", "FR", "DE", "IT", "ES", "KR", "CN"}


def build(engine: Engine) -> web.Application:
    routes = web.RouteTableDef()

    @routes.get("/")
    async def index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC / "index.html")

    @routes.get("/api/status")
    async def status(_: web.Request) -> web.Response:
        return web.json_response(engine.status())

    @routes.get("/api/deals")
    async def deals(_: web.Request) -> web.Response:
        return web.json_response(engine.deals_json())

    @routes.post("/api/scan")
    async def scan(_: web.Request) -> web.Response:
        engine.trigger_scan()
        return web.json_response({"ok": True})

    @routes.post("/api/estimate")
    async def estimate(request: web.Request) -> web.Response:
        body = await request.json()
        try:
            query = str(body["query"]).strip()
            grader = str(body["grader"]).upper()
            grade = float(str(body["grade"]).replace(",", "."))
            price = float(str(body["price"]).replace(",", "."))
            language = str(body.get("language", "EN")).upper()
            first_edition = bool(body.get("first_edition"))
        except (KeyError, ValueError):
            return web.json_response({"error": "Champs invalides."}, status=400)
        if not query or grader not in GRADERS or language not in LANGUAGES or not 1 <= grade <= 10 or price <= 0:
            return web.json_response({"error": "Champs invalides."}, status=400)
        result = await engine.estimate(query, Grade(grader, grade), price, language, first_edition)
        if result is None:
            return web.json_response(
                {"error": "Pas assez d'annonces comparables pour estimer cette carte. "
                          "Essaie le nom anglais et le numéro (ex. Umbreon VMAX 215/203)."}, status=404)
        return web.json_response(result)

    @routes.get("/api/watch")
    async def watch_list(_: web.Request) -> web.Response:
        return web.json_response(await engine.watch_details())

    @routes.post("/api/watch")
    async def watch_add(request: web.Request) -> web.Response:
        query = str((await request.json()).get("query", "")).strip()
        if not query:
            return web.json_response({"error": "Nom de carte vide."}, status=400)
        engine.storage.add_watch(query)
        return web.json_response({"ok": True})

    @routes.delete("/api/watch")
    async def watch_remove(request: web.Request) -> web.Response:
        engine.storage.remove_watch(str((await request.json()).get("query", "")))
        return web.json_response({"ok": True})

    @routes.get("/api/trending")
    async def trending(_: web.Request) -> web.Response:
        try:
            return web.json_response(await engine.trending())
        except Exception as exc:
            return web.json_response({"error": f"Source Cardmarket indisponible : {exc}"}, status=502)

    @routes.get("/api/settings")
    async def get_settings(_: web.Request) -> web.Response:
        return web.json_response({"values": engine.settings(), "marketplaces": sorted(MARKET_CURRENCY)})

    @routes.post("/api/settings")
    async def set_settings(request: web.Request) -> web.Response:
        body = await request.json()
        markets = body.get("ebay_marketplaces")
        if markets is not None:
            chosen = [m for m in str(markets).split(",") if m in MARKET_CURRENCY]
            if not chosen:
                return web.json_response({"error": "Choisis au moins un site eBay."}, status=400)
            body["ebay_marketplaces"] = ",".join(chosen)
        try:
            engine.update_settings(body)
        except ValueError:
            return web.json_response({"error": "Valeur invalide."}, status=400)
        return web.json_response({"ok": True, "values": engine.settings()})

    app = web.Application()
    app.add_routes(routes)
    return app
