"""
helpers.py — Utility functions untuk IDX AI Trading Assistant.
"""

import time
import urllib.parse
from datetime import datetime, timedelta
from curl_cffi import requests
from requests.models import PreparedRequest
from loguru import logger
from config.settings import YFINANCE_TICKER_SUFFIX, ARB_LIMIT, get_ara_limit


class CfProxySession(requests.Session):
    """
    Session khusus untuk mem-bypass pemblokiran Yahoo Finance di Data Center.
    Semua request yang mengarah ke yahoo.com akan dibelokkan melalui
    Cloudflare Worker Proxy (milik user).
    Cookie keamanan dicegat secara manual untuk mempertahankan autentikasi.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.manual_cookie = None

    def request(self, method, url, *args, **kwargs):
        is_yahoo = "yahoo.com" in url
        if is_yahoo:
            # Reconstruct URL agar query parameters ikut terbawa ke Cloudflare
            params = kwargs.pop('params', None)
            if params:
                req = PreparedRequest()
                req.prepare_url(url, params)
                url = req.url
                
            # Sisipkan Cookie Yahoo secara manual karena curl_cffi nge-drop
            # cookie antar domain yang berbeda (workers.dev != yahoo.com)
            headers = kwargs.get('headers', {})
            if self.manual_cookie:
                headers['Cookie'] = self.manual_cookie
                
            kwargs['headers'] = headers
                
            # Proxy forwarding
            proxy_url = "https://yahoo-proxy.ditoaryap-work.workers.dev/?url="
            url = f"{proxy_url}{urllib.parse.quote(url)}"
        
        resp = super().request(method, url, *args, **kwargs)
        
        # Ekstrak 'set-cookie' dari respon Cloudflare untuk request berikutnya
        if is_yahoo:
            set_cookie = resp.headers.get('set-cookie') or resp.headers.get('Set-Cookie')
            if set_cookie:
                # Cukup ambil format id utama (B=123xyz;)
                self.manual_cookie = set_cookie.split(';')[0]
                
        return resp

def get_yf_session():
    """Mendapatkan curl_cffi session yang sudah di-wrap dengan Cloudflare Proxy"""
    session = CfProxySession(impersonate="chrome120")
    
    # 1. Pancing cookie dari halaman utama Yahoo
    session.get("https://finance.yahoo.com")
    
    # 2. Pancing Crumb 
    session.get("https://query1.finance.yahoo.com/v1/test/getcrumb")
    
    return session


def to_yf_ticker(kode: str) -> str:
    """Konversi kode saham IDX ke format yfinance (e.g. BBCA → BBCA.JK)."""
    kode = kode.upper().strip()
    if not kode.endswith(YFINANCE_TICKER_SUFFIX):
        return kode + YFINANCE_TICKER_SUFFIX
    return kode


def from_yf_ticker(ticker: str) -> str:
    """Konversi ticker yfinance ke kode IDX (e.g. BBCA.JK → BBCA)."""
    return ticker.replace(YFINANCE_TICKER_SUFFIX, "").upper().strip()


def is_within_auto_rejection(change_pct: float, price: float) -> bool:
    """
    Cek apakah perubahan harga masih dalam batas auto rejection.
    Returns True jika masih dalam batas (normal), False jika kena AR.
    """
    ara = get_ara_limit(price)
    return ARB_LIMIT <= change_pct <= ara


def format_rupiah(value: float) -> str:
    """Format angka ke format Rupiah (e.g. 1_500_000 → Rp 1.500.000)."""
    if value >= 1e12:
        return f"Rp {value/1e12:.1f}T"
    elif value >= 1e9:
        return f"Rp {value/1e9:.1f}M"
    elif value >= 1e6:
        return f"Rp {value/1e6:.1f}Jt"
    else:
        return f"Rp {value:,.0f}"


def batch_list(items: list, batch_size: int) -> list:
    """Pecah list menjadi batch-batch kecil."""
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


def is_trading_day(dt: datetime = None) -> bool:
    """Cek apakah hari ini adalah hari bursa (Senin-Jumat, bukan libur)."""
    if dt is None:
        dt = datetime.now()
    # Sabtu = 5, Minggu = 6
    return dt.weekday() < 5


def delay(seconds: float = 0.5):
    """Simple delay untuk rate limiting."""
    time.sleep(seconds)
