"""Bot Telegram : scanne eBay et envoie les cartes Pokémon gradées vendues sous leur cote."""
import html
from datetime import datetime, timedelta
import logging
import os
import sys

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from pokedeals import assistant
from pokedeals.config import Config
from pokedeals import links
from pokedeals.deals import Deal, estimate, find_deals, parse_offer
from pokedeals.ebay import EbayClient
from pokedeals.pricing import PriceCharting
from pokedeals.storage import Storage

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("pokedeals")

HELP = (
    "<b>Bot deals Pokémon</b> — cartes gradées (PSA, BGS, CGC, SGC…) vendues sous leur cote.\n\n"
    "/scan — lancer un scan maintenant (et revoir les meilleures affaires)\n"
    "/statut — vérifier que le bot tourne et voir le prochain scan\n"
    "/liste — cartes surveillées\n"
    "/ajouter &lt;carte&gt; — ex. <code>/ajouter Charizard ex 199/165</code>\n"
    "/retirer &lt;carte&gt; — arrêter de surveiller une carte\n"
    "/regles — seuils de rentabilité et frais pris en compte\n\n"
    "<b>Vinted, Leboncoin, salons…</b>\n"
    "/estimer &lt;carte&gt; &lt;note&gt; &lt;prix&gt; — ex. <code>/estimer Umbreon VMAX 215/203 PSA 10 650</code> : "
    "le bot te dit si l'offre est rentable\n"
    "/liens — recherches Vinted et Leboncoin prêtes, pour y activer les alertes"
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


async def run_scan(app: Application, chat_id: int, manual: bool) -> None:
    cfg: Config = app.bot_data["cfg"]
    storage: Storage = app.bot_data["storage"]
    deals = await find_deals(storage.watchlist(), cfg, app.bot_data["ebay"], app.bot_data["pricecharting"])
    fresh = [d for d in deals if storage.is_new_alert(d.listing.item_id, d.cost_eur)]
    now = datetime.now()
    app.bot_data["last_scan"] = (now, len(deals), len(fresh))
    next_scan = (now + timedelta(minutes=cfg.scan_interval_min)).strftime("%H:%M")
    print(
        f"[{now:%H:%M}] Scan terminé : {len(deals)} bonnes affaires en ligne, {len(fresh)} nouvelles envoyées."
        f" Prochain scan automatique vers {next_scan}.",
        flush=True,
    )
    for deal in fresh:
        await app.bot.send_message(chat_id, format_deal(deal), parse_mode=ParseMode.HTML)
        storage.mark_alerted(deal.listing.item_id, deal.cost_eur)
    if manual and not fresh:
        if not deals:
            await app.bot.send_message(chat_id, "Aucune bonne affaire en ligne pour l'instant.")
            return
        await app.bot.send_message(
            chat_id, f"Rien de nouveau depuis le dernier scan. Les meilleures affaires encore en ligne :"
        )
        for deal in deals[:5]:
            await app.bot.send_message(chat_id, format_deal(deal), parse_mode=ParseMode.HTML)


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
    await run_scan(context.application, update.effective_chat.id, manual=True)


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


async def estimer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    offer = parse_offer(" ".join(context.args))
    if offer is None:
        await update.message.reply_text(
            "Usage : /estimer <carte> <note> <prix>\nEx. : /estimer Umbreon VMAX 215/203 PSA 10 650"
        )
        return
    query, grade, price = offer
    await update.message.reply_text(f"Je cherche la cote de {query} {grade}…")
    bd = context.bot_data
    result = await estimate(query, grade, price, bd["cfg"], bd["ebay"], bd["pricecharting"])
    if result is None:
        await update.message.reply_text(
            f"Pas assez d'annonces {grade} sur eBay pour estimer {query}. "
            "Essaie avec le nom anglais et le numéro de la carte."
        )
        return
    good = result.profit_eur >= bd["cfg"].min_profit_eur and result.roi_pct >= bd["cfg"].min_roi_pct
    verdict = "✅ Bonne affaire" if good else ("⚠️ Marge trop faible" if result.profit_eur > 0 else "❌ Pas rentable")
    await update.message.reply_text(
        f"<b>{verdict}</b>\n"
        f"🏷 {html.escape(query)} · {grade}\n"
        f"💶 Prix demandé : {price:.2f} €\n"
        f"📈 Cote : {result.market_eur:.2f} € ({html.escape(result.market_source)})\n"
        f"💰 Revente nette : {result.net_resale_eur:.2f} € → <b>{result.profit_eur:+.2f} € ({result.roi_pct:+.0f} %)</b>\n"
        f"Vérifie le numéro de certification avant d'acheter.",
        parse_mode=ParseMode.HTML,
    )


async def liens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    lines = [
        f"• {html.escape(q)} : <a href=\"{html.escape(links.vinted(q))}\">Vinted</a> · "
        f"<a href=\"{html.escape(links.leboncoin(q))}\">Leboncoin</a>"
        for q in context.bot_data["storage"].watchlist()
    ]
    await update.message.reply_text(
        "<b>Recherches Vinted et Leboncoin</b>\n"
        "Ouvre un lien dans l'appli, puis « Sauvegarder la recherche » avec les notifications activées : "
        "tu es prévenu dès qu'une annonce sort. Puis envoie-la-moi avec /estimer pour savoir si elle est rentable.\n\n"
        + "\n".join(lines),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def statut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    cfg: Config = context.bot_data["cfg"]
    last = context.bot_data.get("last_scan")
    jobs = context.job_queue.get_jobs_by_name("scheduled_scan")
    next_run = jobs[0].next_t.astimezone().strftime("%H:%M") if jobs and jobs[0].next_t else "?"
    if last:
        at, found, sent = last
        summary = f"Dernier scan : {at:%H:%M}, {found} bonnes affaires en ligne, {sent} nouvelles envoyées."
    else:
        summary = "Pas encore de scan depuis le démarrage."
    await update.message.reply_text(
        f"✅ Le bot tourne.\n{summary}\nProchain scan automatique : {next_run} "
        f"(toutes les {cfg.scan_interval_min:.0f} min).\n"
        f"Cartes surveillées : {len(context.bot_data['storage'].watchlist())}.\n"
        "Il ne t'écrit que pour les nouvelles affaires. /scan pour revoir les meilleures."
    )


async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await run_scan(context.application, context.bot_data["cfg"].telegram_chat_id, manual=False)
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
        app.job_queue.run_repeating(
            scheduled_scan, interval=cfg.scan_interval_min * 60, first=10, name="scheduled_scan"
        )


async def post_shutdown(app: Application) -> None:
    await app.bot_data["http"].aclose()


def main() -> None:
    cfg = Config.from_env()
    required = {"TELEGRAM_TOKEN": cfg.telegram_token, "EBAY_CLIENT_ID": cfg.ebay_client_id,
                "EBAY_CLIENT_SECRET": cfg.ebay_client_secret,
                "TELEGRAM_CHAT_ID": str(cfg.telegram_chat_id or "")}
    if not all(required.values()):
        if not sys.stdin.isatty():
            missing = [name for name, value in required.items() if not value]
            raise SystemExit(f"Variables manquantes dans .env : {', '.join(missing)}")
        assistant.run(required)
        for key in required:
            os.environ.pop(key, None)
        cfg = Config.from_env()

    app = Application.builder().token(cfg.telegram_token).post_init(post_init).post_shutdown(post_shutdown).build()
    app.bot_data["cfg"] = cfg
    app.bot_data["storage"] = Storage(cfg.db_path)
    for name, handler in [("start", start), ("help", start), ("scan", scan), ("liste", liste),
                          ("ajouter", ajouter), ("retirer", retirer), ("regles", regles),
                          ("estimer", estimer), ("liens", liens), ("statut", statut)]:
        app.add_handler(CommandHandler(name, handler))
    app.run_polling()


if __name__ == "__main__":
    main()
