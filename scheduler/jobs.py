"""
scheduler/jobs.py — n8n-compatible CLI entrypoints.

Dirancang untuk dipanggil via n8n Execute Command node atau crontab.
Setiap fungsi adalah satu "job" yang bisa dijadwalkan.

Jadwal (sesuai master prompt):
  16:30 WIB (Senin-Jumat) → fetch_daily_data
  Setiap 2 jam (06-22)    → fetch_news_and_sentiment
  06:30 WIB (Senin-Jumat) → generate_morning_briefing
  12:00 WIB               → update_midday
  15:55 WIB               → generate_afternoon_signal (BSJP)
  08:00 SENIN              → weekly_review
  22:00 Setiap Hari        → fetch_fundamentals
"""

import sys
import argparse
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loguru import logger
from data.database import db


def fetch_daily_data():
    """Jam 16:30 — Ambil OHLCV hari ini setelah bursa tutup."""
    logger.info("📊 JOB: Fetch Daily OHLCV Data")
    from data.fetcher.stock_fetcher import fetch_and_save_batch
    # Untuk saat ini gunakan TEST_STOCKS, nanti expand
    from config.settings import TEST_STOCKS
    stocks = TEST_STOCKS

    fetch_and_save_batch(stocks)
    logger.info("✅ Daily data fetch selesai")


def fetch_news_and_sentiment():
    """Setiap 2 jam — Ambil berita baru + proses sentimen AI."""
    logger.info("📰 JOB: Fetch News + Sentiment")
    from data.fetcher.news_fetcher import fetch_all_news, save_articles_to_db
    from ai.sentiment import process_unprocessed_news

    articles = fetch_all_news()
    save_articles_to_db(articles)
    process_unprocessed_news(limit=20)
    logger.info("✅ News + sentiment selesai")


def fetch_macro():
    """Jam 06:30 — Ambil data indeks Asia + komoditas."""
    logger.info("🌏 JOB: Fetch Macro Data")
    from data.fetcher.macro_fetcher import fetch_and_save_macro
    fetch_and_save_macro()
    logger.info("✅ Macro data fetch selesai")


def generate_morning_briefing():
    """Jam 07:00 — Generate full analysis + kirim ke Telegram."""
    logger.info("🌅 JOB: Morning Briefing")
    from ai.agents import run_full_analysis, format_full_report
    from config.settings import TEST_STOCKS

    fetch_macro()  # Ambil data makro dulu

    result = run_full_analysis(TEST_STOCKS)
    report = format_full_report(result)

    # TODO: Kirim ke Telegram (Fase 5)
    print(report)
    logger.info("✅ Morning briefing generated")
    return report


def update_midday():
    """Jam 12:00 — Update harga + status sinyal pagi."""
    logger.info("☀️ JOB: Midday Update")
    # TODO: implement di Fase 5
    logger.info("✅ Midday update selesai")


def generate_afternoon_signal():
    """Jam 15:55 — Sinyal BSJP (Beli Sore Jual Pagi)."""
    logger.info("🌆 JOB: Afternoon BSJP Signal")
    from ai.agents import run_full_analysis, format_full_report
    from config.settings import TEST_STOCKS

    result = run_full_analysis(TEST_STOCKS)
    report = format_full_report(result)

    # TODO: Kirim ke Telegram (Fase 5)
    print(report)
    logger.info("✅ Afternoon BSJP signal generated")
    return report


def fetch_fundamentals():
    """Jam 22:00 — Update laporan keuangan terbaru."""
    logger.info("📈 JOB: Fetch Fundamentals")
    from data.fetcher.fundamental_fetcher import fetch_and_save_fundamentals
    from config.settings import TEST_STOCKS

    fetch_and_save_fundamentals(TEST_STOCKS)
    logger.info("✅ Fundamental fetch selesai")


def weekly_review():
    """Senin 08:00 — Laporan mingguan."""
    logger.info("📋 JOB: Weekly Review")
    # TODO: AI weekly review + kirim Telegram
    logger.info("✅ Weekly review selesai")


# ═══════════════════════════════════════════════════════
# CLI ENTRY POINT — untuk n8n Execute Command
# ═══════════════════════════════════════════════════════

JOBS = {
    'fetch_daily': fetch_daily_data,
    'fetch_news': fetch_news_and_sentiment,
    'fetch_macro': fetch_macro,
    'briefing': generate_morning_briefing,
    'midday': update_midday,
    'afternoon': generate_afternoon_signal,
    'fundamentals': fetch_fundamentals,
    'weekly': weekly_review,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IDX Trading Assistant — Scheduler Jobs")
    parser.add_argument('job', choices=list(JOBS.keys()), help='Job to run')
    args = parser.parse_args()

    db.create_all_tables()
    JOBS[args.job]()
