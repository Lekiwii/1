"""Assistant de premier lancement : demande les clés, les vérifie et remplit le fichier .env."""
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"


def _set(key: str, value: str) -> None:
    lines = (ENV if ENV.exists() else EXAMPLE).read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ask(question: str) -> str:
    while True:
        answer = input(f"\n{question}\n> ").strip()
        if answer:
            return answer


def _telegram(api: str, method: str, **params) -> dict:
    return httpx.get(f"https://api.telegram.org/bot{api}/{method}", params=params, timeout=40).json()


def run(values: dict[str, str]) -> None:
    print("=" * 60)
    print("  Configuration du bot Pokémon (à faire une seule fois)")
    print("=" * 60)

    token = values.get("TELEGRAM_TOKEN", "")
    bot_name = ""
    while True:
        if not token:
            token = _ask(
                "1) Sur Telegram, ouvre @BotFather, envoie /newbot, choisis un nom,\n"
                "   puis colle ici le token qu'il te donne (ex. 123456:ABC-DEF...) :"
            )
        me = _telegram(token, "getMe")
        if me.get("ok"):
            bot_name = me["result"]["username"]
            print(f"   OK, bot @{bot_name} trouvé.")
            _set("TELEGRAM_TOKEN", token)
            break
        print("   Ce token ne marche pas, recommence.")
        token = ""

    client_id, secret = values.get("EBAY_CLIENT_ID", ""), values.get("EBAY_CLIENT_SECRET", "")
    while True:
        if not (client_id and secret):
            print(
                "\n2) Clés eBay : va sur https://developer.ebay.com, crée un compte,\n"
                "   puis « Application Keys » > « Create a keyset » en Production."
            )
            client_id = _ask("   Colle l'App ID (Client ID) :")
            secret = _ask("   Colle le Cert ID (Client Secret) :")
        resp = httpx.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            auth=(client_id, secret),
            data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
            timeout=30,
        )
        if resp.status_code == 200:
            print("   OK, clés eBay valides.")
            _set("EBAY_CLIENT_ID", client_id)
            _set("EBAY_CLIENT_SECRET", secret)
            break
        try:
            reason = resp.json().get("error_description") or resp.json().get("error") or resp.text
        except ValueError:
            reason = resp.text
        print(f"   eBay refuse ces clés (code {resp.status_code}) : {reason}")
        if resp.status_code == 401:
            print(
                "   Si tu as bien copié l'App ID et le Cert ID de la colonne Production, eBay a sans doute\n"
                "   désactivé ces clés : sur developer.ebay.com > Application Keysets, règle\n"
                "   « Marketplace account deletion » sur « Not persisting eBay data », puis relance LANCER.bat."
            )
            raise SystemExit(1)
        client_id = secret = ""

    if not values.get("TELEGRAM_CHAT_ID"):
        print(f"\n3) Sur Telegram, ouvre https://t.me/{bot_name} et envoie /start au bot.")
        print("   J'attends ton message (2 minutes max)...")
        offset, deadline = 0, time.time() + 120
        while time.time() < deadline:
            updates = _telegram(token, "getUpdates", offset=offset, timeout=20).get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                chat = (update.get("message") or {}).get("chat")
                if chat:
                    _set("TELEGRAM_CHAT_ID", str(chat["id"]))
                    _telegram(token, "getUpdates", offset=offset)  # marque le message comme lu
                    print(f"   OK, c'est toi ({chat.get('first_name', chat['id'])}).")
                    print("\nConfiguration terminée ! Le bot démarre.\n")
                    return
        raise SystemExit("Pas reçu de message. Relance LANCER.bat et envoie /start au bot.")
    print("\nConfiguration terminée ! Le bot démarre.\n")
