from __future__ import annotations

import json
import os
import re
import time
from typing import Iterable, Optional, Set, Tuple
from urllib.parse import urljoin

from selenium import webdriver
from selenium.common.exceptions import (
    SessionNotCreatedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = "https://www.immobilienscout24.de"


def create_driver(
    browser: str = "chrome",
    headless: bool = False,
    driver_path: Optional[str] = None,
    user_data_dir: Optional[str] = None,
    profile_directory: Optional[str] = None,
    firefox_profile: Optional[str] = None,
) -> WebDriver:
    selected_browser = browser.strip().lower()
    if selected_browser not in {"chrome", "firefox"}:
        raise ValueError("Unsupported browser. Use 'chrome' or 'firefox'.")

    if selected_browser == "chrome":
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--remote-debugging-port=0")
        options.add_argument("--window-size=1400,1200")
        if headless:
            options.add_argument("--headless=new")
        if user_data_dir:
            options.add_argument(f"--user-data-dir={user_data_dir}")
        if profile_directory:
            options.add_argument(f"--profile-directory={profile_directory}")

        try:
            if driver_path:
                service = ChromeService(executable_path=driver_path)
                return webdriver.Chrome(service=service, options=options)
            return webdriver.Chrome(options=options)
        except SessionNotCreatedException as exc:
            message = str(exc)
            if "DevToolsActivePort file doesn't exist" in message:
                raise RuntimeError(
                    "Chrome failed to start. If you use --user-data-dir/--profile-directory, "
                    "the selected profile is likely locked by another Chrome process. "
                    "Close all Chrome windows/processes and retry, or run without profile args "
                    "for a clean temporary profile."
                ) from exc
            raise

    if user_data_dir or profile_directory:
        raise ValueError(
            "--user-data-dir and --profile-directory are Chrome-only options. "
            "For Firefox use --firefox-profile."
        )

    options = webdriver.FirefoxOptions()
    if headless:
        options.add_argument("-headless")
    if firefox_profile:
        normalized_profile = os.path.expanduser(firefox_profile.strip())
        if "YOUR_PROFILE" in normalized_profile:
            raise ValueError(
                "--firefox-profile still contains placeholder text 'YOUR_PROFILE'. "
                "Replace it with your real Firefox profile directory path."
            )
        if not os.path.isdir(normalized_profile):
            raise ValueError(
                f"Firefox profile directory does not exist: {normalized_profile}"
            )
        options.add_argument("-profile")
        options.add_argument(normalized_profile)

    try:
        if driver_path:
            service = FirefoxService(executable_path=driver_path)
            return webdriver.Firefox(service=service, options=options)
        return webdriver.Firefox(options=options)
    except WebDriverException as exc:
        raise RuntimeError(
            "Firefox failed to start. Ensure Firefox is installed and geckodriver is available "
            "(or pass --driver-path to geckodriver). If using --firefox-profile, verify the path "
            "exists and is not locked by another running Firefox process."
        ) from exc


def _dismiss_overlays(driver: WebDriver) -> None:
    candidates = [
        "//button[contains(., 'Accept all')]",
        "//button[contains(., 'Alle akzeptieren')]",
        "//button[contains(., 'Zustimmen')]",
        "//button[contains(., 'Einverstanden')]",
        "//button[contains(., 'OK')]",
    ]
    for xpath in candidates:
        try:
            button = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            button.click()
            time.sleep(0.5)
        except Exception:
            continue


def is_human_verification_page(driver: WebDriver) -> bool:
    url = (driver.current_url or "").lower()
    if any(token in url for token in ["captcha", "challenge", "verify", "robot"]):
        return True

    source = (driver.page_source or "").lower()
    indicators = [
        "captcha",
        "sicherheitsüberprüfung",
        "sicherheitspr",
        "human verification",
        "ich bin kein roboter",
        "bist du ein mensch",
        "are you human",
    ]
    return any(token in source for token in indicators)


def ensure_logged_in(driver: WebDriver, check_url: Optional[str] = None) -> None:
    target = check_url or f"{BASE_URL}/savedsearch/myscout/manage/"
    driver.get(target)
    _dismiss_overlays(driver)
    if "/mein-konto/" in driver.current_url or "login" in driver.current_url.lower():
        input(
            "Please log in to Immobilienscout24 in the opened browser, then press ENTER here to continue..."
        )


def export_cookies(driver: WebDriver, cookie_file: str) -> None:
    cookies = driver.get_cookies()
    with open(cookie_file, "w", encoding="utf-8") as handle:
        json.dump(cookies, handle, ensure_ascii=False, indent=2)


def import_cookies(driver: WebDriver, cookie_file: str) -> Tuple[bool, str]:
    if not os.path.isfile(cookie_file):
        return False, f"Cookie file not found: {cookie_file}"

    with open(cookie_file, "r", encoding="utf-8") as handle:
        cookies = json.load(handle)

    if not isinstance(cookies, list):
        return False, "Cookie file format is invalid (expected list)"

    driver.get(BASE_URL)
    _dismiss_overlays(driver)

    imported = 0
    skipped = 0
    for cookie in cookies:
        if not isinstance(cookie, dict):
            skipped += 1
            continue
        item = dict(cookie)
        item.pop("sameSite", None)
        if item.get("expiry") is None:
            item.pop("expiry", None)
        try:
            driver.add_cookie(item)
            imported += 1
        except Exception:
            skipped += 1

    driver.get(f"{BASE_URL}/savedsearch/myscout/manage/")
    _dismiss_overlays(driver)

    if "/mein-konto/" in driver.current_url or "login" in driver.current_url.lower():
        return False, (
            f"Imported {imported} cookies (skipped {skipped}), but session is still not logged in"
        )
    return True, f"Imported {imported} cookies (skipped {skipped})"


def _find_expose_urls(html: str) -> Set[str]:
    matches = set(re.findall(r"/expose/\d+", html))
    return {urljoin(BASE_URL, match) for match in matches}


def extract_listing_links(driver: WebDriver, search_url: str) -> Set[str]:
    driver.get(search_url)
    _dismiss_overlays(driver)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(2)

    expose_links = _find_expose_urls(driver.page_source)
    if expose_links:
        return expose_links

    hrefs = driver.find_elements(By.XPATH, "//a[contains(@href,'/expose/')]")
    urls = set()
    for element in hrefs:
        href = element.get_attribute("href")
        if href and "/expose/" in href:
            urls.add(href.split("?")[0])
    return urls


def _find_clickable(driver: WebDriver, xpaths: Iterable[str], timeout: int = 6):
    for xpath in xpaths:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
        except Exception:
            continue
    return None


def _open_contact_form(driver: WebDriver) -> bool:
    cta_xpaths = [
        "//button[contains(., 'Nachricht')]",
        "//a[contains(., 'Nachricht')]",
        "//button[contains(., 'Interesse bekunden')]",
        "//a[contains(., 'Interesse bekunden')]",
        "//button[contains(., 'Anbieter kontaktieren')]",
        "//a[contains(., 'Anbieter kontaktieren')]",
    ]
    button = _find_clickable(driver, cta_xpaths, timeout=5)
    if not button:
        return False
    button.click()
    return True


def _find_message_box(driver: WebDriver):
    textarea_xpaths = [
        "//textarea[contains(@id,'message') or contains(@id,'Message')]",
        "//textarea[contains(@name,'message') or contains(@name,'Message')]",
        "//textarea[contains(@placeholder,'Nachricht')]",
        "//textarea",
    ]
    for xpath in textarea_xpaths:
        try:
            return WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
        except Exception:
            continue
    return None


def send_message_to_listing(driver: WebDriver, listing_url: str, message: str) -> Tuple[bool, str]:
    driver.get(listing_url)
    _dismiss_overlays(driver)

    if not _open_contact_form(driver):
        contact_url = listing_url.rstrip("/") + "#/basicContact/email"
        driver.get(contact_url)

    message_box = _find_message_box(driver)
    if not message_box:
        return False, "Could not locate message input area"

    try:
        message_box.clear()
    except Exception:
        pass
    message_box.send_keys(message)

    send_xpaths = [
        "//button[contains(., 'Nachricht senden')]",
        "//button[contains(., 'Anfrage senden')]",
        "//button[contains(., 'Senden')]",
        "//button[contains(., 'Interesse bekunden')]",
        "//button[@type='submit']",
    ]
    send_button = _find_clickable(driver, send_xpaths, timeout=8)
    if not send_button:
        return False, "Could not locate submit/send button"

    try:
        send_button.click()
    except TimeoutException:
        return False, "Timed out while trying to submit"
    except Exception as exc:
        return False, f"Submit click failed: {exc}"

    return True, "Message sent"


def submit_app(ref: str) -> Tuple[bool, str]:
    driver = create_driver()
    try:
        ensure_logged_in(driver)
        url = ref if ref.startswith("http") else urljoin(BASE_URL, ref)
        return False, (
            "submit_app(ref) is deprecated for Immoscout24. "
            "Use send_message_to_listing(driver, listing_url, message)."
        )
    finally:
        driver.quit()
