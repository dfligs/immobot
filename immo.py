import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Set

import submit


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_state(path: str) -> Dict[str, List[str]]:
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_state(path: str, state: Dict[str, List[str]]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def _append_failure(path: str, payload: Dict[str, str]) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _append_sent(path: str, payload: Dict[str, str]) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _sleep_with_countdown(seconds: int) -> None:
    wait_seconds = max(5, seconds)
    for remaining in range(wait_seconds, 0, -1):
        print(
            f"[{_now_iso()}] Next check in {remaining:02d}s...",
            end="\r",
            flush=True,
        )
        time.sleep(1)
    print(" " * 80, end="\r", flush=True)


def _read_message(path: str) -> str:
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Message file not found: {path}. Create it and put your pre-written message there."
        )
    with open(path, "r", encoding="utf-8") as handle:
        message = handle.read().strip()
    if not message:
        raise ValueError(f"Message file is empty: {path}")
    return message


def _read_search_urls(search_urls: List[str], search_file: str) -> List[str]:
    urls: List[str] = list(search_urls or [])
    if search_file:
        if not os.path.isfile(search_file):
            raise FileNotFoundError(f"Search URL file not found: {search_file}")
        with open(search_file, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)

    normalized: List[str] = []
    seen: Set[str] = set()
    for url in urls:
        if "immobilienscout24.de" not in url:
            raise ValueError(
                "All search URLs must point to immobilienscout24.de and should be saved search links."
            )
        clean = url.strip()
        if clean not in seen:
            normalized.append(clean)
            seen.add(clean)
    if not normalized:
        raise ValueError("At least one search URL is required.")
    return normalized


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor one or more Immobilienscout24 saved searches and send a pre-written "
            "message to newly appearing listings."
        )
    )
    parser.add_argument(
        "--browser",
        choices=["chrome", "firefox"],
        default="chrome",
        help="Browser engine to use (default: chrome).",
    )
    parser.add_argument(
        "--search-url",
        action="append",
        default=[],
        help="Saved search URL to monitor. Repeat this argument for multiple URLs.",
    )
    parser.add_argument(
        "--search-file",
        default="",
        help="Optional text file with one saved search URL per line.",
    )
    parser.add_argument(
        "--message-file",
        default="message.txt",
        help="Path to the text file containing your message.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds (default: 60).",
    )
    parser.add_argument(
        "--state-file",
        default="seen_listings.json",
        help="Path to state file storing already seen listing URLs.",
    )
    parser.add_argument(
        "--failures-file",
        default="message_failures.jsonl",
        help="Path to JSONL file where failed auto-send attempts are recorded.",
    )
    parser.add_argument(
        "--sent-file",
        default="message_sent.jsonl",
        help="Path to JSONL file where successful message sends are recorded.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless. Use non-headless mode for first login/profile setup.",
    )
    parser.add_argument(
        "--driver-path",
        default="",
        help="Optional webdriver executable path (chromedriver or geckodriver).",
    )
    parser.add_argument(
        "--user-data-dir",
        default="",
        help="Optional Chrome user data directory to reuse a logged-in profile.",
    )
    parser.add_argument(
        "--profile-directory",
        default="",
        help="Optional Chrome profile directory, e.g. 'Default' or 'Profile 1'.",
    )
    parser.add_argument(
        "--firefox-profile",
        default="",
        help="Optional Firefox profile directory path (Firefox only).",
    )
    parser.add_argument(
        "--initial-send-existing",
        action="store_true",
        help=(
            "On first run (no prior state for a search), also message currently visible listings. "
            "By default, first run only establishes baseline and messages only future new listings."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect and report new listings, but do not send any messages.",
    )
    parser.add_argument(
        "--import-cookies",
        default="",
        help="Optional JSON cookie file to restore an authenticated session before login checks.",
    )
    parser.add_argument(
        "--export-cookies",
        default="",
        help="Optional path to write current session cookies after login/bootstrap.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        search_urls = _read_search_urls(args.search_url, args.search_file)
        message_text = _read_message(args.message_file)
    except Exception as exc:
        print(f"[{_now_iso()}] Configuration error: {exc}")
        return 1

    state: Dict[str, List[str]] = _load_state(args.state_file)

    try:
        print(
            f"[{_now_iso()}] Browser: {args.browser} | Monitoring {len(search_urls)} saved search(es)."
        )
        for idx, search_url in enumerate(search_urls, start=1):
            print(f"[{_now_iso()}] Search {idx}: {search_url}")

        while True:
            print(f"[{_now_iso()}] Starting monitoring cycle...")
            for search_url in search_urls:
                driver = None
                try:
                    print(f"[{_now_iso()}] Opening browser session for search...")
                    driver = submit.create_driver(
                        browser=args.browser,
                        headless=args.headless,
                        driver_path=args.driver_path or None,
                        user_data_dir=args.user_data_dir or None,
                        profile_directory=args.profile_directory or None,
                        firefox_profile=args.firefox_profile or None,
                    )

                    if args.import_cookies:
                        ok, msg = submit.import_cookies(driver, args.import_cookies)
                        status = "OK" if ok else "WARN"
                        print(f"[{_now_iso()}] Cookie import {status}: {msg}")

                    submit.ensure_logged_in(driver, check_url=search_url)

                    if submit.is_human_verification_page(driver):
                        reason = "Human verification/CAPTCHA page detected; manual intervention required"
                        print(f"[{_now_iso()}] {reason} | {search_url}")
                        _append_failure(
                            args.failures_file,
                            {
                                "timestamp": _now_iso(),
                                "search_url": search_url,
                                "listing_url": "",
                                "reason": reason,
                            },
                        )
                        continue

                    if args.export_cookies:
                        submit.export_cookies(driver, args.export_cookies)
                        print(f"[{_now_iso()}] Session cookies exported to: {args.export_cookies}")

                    print(f"[{_now_iso()}] Reading advert count for search: {search_url}")
                    current_urls = submit.extract_listing_links(driver, search_url)
                    if submit.is_human_verification_page(driver):
                        reason = "Human verification/CAPTCHA page detected while loading search results"
                        print(f"[{_now_iso()}] {reason} | {search_url}")
                        _append_failure(
                            args.failures_file,
                            {
                                "timestamp": _now_iso(),
                                "search_url": search_url,
                                "listing_url": "",
                                "reason": reason,
                            },
                        )
                        continue
                    print(
                        f"[{_now_iso()}] Search total listings: {len(current_urls)} | {search_url}"
                    )

                    existing = set(state.get(search_url, []))

                    if not existing and search_url not in state and not args.initial_send_existing:
                        state[search_url] = sorted(current_urls)
                        print(
                            f"[{_now_iso()}] Baseline created for search ({len(current_urls)} listings tracked): {search_url}"
                        )
                        continue

                    new_urls = sorted(current_urls - existing)
                    if not new_urls:
                        print(f"[{_now_iso()}] No new listings for search: {search_url}")
                        state[search_url] = sorted(current_urls | existing)
                        continue

                    print(
                        f"[{_now_iso()}] {len(new_urls)} new listing(s) found for search: {search_url}"
                    )
                    if args.dry_run:
                        for listing_url in new_urls:
                            print(f"[{_now_iso()}] DRY-RUN would send message to: {listing_url}")
                        state[search_url] = sorted(current_urls | existing)
                        continue

                    for listing_url in new_urls:
                        success, detail = submit.send_message_to_listing(
                            driver=driver,
                            listing_url=listing_url,
                            message=message_text,
                        )
                        if success:
                            print(f"[{_now_iso()}] SENT: {listing_url}")
                            _append_sent(
                                args.sent_file,
                                {
                                    "timestamp": _now_iso(),
                                    "search_url": search_url,
                                    "listing_url": listing_url,
                                },
                            )
                        else:
                            print(f"[{_now_iso()}] FAILED: {listing_url} | {detail}")
                            _append_failure(
                                args.failures_file,
                                {
                                    "timestamp": _now_iso(),
                                    "search_url": search_url,
                                    "listing_url": listing_url,
                                    "reason": detail,
                                },
                            )

                    state[search_url] = sorted(current_urls | existing)

                except Exception as exc:
                    print(f"[{_now_iso()}] Failed processing search {search_url}: {exc}")
                finally:
                    if driver is not None:
                        driver.quit()
                        print(f"[{_now_iso()}] Browser session closed for search.")

            _save_state(args.state_file, state)
            print(f"[{_now_iso()}] Cycle complete. Monitoring continues.")
            _sleep_with_countdown(args.interval)

    except KeyboardInterrupt:
        _save_state(args.state_file, state)
        print(f"[{_now_iso()}] Stopped by user. State saved to {args.state_file}.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
