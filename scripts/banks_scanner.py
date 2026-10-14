"""Veille stages Luxembourg : BGL BNP Paribas, Société Générale Luxembourg, Pictet, Edmond de Rothschild.

Chaque source = une fonction fetch_<banque>() -> list[dict(id, title, location, url)].
Etat : config/banks_known.json  {"<banque>": ["id", ...]}
"""
import os
import re
import sys
import json
import time
import html
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify_telegram import send_telegram_message, esc

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWN_FILE = os.path.join(BASE_DIR, "config", "banks_known.json")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
INTERNSHIP_REGEX = re.compile(
    r"\b(intern|interns|internship|internships|stage|stages|stagiaire|trainee|placement)\b", re.IGNORECASE)


def is_internship(title: str) -> bool:
    return bool(title and INTERNSHIP_REGEX.search(title))


# --- Sources (remplies après identification des endpoints) -------------------

def fetch_oracle_ce(host: str, site: str, location_facet: str) -> list:
    """Oracle HCM Candidate Experience (liste publique, filtrée par lieu côté serveur)."""
    api = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    jobs, offset = [], 0
    while True:
        finder = (f"findReqs;siteNumber={site},selectedLocationsFacet={location_facet},"
                  f"facetsList=LOCATIONS,limit=50,offset={offset},sortBy=POSTING_DATES_DESC")
        r = requests.get(api, params={"onlyData": "true", "expand": "requisitionList", "finder": finder},
                         headers={**UA, "Accept": "application/json"}, timeout=20)
        r.raise_for_status()
        data = r.json()["items"][0]
        for req in data.get("requisitionList", []):
            jobs.append({
                "id": req["Id"], "title": req["Title"], "location": req.get("PrimaryLocation"),
                "url": f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{req['Id']}",
            })
        offset += 50
        if offset >= data.get("TotalJobsCount", 0):
            return jobs


def fetch_edr():
    return fetch_oracle_ce("evht.fa.ocs.oraclecloud.eu", "CX_7001", "300000000468888")  # facette Luxembourg


BROWSER = {**UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "fr,en;q=0.9", "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
           "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1", "Upgrade-Insecure-Requests": "1",
           "Sec-CH-UA": '"Chromium";v="120", "Google Chrome";v="120"', "Sec-CH-UA-Platform": '"Windows"'}


def browser_get(session, url):
    """Akamai (group.bnpparibas) répond 403 + cookie au premier appel, puis 200."""
    for _ in range(4):
        r = session.get(url, headers=BROWSER, timeout=30)
        if r.status_code != 403:
            return r
        time.sleep(1)
    r.raise_for_status()


def fetch_bgl():
    """BGL BNP Paribas : listing HTML (10 cartes/page), au-delà de la dernière page les cartes se répètent."""
    base = "https://group.bnpparibas"
    listing = base + "/en/careers/all-job-offers/bgl-bnp-paribas/luxembourg-country"
    card = re.compile(r'<a href="(/en/careers/job-offer/([^"#?]+))" class="card-link">.*?'
                      r'<h3 class="title-4">(.*?)</h3>.*?<div class="offer-location">(.*?)</div>', re.S)
    s, jobs, page = requests.Session(), {}, 1
    while page <= 20:
        html_page = browser_get(s, listing if page == 1 else f"{listing}?page={page}").text
        new = 0
        for href, slug, title, loc in card.findall(html_page):
            oid = re.sub(r"-\d+$", "", slug)  # même offre listée 2x avec suffixe "-1"
            if oid not in jobs:
                new += 1
                clean = lambda x: html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x))).replace("​", "").strip()
                jobs[oid] = {"id": oid, "title": clean(title), "location": clean(loc) or "Luxembourg", "url": base + href}
        if not new:
            break
        page += 1
    return list(jobs.values())


def fetch_sg():
    """Société Générale Luxembourg : API de recherche du site carrière (token anonyme du front)."""
    site = "https://careers.societegenerale.com"
    s = requests.Session()
    csrf = re.search(r'"csrfToken":"([0-9a-f]+)"', s.get(site + "/", headers=BROWSER, timeout=30).text).group(1)
    token = s.get(site + "/sg-careers-offers/get-token", timeout=30,
                  headers={**UA, "X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": csrf}).json()["token"]
    api = "https://api.socgen.com/business-support/it-for-it-support/cognitive-service-knowledge/api/v1/search-profile"
    jobs, skip = [], 0
    while True:
        body = {"profile": "ces_profile_sgcareers", "lang": "fr", "responseType": "SearchResult",
                "query": {"advanced": [{"type": "simple", "name": "sourcestr6", "op": "eq", "value": "job"},
                                       {"type": "multi", "name": "sourcecsv1", "op": "eq", "values": ["LUX_A01", "LUX"]},
                                       {"type": "multi", "name": "sourcestr8", "op": "eq", "values": ["INTERNSHIP"]}],
                          "skipCount": 100, "skipFrom": skip, "sort": "sourcedatetime1.desc"}}
        r = requests.post(api, json=body, headers={**UA, "Authorization": "Bearer " + token}, timeout=60)
        r.raise_for_status()
        d = r.json()
        docs = d["Result"]["Docs"]
        skip += len(docs)
        # contrat INTERNSHIP filtré côté serveur : on force un mot-clé stage pour passer is_internship()
        jobs += [{"id": x["sourcestr4"], "title": x["title"] if is_internship(x["title"]) else f"Stage - {x['title']}",
                  "location": x["geo"].split(";")[1] if ";" in x["geo"] else "Luxembourg", "url": x["url1"]}
                 for x in docs]
        if not docs or skip >= d["TotalCount"]:
            return jobs


SOURCES = {
    "BGL BNP Paribas": fetch_bgl,
    "Société Générale Luxembourg": fetch_sg,
    "Edmond de Rothschild": fetch_edr,
    # Pictet : site SuccessFactors avec robots.txt "Disallow: /" -> non scrapé volontairement.
}


# --- Coeur -------------------------------------------------------------------

def format_card(bank: str, job: dict) -> str:
    return (
        f"🎓 <b>NOUVELLE OFFRE DE STAGE ({esc(bank.upper())})</b>\n\n"
        f"🏢 <b>Entreprise :</b> {esc(bank)}\n"
        f"💼 <b>Poste :</b> {esc(job['title'])}\n"
        f"📍 <b>Lieu :</b> {esc(job.get('location') or 'Luxembourg')}\n"
        f"🔗 <b>Lien :</b> <a href=\"{esc(job['url'])}\">Consulter l'offre</a>"
    )


def load_known() -> dict:
    if not os.path.exists(KNOWN_FILE):
        return {}
    with open(KNOWN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)  # fichier corrompu -> exception : on n'alerte pas tout le stock


def save_known(known: dict):
    tmp = KNOWN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: sorted(v) for k, v in known.items()}, f, indent=2, ensure_ascii=False)
    os.replace(tmp, KNOWN_FILE)


def main():
    known = load_known()
    for bank, fetch in SOURCES.items():
        try:
            jobs = [j for j in fetch() if is_internship(j["title"])]
        except Exception as e:
            print(f"- {bank}: erreur {e}")
            continue
        seen = set(known.get(bank, []))
        if bank not in known:  # premier passage : on mémorise sans alerter
            known[bank] = [str(j["id"]) for j in jobs]
            print(f"- {bank}: base initialisée ({len(jobs)} stages)")
            continue
        new = [j for j in jobs if str(j["id"]) not in seen]
        for j in new:
            if send_telegram_message(format_card(bank, j), with_letter_button=True):
                seen.add(str(j["id"]))
            time.sleep(0.5)
        known[bank] = sorted(seen)
        print(f"- {bank}: {len(jobs)} stages, {len(new)} nouveau(x)")
    save_known(known)


if __name__ == "__main__":
    main()
