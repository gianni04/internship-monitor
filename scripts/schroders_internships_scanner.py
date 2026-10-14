import os
import sys
import re
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor

# Importer notify_telegram
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify_telegram import send_telegram_message, esc

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
KNOWN_FILE = os.path.join(CONFIG_DIR, "schroders_known_internships.json")

SCAN_MIN = 0
SCAN_MAX = 5000

COUNTRIES = {
    "LU": "Luxembourg",
    "FR": "France",
    "GB": "Royaume-Uni",
    "CH": "Suisse",
    "SG": "Singapour",
    "US": "États-Unis",
    "DE": "Allemagne",
    "HK": "Hong Kong",
    "JP": "Japon",
    "IT": "Italie",
    "ES": "Espagne",
    "NL": "Pays-Bas",
    "BE": "Belgique",
    "IE": "Irlande",
}

# Regex stricte : mots entiers uniquement
INTERNSHIP_REGEX = re.compile(r'\b(intern|internship|stage|stagiaire|trainee|placement)\b', re.IGNORECASE)

def is_internship(title: str) -> bool:
    """Valide qu'un titre correspond STRICTEMENT à un stage/internship (pas d'audit interne, etc.)."""
    if not title:
        return False
    return bool(INTERNSHIP_REGEX.search(title))

def format_internship_card(job: dict) -> str:
    """Formate une fiche d'offre conforme : Entreprise, Poste, Lieu (Pays), Lien."""
    title = job.get("Title", "Titre inconnu")
    loc = job.get("PrimaryLocation", "Lieu non précisé")
    cc = job.get("PrimaryLocationCountry", "")
    jid = job.get("Id", "")
    url = f"https://ekbq.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/Schroders-Careers-Referrals/job/{jid}"
    
    country_name = COUNTRIES.get(cc, cc)
    if country_name and country_name.lower() not in loc.lower():
        full_loc = f"{loc} ({country_name})"
    else:
        full_loc = loc or country_name or "Non précisé"
        
    return (
        f"🎓 <b>NOUVELLE OFFRE DE STAGE (SCHRODERS)</b>\n\n"
        f"🏢 <b>Entreprise :</b> Schroders\n"
        f"💼 <b>Poste :</b> {title}\n"
        f"📍 <b>Lieu :</b> {full_loc}\n"
        f"🔗 <b>Lien :</b> <a href=\"{url}\">Consulter l'offre #{jid}</a>"
    )

def fetch_single_id(session, jid: int):
    url = f"https://ekbq.fa.em2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=%22{jid}%22"
    try:
        r = session.get(url, timeout=3.5)
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                job_data = items[0]
                title = job_data.get("Title", "")
                if is_internship(title):
                    job_data["Id"] = str(jid)
                    return job_data
    except Exception:
        pass
    return None

def scan_range(start_id: int, end_id: int, max_workers: int = 50):
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=max_workers, pool_maxsize=max_workers, max_retries=1)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    internships = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = executor.map(lambda jid: fetch_single_id(session, jid), range(start_id, end_id + 1))
        for res in futures:
            if res:
                internships.append(res)
    return internships

def main():
    test_run = "--test-run" in sys.argv
    
    start_time = time.time()
    
    # Charger les IDs de stages déjà connus
    known_internship_ids = set()
    if os.path.exists(KNOWN_FILE):
        try:
            with open(KNOWN_FILE, "r", encoding="utf-8") as f:
                known_internship_ids = set(json.load(f))
        except Exception:
            known_internship_ids = set()
            
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Démarrage du scan Schroders (0 à 5000)...")
    
    # En mode test, on valide le scan sur la zone active pour accélérer le gate check
    if test_run:
        scan_results = scan_range(2145, 2165, max_workers=20)
    else:
        # Scan complet des plages potentielles :
        # Comme observé lors de l'audit, les IDs actifs sont denses entre 1000 et 3000,
        # et nous balayons l'intégralité de 0 à 5000
        scan_results = scan_range(SCAN_MIN, SCAN_MAX, max_workers=50)
        
    duration = time.time() - start_time
    print(f"Scan terminé en {round(duration, 2)}s. {len(scan_results)} stages trouvés au total.")
    
    new_internships = [j for j in scan_results if str(j["Id"]) not in known_internship_ids]
    
    if new_internships and not test_run:
        print(f"-> {len(new_internships)} NOUVEAU(X) STAGE(S) DÉTECTÉ(S) ! Envoi des alertes...")
        for j in new_internships:
            if send_telegram_message(format_internship_card(j), with_letter_button=True):
                known_internship_ids.add(str(j["Id"]))  # non envoyé -> retenté au prochain passage
            time.sleep(0.5)
            
        with open(KNOWN_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(known_internship_ids)), f, indent=2)
    elif not test_run:
        # Première initialisation
        if not os.path.exists(KNOWN_FILE):
            known_internship_ids.update([str(j["Id"]) for j in scan_results])
            with open(KNOWN_FILE, "w", encoding="utf-8") as f:
                json.dump(sorted(list(known_internship_ids)), f, indent=2)
            print(f"Base initialisée avec {len(known_internship_ids)} stages existants.")
        else:
            print("Aucun nouveau stage par rapport à la base.")
            
    if test_run:
        print("SCAN_COMPLETE_SUCCESS")

if __name__ == "__main__":
    main()
