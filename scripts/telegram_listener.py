"""Écoute les clics sur le bouton « Lettre de motivation » (long-polling) et renvoie la lettre générée.

Lancement: pythonw scripts/telegram_listener.py  (logs: logs/telegram_listener.log)
"""
import json
import logging
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cover_letter import generate_letter_file  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "telegram.json")
OFFSET_PATH = os.path.join(BASE_DIR, "config", "telegram_offset.txt")
LOG_PATH = os.path.join(BASE_DIR, "logs", "telegram_listener.log")
CHUNK = 3900

log = logging.getLogger("listener")
_token = ""


def setup_logging():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")


def safe(e) -> str:
    """Message d'erreur sans le token (les exceptions requests contiennent l'URL)."""
    return str(e).replace(_token, "***") if _token else str(e)


def api(method: str, timeout: int = 15, **kw):
    r = requests.post(f"https://api.telegram.org/bot{_token}/{method}", timeout=timeout, **kw)
    r.raise_for_status()
    return r.json()


def parse_card(text: str, entities: list) -> dict | None:
    """Extrait company/title/location/url d'une carte d'alerte. None si ce n'en est pas une."""
    def field(label):
        m = re.search(rf"^\W*{label}\s*:\s*(.+)$", text or "", re.M)
        return m.group(1).strip() if m else ""
    company, title, location = field("Entreprise"), field("Poste"), field("Lieu")
    url = next((e["url"] for e in entities or [] if e.get("type") == "text_link" and e.get("url")), "")
    if not (company and title):
        return None
    return {"company": company, "title": title, "location": location, "url": url}


def split_chunks(text: str, size: int = CHUNK) -> list[str]:
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        while len(para) > size:  # paragraphe géant: coupe sur un espace
            cut = para.rfind(" ", 0, size)
            if cut <= 0:
                cut = size
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(para[:cut])
            para = para[cut:].lstrip()
        if cur and len(cur) + len(para) + 2 > size:
            chunks.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    return chunks


def handle_callback(cb: dict, chat_id: str):
    msg = cb.get("message") or {}
    if str(msg.get("chat", {}).get("id")) != chat_id or cb.get("data") != "letter":
        log.warning("callback ignoré (chat=%s data=%s)", msg.get("chat", {}).get("id"), cb.get("data"))
        return
    card = parse_card(msg.get("text", ""), msg.get("entities", []))
    if not card:
        api("answerCallbackQuery", json={"callback_query_id": cb["id"], "text": "Carte d'offre illisible."})
        return
    try:
        api("answerCallbackQuery", json={"callback_query_id": cb["id"], "text": "Rédaction en cours…"})
    except Exception as e:  # requête trop ancienne: on génère quand même
        log.warning("answerCallbackQuery: %s", safe(e))
    reply_to = msg.get("message_id")
    log.info("génération: %s / %s", card["company"], card["title"])
    try:
        letter, path = generate_letter_file(card["company"], card["title"], card["location"], card["url"])
    except Exception as e:
        log.error("génération échouée: %s", safe(e))
        api("sendMessage", json={"chat_id": chat_id, "reply_to_message_id": reply_to,
                                  "text": f"Échec de la rédaction : {safe(e)[:500]}"})
        return
    for part in split_chunks(letter):
        api("sendMessage", json={"chat_id": chat_id, "reply_to_message_id": reply_to, "text": part})
    with open(path, "rb") as f:
        api("sendDocument", timeout=60, data={"chat_id": chat_id, "reply_to_message_id": reply_to},
            files={"document": (os.path.basename(path), f)})
    log.info("lettre envoyée: %s", os.path.basename(path))


def read_offset() -> int:
    try:
        with open(OFFSET_PATH, encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def main():
    global _token
    setup_logging()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    _token, chat_id = cfg["bot_token"].strip(), str(cfg["chat_id"]).strip()
    offset = read_offset()
    log.info("listener démarré (offset=%s)", offset)
    while True:
        try:
            updates = api("getUpdates", timeout=60,
                          json={"timeout": 50, "offset": offset, "allowed_updates": ["callback_query"]})["result"]
        except Exception as e:
            log.error("getUpdates: %s", safe(e))
            time.sleep(10)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            with open(OFFSET_PATH, "w", encoding="utf-8") as f:  # avant traitement: pas de rejeu en boucle
                f.write(str(offset))
            if "callback_query" not in u:
                continue
            try:
                handle_callback(u["callback_query"], chat_id)
            except Exception as e:
                log.error("callback: %s", safe(e))
                time.sleep(5)


if __name__ == "__main__":
    main()
