import urllib.parse
from curl_cffi import requests
from yahooquery import Ticker

class CorsSessionWrapper(requests.Session):
    def request(self, method, url, *args, **kwargs):
        if "yahoo.com" in url:
            # Bypass cloudflare by routing through corsproxy
            url = f"https://corsproxy.io/?url={urllib.parse.quote(url)}"
        return super().request(method, url, *args, **kwargs)

try:
    s = CorsSessionWrapper(impersonate="chrome120")
    t = Ticker("BBCA.JK", session=s, asynchronous=False)
    print(t.price)
except Exception as e:
    print(e)
