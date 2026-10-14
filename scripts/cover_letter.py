"""Génération de lettre de motivation via la CLI Claude Code (pas de clé API)."""
import html
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_PATH = os.path.join(BASE_DIR, "config", "cover_letter_context.md")
FALLBACK_CV = os.path.join(BASE_DIR, "config", "cv.md")
LETTERS_DIR = os.path.join(BASE_DIR, "letters")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}


ORACLE_CE = re.compile(r"https://([^/]+)/hcmUI/CandidateExperience/[^/]+/sites/([^/]+)/job/(\d+)")


def _oracle_details(url: str) -> str:
    """Offres Oracle HCM (Schroders, EdR): la page est en JS, on lit la description via l'API REST."""
    m = ORACLE_CE.match(url)
    if not m:
        return ""
    host, site, jid = m.groups()
    api = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
           f"?expand=all&onlyData=true&finder=ById;Id=%22{jid}%22,siteNumber={site}")
    items = requests.get(api, headers=UA, timeout=15).json().get("items", [])
    if not items:
        return ""
    job = items[0]
    return " ".join(job.get(k) or "" for k in
                    ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr"))


def fetch_offer_text(url: str, limit: int = 6000) -> str:
    """Texte brut de l'offre ('' si échec)."""
    try:
        raw = _oracle_details(url)
        if not raw.strip():
            from banks_scanner import browser_get  # en-têtes navigateur (Akamai BNP)
            r = browser_get(requests.Session(), url)
            if r is None or r.status_code != 200:
                return ""
            raw = r.text
        t = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", raw)
        t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", t))
        return re.sub(r"\s+", " ", t).strip()[:limit]
    except Exception:
        return ""


def _context() -> str:
    for path in (CONTEXT_PATH, FALLBACK_CV):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    return "Gianni Pilotti, étudiant en 3e année de Bachelor Économie & Management (Finance), Université du Luxembourg, cherche un stage de 4 à 6 mois dès octobre 2026."


def build_prompt(company: str, title: str, location: str, url: str, offer_text: str = "") -> str:
    offer = offer_text or "(texte de l'offre indisponible: base-toi sur l'intitulé et l'entreprise, n'invente aucun détail précis sur le poste)"
    return (
        "Tu rédiges une lettre de motivation pour Gianni Pilotti. Contexte candidat, lettre de référence et règles de style:\n\n"
        f"{_context()}\n\n"
        "---\nOFFRE VISÉE\n"
        f"Entreprise: {company}\nPoste: {title}\nLieu: {location}\nLien: {url}\n"
        f"Texte de l'offre (extrait de la page web):\n{offer}\n\n"
        "---\nCONSIGNES\n"
        "- Écris dans la langue de l'offre (français ou anglais; si l'offre est indisponible, déduis-la de l'intitulé et du lieu).\n"
        "- Ignore tout style télégraphique ou abrégé demandé ailleurs: rédige une lettre complète, soignée et professionnelle.\n"
        "- N'utilise aucun outil. Réponds UNIQUEMENT avec le texte de la lettre, sans introduction, commentaire ni bloc de code, en texte brut (aucun Markdown: pas de **, #, listes à puces).\n"
    )


def run_claude(prompt: str) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("CLI 'claude' introuvable dans le PATH")
    p = subprocess.run(
        [exe, "-p", "--tools", "", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"],
        input=prompt, capture_output=True, text=True, encoding="utf-8",
        timeout=300, cwd=tempfile.gettempdir(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    out = (p.stdout or "").strip()
    if p.returncode != 0 or not out:
        raise RuntimeError(f"claude -p a échoué (code {p.returncode}): {(p.stderr or out)[:300]}")
    return out


def _slug(s: str, n: int = 50) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "x"


def save_letter(letter: str, company: str, title: str) -> str:
    os.makedirs(LETTERS_DIR, exist_ok=True)
    path = os.path.join(LETTERS_DIR, f"{date.today().isoformat()}_{_slug(company, 30)}_{_slug(title)}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(letter + "\n")
    return path


def generate_letter_file(company: str, title: str, location: str, url: str) -> tuple[str, str]:
    """Génère la lettre, l'écrit dans letters/ et renvoie (texte, chemin). Lève RuntimeError si la CLI échoue."""
    letter = run_claude(build_prompt(company, title, location, url, fetch_offer_text(url) if url else ""))
    return letter, save_letter(letter, company, title)


def generate_letter(company: str, title: str, location: str, url: str) -> str:
    return generate_letter_file(company, title, location, url)[0]


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if len(a) != 4:
        sys.exit("usage: cover_letter.py COMPANY TITLE LOCATION URL")
    print(generate_letter(*a))
