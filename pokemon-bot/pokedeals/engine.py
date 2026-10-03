"""Cœur de l'application : sources, scans périodiques, état partagé par l'interface et Telegram."""
import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Awaitable, Callable

import httpx

from . import links
from .cardinfo import CardInfo, PokemonTCG
from .config import Config, apply_overrides
from .deals import Deal, Estimate, Sources, estimate, find_deals
from .ebay import EbayClient
from .grading import Grade
from .pricing import PriceCharting
from .social import Reddit
from .storage import Storage

log = logging.getLogger(__name__)

Notifier = Callable[[list[Deal]], Awaitable[None]]


def card_dict(card: CardInfo | None) -> dict | None:
    if card is None:
        return None
    return {**asdict(card), "momentum_pct": card.momentum_pct, "trend_label": card.trend_label}


def valuation_dict(v) -> dict:
    return {
        "market_eur": v.market_eur,
        "source": v.source,
        "comps": sorted(v.comps),
        "pricecharting_eur": v.pricecharting_eur,
        "card": card_dict(v.card),
        "buzz": {"week": v.buzz.week, "month": v.buzz.month, "label": v.buzz.label} if v.buzz else None,
    }


def confidence_dict(c) -> dict:
    return {"score": c.score, "label": c.label, "reasons": [{"kind": k, "text": t} for k, t in c.reasons]}


def deal_dict(d: Deal, min_confidence: float) -> dict:
    l = d.listing
    return {
        "id": l.item_id,
        "title": l.title,
        "url": l.url,
        "image": l.image or ((d.valuation.card.image if d.valuation.card else "") or ""),
        "platform": l.source,
        "seller": l.seller,
        "seller_feedback_pct": l.seller_feedback_pct,
        "seller_feedback_score": l.seller_feedback_score,
        "query": d.query,
        "grade": str(d.variant.grade),
        "language": d.variant.language,
        "first_edition": d.variant.first_edition,
        "price": l.price,
        "shipping": l.shipping,
        "currency": l.currency,
        "cost_eur": d.cost_eur,
        "net_resale_eur": d.net_resale_eur,
        "profit_eur": d.profit_eur,
        "roi_pct": d.roi_pct,
        "valuation": valuation_dict(d.valuation),
        "confidence": confidence_dict(d.confidence),
        "alert": d.confidence.score >= min_confidence,
    }


def estimate_dict(e: Estimate) -> dict:
    return {
        "query": e.query,
        "grade": str(e.grade),
        "cost_eur": e.cost_eur,
        "net_resale_eur": e.net_resale_eur,
        "profit_eur": e.profit_eur,
        "roi_pct": e.roi_pct,
        "valuation": valuation_dict(e.valuation),
        "confidence": confidence_dict(e.confidence),
        "listings": e.listings,
    }


class Engine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.storage = Storage(cfg.db_path)
        apply_overrides(cfg, self.storage.settings())
        self.http = httpx.AsyncClient(timeout=30)
        self.sources = Sources(
            ebay=EbayClient(cfg.ebay_client_id, cfg.ebay_client_secret, self.http),
            pricecharting=PriceCharting(cfg.pricecharting_token, cfg.usd_to_eur, self.http) if cfg.pricecharting_token else None,
            pokemontcg=PokemonTCG(self.http, cfg.pokemontcg_api_key),
            reddit=Reddit(cfg.reddit_client_id, cfg.reddit_client_secret, self.http)
            if cfg.reddit_client_id and cfg.reddit_client_secret else None,
        )
        self.deals: list[Deal] = []
        self.last_scan: datetime | None = None
        self.next_scan: datetime | None = None
        self.scanning = False
        self.last_error = ""
        self.notifiers: list[Notifier] = []
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()

    # --- scans ---------------------------------------------------------------
    async def scan(self) -> list[Deal]:
        """Lance un scan complet ; renvoie les nouvelles affaires assez fiables pour une alerte."""
        async with self._lock:
            self.scanning = True
            try:
                deals = await find_deals(self.storage.watchlist(), self.cfg, self.sources)
                self.last_error = ""
            except Exception as exc:
                log.error("Scan échoué : %s", exc)
                self.last_error = str(exc)
                self.last_scan = datetime.now()
                return []
            finally:
                self.scanning = False
            self.deals = deals
            self.last_scan = datetime.now()
            fresh = [
                d for d in deals
                if d.confidence.score >= self.cfg.min_confidence
                and self.storage.is_new_alert(d.listing.item_id, d.cost_eur)
            ]
            for d in fresh:
                self.storage.mark_alerted(d.listing.item_id, d.cost_eur)
            self.storage.set_meta("last_deals", json.dumps([self.deal_json(d) for d in deals]))
            print(
                f"[{self.last_scan:%H:%M}] Scan terminé : {len(deals)} affaires en ligne, "
                f"{len(fresh)} nouvelles alertes.",
                flush=True,
            )
        for notify in self.notifiers:
            try:
                await notify(fresh)
            except Exception:
                log.exception("Envoi des alertes échoué")
        return fresh

    async def run_forever(self) -> None:
        await asyncio.sleep(3)
        while True:
            await self.scan()
            self.next_scan = datetime.now() + timedelta(minutes=self.cfg.scan_interval_min)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.cfg.scan_interval_min * 60)
            except asyncio.TimeoutError:
                pass

    def trigger_scan(self) -> None:
        self._wake.set()

    # --- données pour l'interface ---------------------------------------------
    def deal_json(self, d: Deal) -> dict:
        return deal_dict(d, self.cfg.min_confidence)

    def deals_json(self) -> list[dict]:
        if self.deals:
            return [self.deal_json(d) for d in self.deals]
        saved = self.storage.get_meta("last_deals")
        return json.loads(saved) if saved else []

    def status(self) -> dict:
        return {
            "scanning": self.scanning,
            "last_scan": self.last_scan.strftime("%H:%M") if self.last_scan else None,
            "next_scan": self.next_scan.strftime("%H:%M") if self.next_scan else None,
            "last_error": self.last_error,
            "watch_count": len(self.storage.watchlist()),
            "sources": {
                "eBay": ", ".join(self.cfg.ebay_marketplaces),
                "Cardmarket / TCGplayer (pokemontcg.io)": "actif",
                "PriceCharting": "actif" if self.sources.pricecharting else "non configuré",
                "Reddit": "actif" if self.sources.reddit else "non configuré",
            },
        }

    async def estimate(self, query: str, grade: Grade, price: float, language: str, first_edition: bool) -> dict | None:
        result = await estimate(query, grade, price, self.cfg, self.sources, language, first_edition)
        return estimate_dict(result) if result else None

    async def watch_details(self) -> list[dict]:
        async def one(query: str) -> dict:
            card = None
            if self.sources.pokemontcg:
                try:
                    card = await self.sources.pokemontcg.lookup(query)
                except Exception as exc:
                    log.warning("pokemontcg.io « %s » : %s", query, exc)
            return {"query": query, "card": card_dict(card), "vinted": links.vinted(query), "leboncoin": links.leboncoin(query)}

        return list(await asyncio.gather(*(one(q) for q in self.storage.watchlist())))

    async def trending(self) -> list[dict]:
        if not self.sources.pokemontcg:
            return []
        cards = await self.sources.pokemontcg.trending(min_price_eur=max(10, self.cfg.min_price_eur / 2))
        watched = {q.lower() for q in self.storage.watchlist()}
        result = []
        for c in cards:
            query = f"{c.name} {c.number}"
            result.append({**card_dict(c), "query": query, "watched": query.lower() in watched})
        return result

    def settings(self) -> dict:
        return {
            key: (",".join(getattr(self.cfg, key)) if isinstance(getattr(self.cfg, key), list) else getattr(self.cfg, key))
            for key in (
                "min_profit_eur", "min_roi_pct", "min_confidence", "sell_fee_pct", "sell_shipping_eur",
                "min_seller_feedback_pct", "min_seller_feedback_score", "min_price_eur", "max_price_eur",
                "scan_interval_min", "ebay_marketplaces",
            )
        }

    def update_settings(self, values: dict) -> None:
        clean = {k: str(v) for k, v in values.items() if k in self.settings()}
        apply_overrides(self.cfg, clean)
        for k, v in clean.items():
            self.storage.save_setting(k, v)

    async def close(self) -> None:
        await self.http.aclose()
