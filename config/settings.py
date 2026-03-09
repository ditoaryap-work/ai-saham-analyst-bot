"""
settings.py — Konfigurasi sistem IDX AI Trading Assistant.
Memuat semua variabel dari file .env dan menyediakan
konstanta default untuk seluruh modul.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Lokasi file ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / "config" / ".env"
load_dotenv(ENV_PATH)

# ── Telegram ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── OpenRouter / AI ──────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-v3.2")

# ── Database ─────────────────────────────────────────────
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "database.sqlite"))

# ── Portfolio ────────────────────────────────────────────
MODAL_AWAL = float(os.getenv("MODAL_AWAL", "10000000"))
RISK_PROFILE = os.getenv("RISK_PROFILE", "moderate")
MAX_POSISI = int(os.getenv("MAX_POSISI", "5"))
MAX_PER_SAHAM_PCT = float(os.getenv("MAX_PER_SAHAM_PCT", "0.30"))

# ── yfinance ─────────────────────────────────────────────
YFINANCE_DELAY = float(os.getenv("YFINANCE_DELAY", "0.5"))
YFINANCE_BATCH_SIZE = int(os.getenv("YFINANCE_BATCH_SIZE", "50"))
YFINANCE_TICKER_SUFFIX = ".JK"  # Suffix JSX di Yahoo Finance

# ── Logging ──────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
VPS_TIMEZONE = os.getenv("VPS_TIMEZONE", "Asia/Jakarta")

# ── Saham Test (Bisa diubah via .env) ───────────────────
_env_stocks = os.getenv("TEST_STOCKS", "BBCA,TLKM,BMRI,ASII,UNVR")
TEST_STOCKS = [s.strip() for s in _env_stocks.split(",") if s.strip()]

# ── Trading Rules IDX (per April 2025) ───────────────────
# Auto Rejection Buy (ARB): flat -15%
ARB_LIMIT = -0.15

# Auto Rejection Sell (ARA): berjenjang berdasarkan harga
def get_ara_limit(price: float) -> float:
    """Hitung batas ARA berdasarkan harga saham."""
    if price < 200:
        return 0.35   # 35% untuk harga < Rp 200
    elif price < 5000:
        return 0.25   # 25% untuk harga Rp 200 - Rp 4.999
    else:
        return 0.20   # 20% untuk harga >= Rp 5.000

# ── Jam Bursa ────────────────────────────────────────────
TRADING_HOURS = {
    "senin_kamis": {
        "sesi_1": ("09:00", "12:00"),
        "sesi_2": ("13:30", "15:49"),
    },
    "jumat": {
        "sesi_1": ("09:00", "11:30"),
        "sesi_2": ("14:00", "15:49"),
    },
}

# ── Scheduler Timing ─────────────────────────────────────
SCHEDULE = {
    "fetch_ohlcv": "16:30",
    "fetch_fundamental": "22:00",
    "briefing_pagi": "06:30",
    "update_siang": "12:00",
    "sinyal_sore": "15:55",
    "kirim_sore": "16:15",
    "review_mingguan": "senin 08:00",
    "backup_db": "senin 09:00",
}

# ── RSS Feeds ────────────────────────────────────────────
RSS_FEEDS = [
    "https://www.cnbcindonesia.com/market/rss",
    "https://investasi.kontan.co.id/rss",
    "https://finance.detik.com/rss",
]

# ── Indeks & Komoditas (yfinance tickers) ────────────────
MACRO_TICKERS = {
    "IHSG": "^JKSE",
    "Nikkei": "^N225",
    "Hang Seng": "^HSI",
    "STI": "^STI",
    "Gold": "GC=F",
    "Crude Oil": "CL=F",
}
