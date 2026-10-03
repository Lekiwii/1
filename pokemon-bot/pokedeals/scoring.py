"""Indice de confiance d'une bonne affaire : à quel point la cote et la revente sont sûres.

Il croise toutes les sources disponibles. Un indice élevé ne garantit pas la revente, mais un
indice faible signale qu'une ou plusieurs vérifications ont échoué.
"""
import statistics
from dataclasses import dataclass, field

from .cardinfo import CardInfo
from .social import Buzz


@dataclass
class Confidence:
    score: int
    reasons: list[tuple[str, str]] = field(default_factory=list)  # (« + » / « - » / « ! », explication)

    @property
    def label(self) -> str:
        if self.score >= 70:
            return "Fiable"
        if self.score >= 45:
            return "À vérifier"
        return "Risqué"


def dispersion(prices: list[float]) -> float | None:
    """Écart interquartile rapporté à la médiane : 0,1 = prix très homogènes, 0,5 = très dispersés."""
    if len(prices) < 4:
        return None
    q1, _, q3 = statistics.quantiles(prices, n=4)
    median = statistics.median(prices)
    return (q3 - q1) / median if median else None


def confidence(
    *,
    market_eur: float,
    comps: list[float],
    pricecharting_eur: float | None,
    card: CardInfo | None,
    buzz: Buzz | None,
    seller_feedback_score: int | None,
    language_explicit: bool,
) -> Confidence:
    score = 20
    reasons: list[tuple[str, str]] = []

    n = len(comps)
    if n >= 10:
        score += 25
        reasons.append(("+", f"{n} annonces comparables : cote solide"))
    elif n >= 5:
        score += 15
        reasons.append(("+", f"{n} annonces comparables"))
    elif n >= 3:
        score += 5
        reasons.append(("!", f"seulement {n} annonces comparables : cote fragile"))
    elif not pricecharting_eur:
        reasons.append(("-", "presque aucune annonce comparable"))

    d = dispersion(comps)
    if d is not None:
        if d <= 0.25:
            score += 10
            reasons.append(("+", "prix comparables homogènes"))
        elif d >= 0.6:
            score -= 10
            reasons.append(("-", "prix comparables très dispersés"))

    if pricecharting_eur:
        gap = abs(pricecharting_eur - market_eur) / market_eur
        if gap <= 0.2:
            score += 20
            reasons.append(("+", f"PriceCharting confirme la cote ({pricecharting_eur:.0f} €, ventes réelles)"))
        else:
            score -= 15
            reasons.append(("-", f"PriceCharting donne {pricecharting_eur:.0f} € : écart de {gap:.0%}"))

    if card and card.trend_eur:
        if market_eur >= card.trend_eur:
            score += 10
            reasons.append(("+", f"cote cohérente avec le prix non gradé Cardmarket ({card.trend_eur:.0f} €)"))
        else:
            score -= 20
            reasons.append(("-", f"cote gradée sous le prix non gradé Cardmarket ({card.trend_eur:.0f} €) : suspect"))
        m = card.momentum_pct
        if m is not None:
            if m >= 3:
                score += 10
                reasons.append(("+", f"prix Cardmarket en hausse ({m:+.0f} % sur 7 j vs 30 j)"))
            elif m <= -8:
                score -= 15
                reasons.append(("-", f"prix Cardmarket en forte baisse ({m:+.0f} %) : revente plus dure"))
            elif m <= -3:
                score -= 5
                reasons.append(("!", f"prix Cardmarket en baisse ({m:+.0f} %)"))
    elif card is None:
        reasons.append(("!", "carte non identifiée sur Cardmarket : vérifie qu'il s'agit bien de la bonne"))

    if buzz:
        if buzz.label == "buzz en hausse":
            score += 5
            reasons.append(("+", f"discussions Reddit en hausse ({buzz.week} cette semaine)"))
        elif buzz.label == "intérêt en baisse":
            score -= 5
            reasons.append(("!", "moins de discussions sur Reddit que d'habitude"))

    if seller_feedback_score is not None:
        if seller_feedback_score >= 1000:
            score += 10
            reasons.append(("+", f"vendeur très établi ({seller_feedback_score} avis)"))
        elif seller_feedback_score >= 200:
            score += 5
            reasons.append(("+", f"vendeur établi ({seller_feedback_score} avis)"))

    if language_explicit:
        score += 5
    else:
        reasons.append(("!", "langue non précisée dans le titre : vérifie sur les photos"))

    return Confidence(max(0, min(100, score)), reasons)
