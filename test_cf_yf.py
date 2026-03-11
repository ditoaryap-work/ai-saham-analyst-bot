import yfinance as yf
import urllib.parse
from curl_cffi import requests
from requests.models import PreparedRequest

class CfProxySession(requests.Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.manual_cookie = None

    def request(self, method, url, *args, **kwargs):
        is_yahoo = "yahoo.com" in url
        if is_yahoo:
            params = kwargs.pop('params', None)
            if params:
                req = PreparedRequest()
                req.prepare_url(url, params)
                url = req.url
                
            headers = kwargs.get('headers', {})
            if self.manual_cookie:
                headers['Cookie'] = self.manual_cookie
                
            kwargs['headers'] = headers
                
            url = f"https://yahoo-proxy.ditoaryap-work.workers.dev/?url={urllib.parse.quote(url)}"
        
        resp = super().request(method, url, *args, **kwargs)
        
        if is_yahoo:
            # Manually extract the set-cookie header
            # curl_cffi might have it in headers or cookies
            set_cookie = resp.headers.get('set-cookie') or resp.headers.get('Set-Cookie')
            if set_cookie:
                # Basic parsing to just get the 'B=123xyz;' part
                self.manual_cookie = set_cookie.split(';')[0]
                
        return resp

try:
    s = CfProxySession(impersonate="chrome120")
    print("Testing CF Proxy cookie extraction...")
    
    # Trigger cookie creation
    s.get("https://finance.yahoo.com")
    
    # Trigger crumb creation
    res = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb")
    print("Manual Crumb:", res.text)
    
    ticker = yf.Ticker("BBCA.JK", session=s)
    
    print("\nInfo:")
    print(ticker.info.get('longName'))
    
    print("\nHistory:")
    print(ticker.history(period="1d"))
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()
