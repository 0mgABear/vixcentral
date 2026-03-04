import time
import requests

url = "http://vixcentral.com/ajax_update"
params = {"_": int(time.time() * 1000)}

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://vixcentral.com/",
}

data = requests.get(url, params=params, headers=headers, timeout=30).json()

last = data[2]          # "Last" curve
f1 = float(last[0])
f2 = float(last[1])

contango = (f2 / f1 - 1.0) * 100.0

print("F1:", f1)
print("F2:", f2)
print("Contango(1):", f"{contango:.2f}%")