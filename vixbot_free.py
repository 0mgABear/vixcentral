import os
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

URL = "http://vixcentral.com/"

def is_weekday(d):
    return d.weekday() < 5

def tg_send(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHANNEL_ID") or os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram secrets not set; skipping send.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": msg,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def scrape_contango():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0 Safari/537.36"
        })

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#basicTable", timeout=60000)

        # Wait until % Contango values appear
        page.wait_for_selector(
            'xpath=//*[@id="basicTable"]//th[normalize-space(.)="% Contango"]'
            '/following::td[contains(normalize-space(.), "%")]',
            timeout=60000
        )

        cell = page.locator(
            'xpath=//*[@id="basicTable"]//th[normalize-space(.)="% Contango"]'
            '/following::th[normalize-space(.)="1"]/following-sibling::td[1]'
        ).first

        text = cell.inner_text().strip()
        browser.close()

    m = re.search(r"(-?\d+(\.\d+)?)%", text)
    if not m:
        raise RuntimeError(f"Unexpected contango format: {text}")

    return float(m.group(1))


def main():
    today = date.today()

    if not is_weekday(today):
        print("Weekend; skipping.")
        return

    value = scrape_contango()
    today_str = today.strftime("%d %b %Y")

    tg_send(f"{today_str} VIX Contango (Month 1): {value:.2f}%")


if __name__ == "__main__":
    main()
