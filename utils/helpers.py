"""
helpers.py — Utility functions untuk IDX AI Trading Assistant.
"""

import time
from datetime import datetime, timedelta
from curl_cffi import requests as curl_requests
from config.settings import YFINANCE_TICKER_SUFFIX, ARB_LIMIT, get_ara_limit


def get_yf_session():
    """Returns a curl_cffi session that bypasses Cloudflare bot protection."""
    session = curl_requests.Session(impersonate="chrome110")
    # yfinance sometimes checks for 'headers' dict directly
    if hasattr(session, 'headers'):
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"})
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
