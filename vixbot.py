import json
import os
import time
import requests
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

url = "http://vixcentral.com/ajax_update"
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
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "http://vixcentral.com/",
    }

    r = requests.get(
        url,
        params={"_": int(time.time() * 1000)},
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()

    data = r.json()

    last = data[2]

    if not isinstance(last, list) or len(last) < 2:
        raise RuntimeError(f"Unexpected ajax_update format: {last!r}")

    f1 = float(last[0])
    f2 = float(last[1])

    val = (f2 / f1 - 1.0) * 100.0

    if val < -80 or val > 200:
        raise RuntimeError(f"Contango out of range: {val}")

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
