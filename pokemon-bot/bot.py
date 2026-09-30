"""Bot Telegram : scanne eBay et envoie les cartes Pokémon gradées vendues sous leur cote."""
import html
import logging

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from pokedeals.config import Config
from pokedeals.deals import Deal, find_deals
from pokedeals.ebay import EbayClient
from pokedeals.pricing import PriceCharting
from pokedeals.storage import Storage

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("pokedeals")

HELP = (
    "<b>Bot deals Pokémon</b> — cartes gradées (PSA, BGS, CGC, SGC…) vendues sous leur cote.\n\n"
    "/scan — lancer un scan maintenant\n"
    "/liste — cartes surveillées\n"
    "/ajouter &lt;carte&gt; — ex. <code>/ajouter Charizard ex 199/165</code>\n"
    "/retirer &lt;carte&gt; — arrêter de surveiller une carte\n"
    "/regles — seuils de rentabilité et frais pris en compte"
)


def format_deal(deal: Deal) -> str:
    l = deal.listing
    return (
        f"🔥 <b>{html.escape(l.title)}</b>\n"
        f"🏷 {deal.grade} · {l.source} · vendeur {html.escape(l.seller)} "
        f"({l.seller_feedback_pct:.1f} %, {l.seller_feedback_score} avis)\n"
        f"💶 Achat : <b>{deal.cost_eur:.2f} €</b> port compris\n"
        f"📈 Cote : {deal.market_eur:.2f} € ({html.escape(deal.market_source)})\n"
        f"💰 Revente nette : {deal.net_resale_eur:.2f} € → <b>+{deal.profit_eur:.2f} € ({deal.roi_pct:+.0f} %)</b>\n"
        f"🔎 Recherche : {html.escape(deal.query)}\n"
        f'<a href="{html.escape(l.url)}">Voir l\'annonce</a>'
    )


async def run_scan(app: Application, chat_id: int, announce_empty: bool) -> None:
    cfg: Config = app.bot_data["cfg"]
    storage: Storage = app.bot_data["storage"]
    deals = await find_deals(storage.watchlist(), cfg, app.bot_data["ebay"], app.bot_data["pricecharting"])
    fresh = [d for d in deals if storage.is_new_alert(d.listing.item_id, d.cost_eur)]
    log.info("Scan : %d bonnes affaires, %d nouvelles", len(deals), len(fresh))
    for deal in fresh:
        await app.bot.send_message(chat_id, format_deal(deal), parse_mode=ParseMode.HTML)
        storage.mark_alerted(deal.listing.item_id, deal.cost_eur)
    if announce_empty and not fresh:
        await app.bot.send_message(chat_id, "Aucune nouvelle bonne affaire pour l'instant.")


def authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    owner = context.bot_data["cfg"].telegram_chat_id
    return owner is not None and update.effective_chat.id == owner


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        await update.message.reply_text(
            f"Ton identifiant Telegram est {update.effective_chat.id}.\n"
            "Mets-le dans TELEGRAM_CHAT_ID (fichier .env) puis relance le bot."
        )
        return
    await update.message.reply_text(HELP, parse_mode=ParseMode.HTML)


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    await update.message.reply_text("Scan en cours…")
    await run_scan(context.application, update.effective_chat.id, announce_empty=True)


async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    queries = context.bot_data["storage"].watchlist()
    text = "\n".join(f"• {html.escape(q)}" for q in queries) or "Aucune carte surveillée."
    await update.message.reply_text(f"<b>Cartes surveillées</b>\n{text}", parse_mode=ParseMode.HTML)


async def ajouter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Usage : /ajouter Charizard ex 199/165")
        return
    context.bot_data["storage"].add_watch(query)
    await update.message.reply_text(f"Ajouté : {query}")


async def retirer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    query = " ".join(context.args).strip()
    removed = context.bot_data["storage"].remove_watch(query)
    await update.message.reply_text(f"Retiré : {query}" if removed else "Carte introuvable, vois /liste.")


async def regles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    cfg: Config = context.bot_data["cfg"]
    await update.message.reply_text(
        f"Marketplaces : {', '.join(cfg.ebay_marketplaces)}\n"
        f"Prix d'achat : {cfg.min_price_eur:.0f}–{cfg.max_price_eur:.0f} €\n"
        f"Bénéfice minimum : {cfg.min_profit_eur:.0f} € et {cfg.min_roi_pct:.0f} % de ROI\n"
        f"Frais de revente : {cfg.sell_fee_pct:.1f} % + {cfg.sell_shipping_eur:.2f} € d'envoi\n"
        f"Vendeurs : ≥ {cfg.min_seller_feedback_pct:.1f} % et ≥ {cfg.min_seller_feedback_score} avis\n"
        f"Cote : {'PriceCharting' if cfg.pricecharting_token else 'médiane des annonces'}"
        f" · scan toutes les {cfg.scan_interval_min:.0f} min"
    )


async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await run_scan(context.application, context.bot_data["cfg"].telegram_chat_id, announce_empty=False)
    except Exception:
        log.exception("Scan automatique échoué")


async def post_init(app: Application) -> None:
    cfg: Config = app.bot_data["cfg"]
    http = httpx.AsyncClient(timeout=30)
    app.bot_data["http"] = http
    app.bot_data["ebay"] = EbayClient(cfg.ebay_client_id, cfg.ebay_client_secret, http)
    app.bot_data["pricecharting"] = (
        PriceCharting(cfg.pricecharting_token, cfg.usd_to_eur, http) if cfg.pricecharting_token else None
    )
    if cfg.telegram_chat_id is not None:
        app.job_queue.run_repeating(scheduled_scan, interval=cfg.scan_interval_min * 60, first=10)


async def post_shutdown(app: Application) -> None:
    await app.bot_data["http"].aclose()


def main() -> None:
    cfg = Config.from_env()
    missing = [n for n, v in [("TELEGRAM_TOKEN", cfg.telegram_token), ("EBAY_CLIENT_ID", cfg.ebay_client_id),
                              ("EBAY_CLIENT_SECRET", cfg.ebay_client_secret)] if not v]
    if missing:
        raise SystemExit(f"Variables manquantes dans .env : {', '.join(missing)}")

    app = Application.builder().token(cfg.telegram_token).post_init(post_init).post_shutdown(post_shutdown).build()
    app.bot_data["cfg"] = cfg
    app.bot_data["storage"] = Storage(cfg.db_path)
    for name, handler in [("start", start), ("help", start), ("scan", scan), ("liste", liste),
                          ("ajouter", ajouter), ("retirer", retirer), ("regles", regles)]:
        app.add_handler(CommandHandler(name, handler))
    app.run_polling()


if __name__ == "__main__":
    main()
