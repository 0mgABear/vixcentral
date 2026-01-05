import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load local .env if present (safe in GitHub Actions too)
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

URL = "http://vixcentral.com/"
DATA_PATH = Path(__file__).with_name("data.json")


def is_weekday(d):
    return d.weekday() < 5  # Mon–Fri


def fmt_date_iso_to_pretty(iso_str):
    # iso_str like "2026-01-05" -> "05 Jan 2026"
    return date.fromisoformat(iso_str).strftime("%d %b %Y")


def tg_send(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHANNEL_ID")

    if not token or not chat_id:
        print("Telegram secrets not set; skipping send.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,  # can be @channel_handle or numeric id (-100...)
            "text": msg,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def load_data():
    if not DATA_PATH.exists():
        return []
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def save_data(data):
    DATA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def scrape_contango_once():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            }
        )

        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_selector("#basicTable", timeout=90000)

        # Wait until % Contango section has at least one % cell populated
        page.wait_for_selector(
            'xpath=//*[@id="basicTable"]//th[normalize-space(.)="% Contango"]'
            '/following::td[contains(normalize-space(.), "%")]',
            timeout=90000,
        )

        # Locate the "1" cell value after % Contango and pick the first match
        cell = page.locator(
            'xpath=//*[@id="basicTable"]//th[normalize-space(.)="% Contango"]'
            '/following::th[normalize-space(.)="1"]/following-sibling::td[1]'
        ).first

        text = cell.inner_text().strip()
        browser.close()

    m = re.search(r"(-?\d+(\.\d+)?)\s*%", text)
    if not m:
        raise RuntimeError(f"Unexpected contango format: {text!r}")

    val = float(m.group(1))

    # Sanity bounds: adjust if you want, but prevents storing nonsense on DOM changes
    if val < -80 or val > 200:
        raise RuntimeError(f"Scraped contango out of range: {val} (raw: {text!r})")

    return val


def scrape_contango():
    last_err = None
    for attempt in range(1, 4):  # 3 attempts
        try:
            return scrape_contango_once()
        except Exception as e:
            last_err = e
            print(f"Scrape attempt {attempt} failed: {e}")
            time.sleep(attempt)  # backoff: 1s, 2s, 3s
    raise last_err


def main():
    today = date.today()

    if not is_weekday(today):
        print("Weekend; skipping.")
        return

    # Store ISO internally for correctness; display pretty in Telegram
    today_iso = today.isoformat()          # e.g., "2026-01-05"
    today_pretty = today.strftime("%d %b %Y")  # e.g., "05 Jan 2026"

    data = load_data()

    # Avoid double run same day (ISO-based)
    if data and data[-1].get("d") == today_iso:
        return

    value = scrape_contango()

    # Daily Update (pretty date)
    tg_send(f"{today_pretty} contango: {value:.2f}%")

    prev = data[-1] if data else None

    # Keep only 5 records (store ISO date)
    data.append({"d": today_iso, "value": value})
    data = data[-5:]
    save_data(data)

    # 40% Drop Alert (separate message)
    if prev:
        prev_val = prev.get("value")
        if isinstance(prev_val, (int, float)) and prev_val > 0:
            drop = (prev_val - value) / prev_val
            if drop >= 0.40:
                msg = f"{today_pretty} ⚠️ >40% drop: {prev_val:.2f}% → {value:.2f}% ({drop*100:.1f}%)"
                tg_send(msg)

    # 5 Consecutive Days Drop Alert (separate message)
    if len(data) == 5:
        vals = [x.get("value") for x in data]
        if all(isinstance(v, (int, float)) for v in vals) and all(
            vals[i] < vals[i - 1] for i in range(1, 5)
        ):
            lines = "\n".join(
                f'{fmt_date_iso_to_pretty(x["d"])}: {x["value"]:.2f}%'
                for x in data
            )
            msg = f"{today_pretty} ⚠️ 5 consecutive Trading Day drops:\n{lines}"
            tg_send(msg)


if __name__ == "__main__":
    main()
