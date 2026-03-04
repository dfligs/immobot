# Immobilienscout24 Saved-Search Auto Message Bot

Monitors one or multiple Immobilienscout24 saved searches and sends a pre-written message when a new listing appears.

## What this version does

- Works with `https://www.immobilienscout24.de/` saved searches.
- Accepts one or many saved-search URLs (for example links containing `saveSearchId=...`).
- Tracks already seen listings in a local state file.
- Sends your pre-written message to newly detected listings.
- Reports failed auto-send attempts in console and in a JSONL log file.

## Important notes

- Use responsibly and in line with website terms.
- Site structure can change over time; selectors may need updates.
- Messaging works best when the selected browser uses a profile already logged into your Immobilienscout24 account.

## Requirements

- Python 3.9+
- Google Chrome or Firefox
- ChromeDriver (for Chrome) or geckodriver (for Firefox)
- Python package: `selenium`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Files used by the script

- `immo.py`: main monitor loop and CLI
- `submit.py`: browser/session, listing extraction, and message sending helpers
- `message.txt`: your pre-written message (you create this file)
- `seen_listings.json`: generated state file of already seen listings
- `message_failures.jsonl`: generated log file for failed sends
- `message_sent.jsonl`: generated log file for successful sends

## Setup

1. Create `message.txt` in the repo root and put your full message there.
  - You can start from `message.example.txt`.
2. Collect saved search URL(s), e.g. from:
    - `https://www.immobilienscout24.de/savedsearch/myscout/manage/`
3. Decide whether to pass URLs directly via CLI or from a text file.

Optional: create `searches.txt` with one URL per line.

- You can start from `searches.example.txt` and copy it to `searches.txt`.

## Usage

### Monitor one saved search

```bash
python immo.py --search-url "https://www.immobilienscout24.de/Suche/shape/...&saveSearchId=123456"
```

### Monitor multiple saved searches

```bash
python immo.py \
  --search-url "https://www.immobilienscout24.de/Suche/shape/...&saveSearchId=111" \
  --search-url "https://www.immobilienscout24.de/Suche/shape/...&saveSearchId=222"
```

### Monitor from file

```bash
python immo.py --search-file searches.txt
```

### Recommended: reuse logged-in Chrome profile

```bash
python immo.py \
  --search-file searches.txt \
  --user-data-dir "C:\\Users\\<you>\\AppData\\Local\\Google\\Chrome\\User Data" \
  --profile-directory "Default"
```

If login is required, the script opens browser and waits for you to log in once.

### Firefox example

```bash
python immo.py \
  --browser firefox \
  --search-file searches.txt \
  --firefox-profile "/path/to/firefox/profile"
```

## Useful options

- `--interval 60` polling interval in seconds (default `60`)
- `--message-file message.txt` custom message file path
- `--state-file seen_listings.json` custom state file path
- `--failures-file message_failures.jsonl` custom failures log path
- `--sent-file message_sent.jsonl` custom successful-sends log path
- `--browser chrome|firefox` choose browser engine (default `chrome`)
- `--headless` run without visible browser (not recommended for first login)
- `--driver-path <path>` explicit webdriver path (ChromeDriver or geckodriver)
- `--initial-send-existing` on first run, also message listings already visible now
- `--dry-run` detect/report new listings but do not send any messages
- `--user-data-dir ...` Chrome-only user data path
- `--profile-directory ...` Chrome-only profile folder name
- `--firefox-profile ...` Firefox-only profile directory path
- `--import-cookies is24_cookies.json` restore session cookies before login checks
- `--export-cookies is24_cookies.json` export current session cookies after login/bootstrap

See all options:

```bash
python immo.py --help
```

## How failure reporting works

When a new listing is found but auto-message cannot be submitted, the script:

- prints `FAILED: <listing_url> | <reason>` to console
- appends a JSON line to `message_failures.jsonl` with:
  - timestamp
  - search URL
  - listing URL
  - failure reason

This gives you a clear manual follow-up list.

If the site shows a human-verification/CAPTCHA page, the script logs this as a failure and skips that search cycle until you intervene manually.

## Successful send audit log

When a message is successfully sent, the script appends one JSON line to `message_sent.jsonl` containing:

- timestamp
- search URL
- listing URL

## Headless Pi4 session fallback (cookie export/import)

This helps reduce how often you need interactive re-login on a headless Raspberry Pi.

1. Bootstrap login once on a machine/session with display:

```bash
python immo.py \
  --search-file searches.txt \
  --export-cookies is24_cookies.json
```

2. Copy `is24_cookies.json` securely to the Pi.

3. Run headless on Pi with cookie import:

```bash
python immo.py \
  --search-file searches.txt \
  --headless \
  --import-cookies is24_cookies.json \
  --export-cookies is24_cookies.json
```

Notes:

- If imported cookies are expired/invalid, the script falls back to normal login flow.
- Keep cookie files private (`chmod 600`) and never commit them to git.
- Cookies may still expire or be invalidated by site/device/IP checks.

## Legacy scripts

- `wg-gesucht.py`, `wg-gesucht-spider.py`, and `submit_wg.py` are retained as legacy WG-Gesucht workflow.
- `immo_spider.py` is now a legacy placeholder; current Immoscout flow is `immo.py` + `submit.py`.
