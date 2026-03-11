import requests
import json

api_key = "demo" # FMP allows 'demo' key for AAPL, but let's see if we can query the endpoint format

urls = [
    "https://financialmodelingprep.com/api/v3/profile/BBCA.JK?apikey=demo",
    "https://financialmodelingprep.com/api/v3/historical-price-full/BBCA.JK?apikey=demo"
]
for u in urls:
    r = requests.get(u)
    print(f"URL: {u.split('?')[0]}")
    print(f"Status: {r.status_code}")
    print(str(r.text)[:150])
