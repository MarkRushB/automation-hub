#!/usr/bin/env python3
"""Monitor Massachusetts ReserveAmerica campsite availability."""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import smtplib
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from playwright.sync_api import Page, sync_playwright


HOME = "https://massdcrcamping.reserveamerica.com/unifSearch.do?tti=Home"
SITE_TYPES = {
    "any": "",
    "rv": "2001",
    "lodging": "10001",
    "tent": "2003",
    "trailer": "2002",
    "group": "9002",
    "horse": "3001",
}


class RateLimitedError(RuntimeError):
    """The site appears to be rate-limiting or challenging this client."""


BLOCK_PAGE_PHRASES = (
    "too many requests",
    "access denied",
    "temporarily blocked",
    "unusual traffic",
    "verify you are human",
    "security check",
    "captcha",
)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    required = ("campground", "arrival", "nights")
    missing = [key for key in required if not cfg.get(key)]
    if missing:
        raise ValueError(f"Missing configuration: {', '.join(missing)}")
    datetime.strptime(cfg["arrival"], "%Y-%m-%d")
    if cfg.get("site_type", "any") not in SITE_TYPES:
        raise ValueError(f"site_type must be one of: {', '.join(SITE_TYPES)}")
    return cfg


def set_search_fields(page: Page, cfg: dict) -> None:
    response = page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
    if response and response.status in (403, 429):
        raise RateLimitedError(f"ReserveAmerica returned HTTP {response.status}")
    page.locator('select[name="interest"]').select_option("camping")
    page.locator('select[name="lookingFor"]').select_option(
        SITE_TYPES[cfg.get("site_type", "any")]
    )
    page.locator('input[name="locationCriteria"]').fill(cfg["campground"])
    page.locator('input[name="locationPosition"]').evaluate("el => el.value = ''")

    date_value = datetime.strptime(cfg["arrival"], "%Y-%m-%d").strftime("%m/%d/%Y")
    arrival = page.locator('input[name="campingDate"]')
    arrival.fill(date_value)
    arrival.evaluate("el => el.dispatchEvent(new Event('change', {bubbles:true}))")

    nights = page.locator('input[name="lengthOfStay"]')
    nights.evaluate("el => el.disabled = false")
    nights.fill(str(int(cfg["nights"])))


def ensure_not_blocked(page: Page) -> None:
    text = page.locator("body").inner_text(timeout=30_000).lower()
    match = next((phrase for phrase in BLOCK_PAGE_PHRASES if phrase in text), None)
    if match:
        raise RateLimitedError(f"Possible access restriction page detected: {match}")


def check_once(page: Page, cfg: dict) -> tuple[bool, str, str]:
    set_search_fields(page, cfg)
    ensure_not_blocked(page)
    search_name = cfg["campground"].rsplit(",", 1)[0].strip()
    page.get_by_role("button", name="Search").click()
    page.wait_for_load_state("domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2_000)
    ensure_not_blocked(page)

    if "unifSearchSuggestions.do" in page.url:
        suggestion = page.get_by_role("link", name=search_name, exact=False).first
        if not suggestion.is_visible():
            suggestion = page.get_by_text(search_name, exact=False).first
        if not suggestion.is_visible():
            raise RuntimeError(
                f"No search suggestion matched campground: {cfg['campground']}"
            )
        suggestion.click()
        page.wait_for_load_state("domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)
        ensure_not_blocked(page)

    booking_url = page.url
    book_link = page.get_by_role(
        "link", name=re.compile(re.escape(search_name) + r".*Book Sites", re.I)
    ).first
    if book_link.is_visible():
        href = book_link.get_attribute("href")
        if href:
            booking_url = urljoin(page.url, href)

    normalized = " ".join(page.locator("body").inner_text(timeout=30_000).split())
    wanted_sites = [str(x).strip() for x in cfg.get("sites", []) if str(x).strip()]
    count_match = re.search(r"\b(\d+)\s+matching sites? available\b", normalized, re.I)

    positive = cfg.get("available_text", ["Book Now", "Available", "View Details"])
    hits = [phrase for phrase in positive if phrase.lower() in normalized.lower()]

    if count_match:
        available_count = int(count_match.group(1))
        available = available_count > 0
        detail = f"matching sites available={available_count}"
    else:
        available = bool(hits)
        detail = f"availability labels={hits or 'none'}"

    if wanted_sites:
        site_hits = [s for s in wanted_sites if s.lower() in normalized.lower()]
        available = bool(available and site_hits)
        detail += f", matching sites={site_hits or 'none'}"

    negative = cfg.get(
        "unavailable_text",
        ["No availability", "No campsites available", "0 results found"],
    )
    negative_hits = [p for p in negative if p.lower() in normalized.lower()]
    if negative_hits:
        available = False
        detail += f", unavailable labels={negative_hits}"

    return available, detail, booking_url


def send_webhook(url: str, message: str) -> None:
    payload = json.dumps({"content": message, "text": message}).encode("utf-8")
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=20) as response:
        response.read()


def send_bark(cfg: dict, message: str, click_url: str) -> None:
    bark = cfg.get("bark") or {}
    if not bark.get("enabled"):
        return
    server = bark.get("server", "https://api.day.app").rstrip("/")
    device_key = os.getenv("BARK_DEVICE_KEY", str(bark.get("device_key", ""))).strip()
    if not device_key:
        raise ValueError("Bark is enabled, but BARK_DEVICE_KEY is empty")

    payload = {
        "device_key": device_key,
        "title": bark.get("title", "Campsite availability"),
        "body": message,
        "level": bark.get("level", "active"),
        "group": bark.get("group", "Camping"),
        "url": click_url,
    }
    if bark.get("sound"):
        payload["sound"] = bark["sound"]

    req = Request(
        f"{server}/push",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(req, timeout=20) as response:
        response.read()


def send_email(cfg: dict, message: str) -> None:
    email_cfg = cfg.get("email") or {}
    if not email_cfg.get("enabled"):
        return
    msg = EmailMessage()
    msg["Subject"] = email_cfg.get("subject", "Campsite availability found")
    msg["From"] = email_cfg["from"]
    msg["To"] = email_cfg["to"]
    msg.set_content(message)
    with smtplib.SMTP(email_cfg["smtp_host"], int(email_cfg.get("smtp_port", 587))) as smtp:
        smtp.starttls()
        smtp.login(email_cfg["username"], email_cfg["password"])
        smtp.send_message(msg)


def notify(cfg: dict, message: str, click_url: str) -> None:
    print("\a" + message, flush=True)
    send_bark(cfg, message, click_url)
    if cfg.get("webhook_url"):
        send_webhook(cfg["webhook_url"], message)
    send_email(cfg, message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor a Massachusetts campsite")
    parser.add_argument("-c", "--config", default="config.json")
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    parser.add_argument("--test-notification", action="store_true")
    args = parser.parse_args()
    cfg = load_config(args.config)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.test_notification:
        notify(cfg, "Campsite monitor test notification", HOME)
        logging.info("Test notification sent")
        return 0

    interval = max(300, int(cfg.get("check_interval_seconds", 900)))
    jitter = max(0, int(cfg.get("jitter_seconds", 120)))
    max_backoff = max(interval, int(cfg.get("max_backoff_seconds", 7200)))
    notified = False
    consecutive_failures = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        page = browser.new_page(locale="en-US")
        while True:
            try:
                available, detail, url = check_once(page, cfg)
                logging.info("available=%s; %s", available, detail)
                if available and not notified:
                    notify(
                        cfg,
                        f"Campsite may be available: {cfg['campground']}\n"
                        f"Arrival: {cfg['arrival']}, nights: {cfg['nights']}\n{url}",
                        url,
                    )
                    notified = True
                elif not available:
                    notified = False
                consecutive_failures = 0
            except RateLimitedError as exc:
                consecutive_failures += 1
                logging.warning("%s", exc)
                if args.once:
                    browser.close()
                    return 2
            except Exception:
                consecutive_failures += 1
                logging.exception("Availability check failed")
                if args.once:
                    browser.close()
                    return 2

            if args.once:
                break
            if consecutive_failures:
                delay = min(
                    max_backoff,
                    interval * (2 ** min(consecutive_failures - 1, 6)),
                )
                delay += random.randint(0, jitter)
                logging.warning(
                    "Backing off for %d seconds after %d consecutive failure(s)",
                    delay,
                    consecutive_failures,
                )
            else:
                delay = interval + random.randint(0, jitter)
            time.sleep(delay)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

