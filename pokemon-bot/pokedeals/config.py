import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _float(name: str, default: float) -> float:
    value = os.environ.get(name, "")
    return float(value) if value else default


@dataclass
class Config:
    telegram_token: str = ""
    telegram_chat_id: int | None = None
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    ebay_marketplaces: list[str] = field(default_factory=lambda: ["EBAY_FR"])
    pricecharting_token: str = ""
    usd_to_eur: float = 0.92
    gbp_to_eur: float = 1.17
    comps_discount_pct: float = 10
    min_profit_eur: float = 30
    min_roi_pct: float = 15
    sell_fee_pct: float = 13
    sell_shipping_eur: float = 8
    min_seller_feedback_pct: float = 98
    min_seller_feedback_score: int = 50
    min_price_eur: float = 20
    max_price_eur: float = 2000
    scan_interval_min: float = 15
    db_path: str = "pokedeals.sqlite3"

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        markets = os.environ.get("EBAY_MARKETPLACES", "EBAY_FR")
        return cls(
            telegram_token=os.environ.get("TELEGRAM_TOKEN", ""),
            telegram_chat_id=int(chat_id) if chat_id else None,
            ebay_client_id=os.environ.get("EBAY_CLIENT_ID", ""),
            ebay_client_secret=os.environ.get("EBAY_CLIENT_SECRET", ""),
            ebay_marketplaces=[m.strip() for m in markets.split(",") if m.strip()],
            pricecharting_token=os.environ.get("PRICECHARTING_TOKEN", ""),
            usd_to_eur=_float("USD_TO_EUR", 0.92),
            gbp_to_eur=_float("GBP_TO_EUR", 1.17),
            comps_discount_pct=_float("COMPS_DISCOUNT_PCT", 10),
            min_profit_eur=_float("MIN_PROFIT_EUR", 30),
            min_roi_pct=_float("MIN_ROI_PCT", 15),
            sell_fee_pct=_float("SELL_FEE_PCT", 13),
            sell_shipping_eur=_float("SELL_SHIPPING_EUR", 8),
            min_seller_feedback_pct=_float("MIN_SELLER_FEEDBACK_PCT", 98),
            min_seller_feedback_score=int(_float("MIN_SELLER_FEEDBACK_SCORE", 50)),
            min_price_eur=_float("MIN_PRICE_EUR", 20),
            max_price_eur=_float("MAX_PRICE_EUR", 2000),
            scan_interval_min=_float("SCAN_INTERVAL_MIN", 15),
            db_path=os.environ.get("DB_PATH", "pokedeals.sqlite3"),
        )
