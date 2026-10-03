"""Bot Telegram : alertes et commandes, branché sur le même moteur que l'application PC."""
import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from . import links
from .deals import Deal, parse_offer
from .engine import Engine

log = logging.getLogger(__name__)

HELP = (
    "<b>Bot deals Pokémon</b> — cartes gradées vendues sous leur cote, avec indice de confiance.\n"
    "L'application PC (http://localhost:{port}) donne tous les détails.\n\n"
    "/scan — scan immédiat (et revoir les meilleures affaires)\n"
    "/statut — vérifier que le bot tourne\n"
    "/liste — cartes surveillées\n"
    "/ajouter &lt;carte&gt; — ex. <code>/ajouter Charizard ex 199/165</code>\n"
    "/retirer &lt;carte&gt;\n"
    "/estimer &lt;carte&gt; &lt;note&gt; &lt;prix&gt; — ex. <code>/estimer Umbreon VMAX 215/203 PSA 10 650</code>\n"
    "/liens — recherches Vinted et Leboncoin prêtes\n"
    "/regles — seuils et frais"
)


def format_deal(deal: Deal) -> str:
    l, c, v = deal.listing, deal.confidence, deal.valuation
    badge = {"Fiable": "🟢", "À vérifier": "🟡", "Risqué": "🔴"}[c.label]
    trend = ""
    if v.card and v.card.momentum_pct is not None:
        trend = f"📊 Tendance Cardmarket : {v.card.trend_label} ({v.card.momentum_pct:+.0f} %)\n"
    reasons = "\n".join(f"  {'✅' if k == '+' else '❌' if k == '-' else '⚠️'} {html.escape(t)}" for k, t in c.reasons[:5])
    return (
        f"🔥 <b>{html.escape(l.title)}</b>\n"
        f"🏷 {deal.variant} · {l.source} · {html.escape(l.seller)} ({l.seller_feedback_pct:.1f} %, {l.seller_feedback_score} avis)\n"
        f"💶 Achat : <b>{deal.cost_eur:.2f} €</b> port compris\n"
        f"📈 Cote : {deal.market_eur:.2f} € ({html.escape(deal.market_source)})\n"
        f"💰 Revente nette : {deal.net_resale_eur:.2f} € → <b>+{deal.profit_eur:.2f} € ({deal.roi_pct:+.0f} %)</b>\n"
        f"{trend}"
        f"{badge} Confiance : <b>{c.score}/100 ({c.label})</b>\n{reasons}\n"
        f'<a href="{html.escape(l.url)}">Voir l\'annonce</a>'
    )


def build(engine: Engine) -> Application | None:
    cfg = engine.cfg
    if not cfg.telegram_token or cfg.telegram_chat_id is None:
        return None
    app = Application.builder().token(cfg.telegram_token).build()
    owner = cfg.telegram_chat_id

    def mine(update: Update) -> bool:
        return update.effective_chat is not None and update.effective_chat.id == owner

    async def send_deals(deals: list[Deal]) -> None:
        for d in deals:
            await app.bot.send_message(owner, format_deal(d), parse_mode=ParseMode.HTML)

    engine.notifiers.append(send_deals)

    async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not mine(update):
            await update.message.reply_text(f"Ton identifiant Telegram est {update.effective_chat.id}.")
            return
        await update.message.reply_text(HELP.format(port=cfg.web_port), parse_mode=ParseMode.HTML)

    async def scan(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not mine(update):
            return
        await update.message.reply_text("Scan en cours…")
        fresh = await engine.scan()
        if fresh:
            return
        best = [d for d in engine.deals if d.confidence.score >= cfg.min_confidence][:5]
        if not best:
            await update.message.reply_text("Aucune bonne affaire fiable en ligne pour l'instant.")
            return
        await update.message.reply_text("Rien de nouveau. Les meilleures affaires encore en ligne :")
        await send_deals(best)

    async def statut(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not mine(update):
            return
        s = engine.status()
        last = f"Dernier scan : {s['last_scan']}, {len(engine.deals)} affaires en ligne." if s["last_scan"] else "Premier scan en cours."
        await update.message.reply_text(
            f"✅ Le bot tourne.\n{last}\nProchain scan : {s['next_scan'] or '?'} (toutes les {cfg.scan_interval_min:.0f} min).\n"
            f"Cartes surveillées : {s['watch_count']}.\nApplication : http://localhost:{cfg.web_port}"
            + (f"\n⚠️ Dernière erreur : {s['last_error']}" if s["last_error"] else "")
        )

    async def liste(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not mine(update):
            return
        text = "\n".join(f"• {html.escape(q)}" for q in engine.storage.watchlist()) or "Aucune carte surveillée."
        await update.message.reply_text(f"<b>Cartes surveillées</b>\n{text}", parse_mode=ParseMode.HTML)

    async def ajouter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not mine(update):
            return
        query = " ".join(context.args).strip()
        if not query:
            await update.message.reply_text("Usage : /ajouter Charizard ex 199/165")
            return
        engine.storage.add_watch(query)
        await update.message.reply_text(f"Ajouté : {query}")

    async def retirer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not mine(update):
            return
        query = " ".join(context.args).strip()
        removed = engine.storage.remove_watch(query)
        await update.message.reply_text(f"Retiré : {query}" if removed else "Carte introuvable, vois /liste.")

    async def estimer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not mine(update):
            return
        offer = parse_offer(" ".join(context.args))
        if offer is None:
            await update.message.reply_text("Usage : /estimer <carte> <note> <prix>\nEx. : /estimer Umbreon VMAX 215/203 PSA 10 650")
            return
        query, grade, price = offer
        await update.message.reply_text(f"Je cherche la cote de {query} {grade}…")
        r = await engine.estimate(query, grade, price, "EN", False)
        if r is None:
            await update.message.reply_text(f"Pas assez de données pour {query} {grade}. Essaie le nom anglais et le numéro.")
            return
        good = r["profit_eur"] >= cfg.min_profit_eur and r["roi_pct"] >= cfg.min_roi_pct
        verdict = "✅ Bonne affaire" if good else ("⚠️ Marge trop faible" if r["profit_eur"] > 0 else "❌ Pas rentable")
        c = r["confidence"]
        await update.message.reply_text(
            f"<b>{verdict}</b> · confiance {c['score']}/100 ({c['label']})\n"
            f"🏷 {html.escape(query)} · {grade}\n💶 Prix : {price:.2f} €\n"
            f"📈 Cote : {r['valuation']['market_eur']:.2f} € ({html.escape(r['valuation']['source'])})\n"
            f"💰 Revente nette : {r['net_resale_eur']:.2f} € → <b>{r['profit_eur']:+.2f} € ({r['roi_pct']:+.0f} %)</b>\n"
            "Détail complet dans l'application PC.",
            parse_mode=ParseMode.HTML,
        )

    async def liens(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not mine(update):
            return
        lines = [
            f"• {html.escape(q)} : <a href=\"{html.escape(links.vinted(q))}\">Vinted</a> · "
            f"<a href=\"{html.escape(links.leboncoin(q))}\">Leboncoin</a>"
            for q in engine.storage.watchlist()
        ]
        await update.message.reply_text(
            "<b>Recherches Vinted et Leboncoin</b>\nOuvre un lien, puis « Sauvegarder la recherche » avec les "
            "notifications. Quand une annonce sort, vérifie-la avec /estimer.\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        )

    async def regles(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not mine(update):
            return
        await update.message.reply_text(
            f"Marketplaces : {', '.join(cfg.ebay_marketplaces)}\n"
            f"Prix d'achat : {cfg.min_price_eur:.0f}–{cfg.max_price_eur:.0f} €\n"
            f"Alerte si bénéfice ≥ {cfg.min_profit_eur:.0f} €, ROI ≥ {cfg.min_roi_pct:.0f} %, confiance ≥ {cfg.min_confidence:.0f}/100\n"
            f"Frais de revente : {cfg.sell_fee_pct:.1f} % + {cfg.sell_shipping_eur:.2f} €\n"
            f"Modifiable dans l'application : http://localhost:{cfg.web_port}"
        )

    for name, handler in [("start", start), ("help", start), ("scan", scan), ("statut", statut), ("liste", liste),
                          ("ajouter", ajouter), ("retirer", retirer), ("estimer", estimer), ("liens", liens),
                          ("regles", regles)]:
        app.add_handler(CommandHandler(name, handler))
    return app
