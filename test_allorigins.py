import urllib.parse
from curl_cffi import requests
from yahooquery import Ticker

class AllOriginsSession(requests.Session):
    def request(self, method, url, *args, **kwargs):
        if "yahoo.com" in url:
            url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(url)}"
        # Disable redirects if any, or let allorigins handle it
        return super().request(method, url, *args, **kwargs)

try:
    s = AllOriginsSession(impersonate="chrome120")
    t = Ticker("BBCA.JK", session=s, asynchronous=False)
    print(t.price)
except Exception as e:
    print(e)
