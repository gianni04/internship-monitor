# internship-monitor

Small Python bot I use for my internship search in Luxembourg. It checks the career sites of a few banks and asset managers, and sends new internship offers to Telegram. Each alert has a button that asks an LLM to draft a cover letter for that offer, in the style of a letter I wrote myself.

## Sources

| Company | How |
|---|---|
| Schroders | Oracle HCM REST API, requisition by ID |
| Edmond de Rothschild | Oracle HCM REST API, job list filtered on Luxembourg |
| BGL BNP Paribas | Career site listing (HTML) |
| Société Générale Luxembourg | Search API used by the career site, contract type = internship |
| Quintet Private Bank | Watches the graduates & interns page for a change |

Pictet is not included: its job site disallows crawling in robots.txt.

Internships are detected from the title (`intern`, `internship`, `stage`, `stagiaire`, `trainee`, `placement`, whole words only) or from the contract type when the API gives it.

## How it works

- `scripts/check_all_offers.py` runs every source. Seen offer IDs are kept in `config/*_known*.json`. The first run of a source stores what is already online without sending alerts.
- An offer is marked as seen only if the Telegram message was actually sent, so a failed send is retried on the next run.
- `scripts/telegram_listener.py` long-polls Telegram. When the "Cover letter" button is pressed, it reads company, title and link from the alert, fetches the job description (Oracle API when possible, page text otherwise), and calls the Claude Code CLI (`claude -p`) with my profile, a reference letter and style rules from `config/cover_letter_context.md`. The letter comes back in the chat as text and as a `.md` file.

## Setup

```bash
pip install -r requirements.txt
cp config/telegram.example.json config/telegram.json            # bot token + chat id
cp config/cover_letter_context.example.md config/cover_letter_context.md
python scripts/check_all_offers.py      # one pass over all sources
python scripts/telegram_listener.py     # keep running for the cover letter button
```

I run `check_all_offers.py` every 15 minutes with Windows Task Scheduler and start the listener at logon. A GitHub Actions workflow is included (manual trigger only).

## Limits

- The sources are undocumented endpoints used by the career sites. They can change without notice.
- Cover letters are drafts. I read and correct every one before sending.
