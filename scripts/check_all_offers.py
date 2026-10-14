import os
import sys
import requests
from datetime import datetime

from notify_telegram import send_telegram_message

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")

def check_schroders():
    """Vérifie Schroders via le scanner exclusif de stages (0 à 5000)."""
    import schroders_internships_scanner
    schroders_internships_scanner.main()
    return "Vérification Schroders (stages uniquement) terminée."

def check_quintet():
    """Vérifie si la page Graduate & Interns de Quintet mentionne de nouvelles informations."""
    cache_file = os.path.join(CONFIG_DIR, "quintet_state.txt")
    url = "https://www.quintet.com/en-gb/your-career-at-quintet/graduates-and-interns"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return f"Quintet : Erreur HTTP {resp.status_code}"
            
        content = resp.text
        has_no_intake = "no Graduate Programme intake for 2026" in content
        current_state = "CLOSED" if has_no_intake else "OPEN_OR_CHANGED"
        
        prev_state = None
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                prev_state = f.read().strip()
                
        if prev_state and prev_state != current_state:
            msg = (
                "🎓 <b>NOUVELLE OFFRE DE STAGE (QUINTET)</b>\n\n"
                "🏢 <b>Entreprise :</b> Quintet Private Bank\n"
                "💼 <b>Poste :</b> Graduate & Interns Programme\n"
                "📍 <b>Lieu :</b> Luxembourg (Luxembourg)\n"
                f"🔗 <b>Lien :</b> <a href=\"{url}\">Consulter l'offre</a>"
            )
            if not send_telegram_message(msg, with_letter_button=True):
                return "Quintet : changement détecté mais envoi Telegram échoué (retenté au prochain passage)."
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(current_state)
            return "Quintet : Changement détecté et notifié sur Telegram !"
        elif not prev_state:
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(current_state)
            return "Quintet : État initial enregistré."
        else:
            return "Quintet : Aucun changement (toujours fermé pour 2026)."
    except Exception as e:
        return f"Quintet exception: {e}"

def check_banks():
    """BGL BNP Paribas, SG Luxembourg, Edmond de Rothschild (stages Luxembourg)."""
    import banks_scanner
    banks_scanner.main()
    return "Vérification banques Luxembourg terminée."

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Lancement de la vérification globale...")
    res_schroders = check_schroders()
    print(f"- Schroders: {res_schroders}")
    
    res_quintet = check_quintet()
    print(f"- Quintet: {res_quintet}")

    try:
        print(f"- Banques: {check_banks()}")
    except Exception as e:
        print(f"- Banques exception: {e}")

if __name__ == "__main__":
    main()
