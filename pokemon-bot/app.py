"""Application PC Pokémon Deals : tableau de bord local + scans automatiques + alertes Telegram."""
import asyncio
import logging
import os
import sys
import webbrowser

from aiohttp import web

from pokedeals import assistant, telegram_bot
from pokedeals import web as webapp
from pokedeals.config import Config
from pokedeals.engine import Engine

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
for noisy in ("httpx", "apscheduler", "aiohttp.access", "telegram"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


def load_config() -> Config:
    cfg = Config.from_env()
    required = {"TELEGRAM_TOKEN": cfg.telegram_token, "EBAY_CLIENT_ID": cfg.ebay_client_id,
                "EBAY_CLIENT_SECRET": cfg.ebay_client_secret,
                "TELEGRAM_CHAT_ID": str(cfg.telegram_chat_id or "")}
    if all(required.values()):
        return cfg
    if not sys.stdin.isatty():
        missing = [name for name, value in required.items() if not value]
        raise SystemExit(f"Variables manquantes dans .env : {', '.join(missing)}")
    assistant.run(required)
    for key in required:
        os.environ.pop(key, None)
    return Config.from_env()


async def main() -> None:
    cfg = load_config()
    engine = Engine(cfg)

    runner = web.AppRunner(webapp.build(engine))
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", cfg.web_port).start()
    url = f"http://localhost:{cfg.web_port}"

    bot = telegram_bot.build(engine)
    if bot:
        try:
            await bot.initialize()
            await bot.start()
            await bot.updater.start_polling()
        except Exception as exc:
            print(f"Telegram injoignable ({exc}) : l'application tourne sans alertes Telegram.", flush=True)
            engine.notifiers.clear()
            bot = None

    print("=" * 60)
    print(f"  Application ouverte : {url}")
    print("  Laisse cette fenêtre ouverte pour que les scans continuent.")
    print("=" * 60, flush=True)
    webbrowser.open(url)

    try:
        await engine.run_forever()
    finally:
        if bot:
            await bot.updater.stop()
            await bot.stop()
            await bot.shutdown()
        await runner.cleanup()
        await engine.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
