import html
import json
import os
import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "telegram.json")

LETTER_MARKUP = {"inline_keyboard": [[{"text": "✍️ Lettre de motivation", "callback_data": "letter"}]]}

def esc(s) -> str:
    """Échappe un texte pour parse_mode HTML."""
    return html.escape(str(s))

def send_telegram_message(message: str, with_letter_button: bool = False) -> bool:
    if not os.path.exists(CONFIG_PATH):
        print(f"Erreur : fichier de configuration {CONFIG_PATH} introuvable.")
        return False

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        
        token = cfg.get("bot_token", "").strip()
        chat_id = cfg.get("chat_id", "").strip()
        
        if not token or not chat_id:
            print("Token ou Chat ID manquant dans config/telegram.json.")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        if with_letter_button:
            payload["reply_markup"] = LETTER_MARKUP
        
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("Notification Telegram envoyée avec succès.")
            return True
        else:
            print(f"Erreur Telegram ({resp.status_code}) : {resp.text}")
            return False
    except Exception as e:
        print(f"Exception lors de l'envoi Telegram : {e}")
        return False

if __name__ == "__main__":
    send_telegram_message("🤖 <b>Test du bot de veille stages/jobs</b>\n\nLe système de notification est opérationnel !")
