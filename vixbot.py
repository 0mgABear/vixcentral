import json
import os
import re
import time
import requests
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

URL = "http://vixcentral.com/"
DATA_PATH = Path(__file__).with_name("data.json")


def fmt_date_iso(iso_str):
    return date.fromisoformat(iso_str).strftime("%d %b %Y")


def tg_send(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHANNEL_ID")

    if not token or not chat_id:
        raise RuntimeError("Telegram secrets not set")

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": msg,
        "disable_web_page_preview": "true",
    }

    r = requests.post(url, data=payload, timeout=20)
    r.raise_for_status()

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

        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_selector("#basicTable", timeout=90000)

        page.wait_for_selector(
            'xpath=//*[@id="basicTable"]//th[normalize-space(.)="% Contango"]'
            '/following::td[contains(normalize-space(.), "%")]',
            timeout=90000,
        )

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

    if val < -80 or val > 200:
        raise RuntimeError(f"Scraped contango out of range: {val} (raw: {text!r})")

    return val


def scrape_contango():
    last_err = None
    for attempt in range(1, 4):
        try:
            return scrape_contango_once()
        except Exception as e:
            last_err = e
            time.sleep(attempt)
    raise last_err


def main():
    today = date.today()

    today_iso = today.isoformat()          
    today_disp = today.strftime("%d %b %Y") 

    data = load_data()

    if data and data[-1].get("d") == today_iso:
        return

    value = scrape_contango()

    tg_send(f"{today_disp} contango: {value:.2f}%")

    prev = data[-1] if data else None

    data.append({"d": today_iso, "value": value})
    data = data[-5:]
    save_data(data)

    if prev:
        prev_val = prev.get("value")
        if prev_val and prev_val > 0:
            drop = (prev_val - value) / prev_val
            if drop >= 0.40:
                msg = (
                    f"{today_disp} ⚠️ >40% drop: "
                    f"{prev_val:.2f}% → {value:.2f}% ({drop*100:.1f}%)"
                )
                tg_send(msg)

    if len(data) == 5:
        vals = [x.get("value") for x in data]
        if all(vals[i] < vals[i - 1] for i in range(1, 5)):
            lines = "\n".join(
                f'{fmt_date_iso(x["d"])}: {x["value"]:.2f}%'
                for x in data
            )
            msg = f"{today_disp} ⚠️ 5 consecutive Trading Day drops:\n{lines}"
            tg_send(msg)


if __name__ == "__main__":
    main()
