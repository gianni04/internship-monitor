# internship-monitor

A small Python bot that watches the career pages of Luxembourg banks and asset managers for internships. New offers go to Telegram, and each alert has a button that drafts a cover letter for that offer.

## How it works

- `scripts/check_all_offers.py` checks Schroders and Edmond de Rothschild (Oracle HCM job APIs), BGL BNP Paribas (career page), Société Générale Luxembourg (search API) and Quintet (graduate page, watched for changes). Pictet is not covered: no scraper is written for its careers site.
- An offer counts as an internship if the title contains words like "intern", "stage" or "trainee", or if the source gives a contract type of internship.
- Seen offers are stored in `config/*_known*.json`, so each offer is sent once. The first run stores what is already online and sends nothing.
- An offer is marked as seen only after the Telegram message goes out. If the send fails, it is retried on the next run.
- The alert has a cover letter button. `scripts/telegram_listener.py` waits for that press, reads the job description, and sends it to an LLM command-line tool (set in `scripts/cover_letter.py`) with your profile, a reference letter and style rules. The letter comes back in the chat and is saved in `letters/`.
- I run the check every 15 minutes with Windows Task Scheduler and start the listener at logon with `scripts/start_listener.bat`.

## Run it

```bash
pip install -r requirements.txt
cp config/telegram.example.json config/telegram.json
cp config/cover_letter_context.example.md config/cover_letter_context.md
python scripts/notify_telegram.py      # sends a test message to your chat
python scripts/check_all_offers.py     # one pass over all sources
python scripts/telegram_listener.py    # keep running for the cover letter button
```

Settings live in the JSON and Markdown files under `config/`, not in environment variables. Fill in `bot_token` and `chat_id` in `config/telegram.json`. The real files are git-ignored, so only the `.example` templates are in the repo. The cover letter button needs that command-line tool on your PATH.

## Limits

- The sources are the endpoints and pages the career sites use. They are not documented APIs and can change without notice.
- The GitHub Actions workflow only runs when you start it by hand, and it needs the Telegram secrets set in the repo.
- Cover letters are drafts. I read and correct every one before sending it.
