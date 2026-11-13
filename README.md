# Rent Check

Checks wba.nl every 10 minutes for new rental listings in and around Apeldoorn,
Deventer, Zwolle and Arnhem, and sends each new one to you on Telegram with a
photo, the details and a button that opens the listing.

## Setup (about 10 minutes)

1. **Create the bot.** In Telegram, open a chat with **@BotFather**, send
   `/newbot`, and pick a name and a username. BotFather replies with a token
   that looks like `123456789:AAH...`. Keep it private.
2. **Start the bot.** Open your new bot's chat and press **Start** (a bot can
   only message people who have started it).
3. **Find your chat ID.** Open this address in a browser, with your token in
   place of `TOKEN`:
   `https://api.telegram.org/botTOKEN/getUpdates`
   Look for `"chat":{"id":123456789` – that number is your chat ID.
4. **GitHub.** Create a new **public** repository (scheduled jobs are free and
   unlimited on public repositories) and upload everything in this folder,
   including the hidden `.github` folder.
5. **Secrets.** In the repository go to *Settings → Secrets and variables →
   Actions → New repository secret* and add two:
   `TELEGRAM_BOT_TOKEN` (the token) and `TELEGRAM_CHAT_ID` (the number).
6. **First run.** Open the *Actions* tab, choose *Rent check*, press
   *Run workflow*. The first run only records what is already online and sends
   nothing. From then on it runs by itself and messages you about new listings.

## Try it on your Mac first

    python3 check.py --dry-run     # shows what it finds, saves nothing

    TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python3 check.py

To see a real message straight away, run it once, delete the newest ID from
`seen_ids` in `listings.json`, and run it again.

## Changing what you get

Open `check.py`; the settings are at the top:

- `TOWNS` – the towns to watch
- `SKIP_TYPES` – property types to ignore (e.g. add `"kamer"`, `"chalet"`)
- `SKIP_STATUSES` – listings first seen with these statuses are not sent
- `MAX_RENT` – ignore anything above this monthly rent

## Files

- `check.py` – the checker
- `listings.json` – created by the first run; what has been seen so far
- `.github/workflows/check.yml` – the 10-minute schedule
