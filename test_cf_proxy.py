import urllib.parse
from curl_cffi import requests
from yahooquery import Ticker

class ProxySession(requests.Session):
    def request(self, method, url, *args, **kwargs):
        if "yahoo.com" in url:
            url = f"https://yahoo-proxy.ditoaryap-work.workers.dev/?url={urllib.parse.quote(url)}"
        return super().request(method, url, *args, **kwargs)

try:
    print("Testing YahooQuery through CF proxy...")
    s = ProxySession(impersonate="chrome120")
    
    # We must fetch the crumb manually because yahooquery expects it on the yahoo.com domain
    s.get(f"https://yahoo-proxy.ditoaryap-work.workers.dev/?url={urllib.parse.quote('https://finance.yahoo.com')}")
    crumb_resp = s.get(f"https://yahoo-proxy.ditoaryap-work.workers.dev/?url={urllib.parse.quote('https://query2.finance.yahoo.com/v1/test/getcrumb')}")
    
    print("Crumb:", crumb_resp.text)
    
    # Test raw API fetch for price and history
    import json
    
    # History
    hist_url = f"https://yahoo-proxy.ditoaryap-work.workers.dev/?url={urllib.parse.quote('https://query2.finance.yahoo.com/v8/finance/chart/BBCA.JK?range=5d&interval=1d')}"
    hist_data = s.get(hist_url).json()
    print("History Result:", hist_data['chart']['error'])
    print("Has History Data?", 'result' in hist_data['chart'] and hist_data['chart']['result'] is not None)

except Exception as e:
    print("Error:", e)
