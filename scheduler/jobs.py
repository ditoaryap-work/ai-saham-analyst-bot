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
    """Jam 16:30 — Ambil OHLCV. Jika watchlist_harian kosong, ambil TEST_STOCKS."""
    logger.info("📊 JOB: Fetch Daily OHLCV Data")
    from data.fetcher.stock_fetcher import fetch_and_save_batch
    from config.settings import TEST_STOCKS
    
    # Ambil dari watchlist hari ini jika ada
    today = date.today().isoformat()
    rows = db.execute("SELECT kode FROM watchlist_harian WHERE tanggal = ?", (today,))
    if rows:
        stocks = [r['kode'] for r in rows]
        logger.info(f"Menggunakan {len(stocks)} saham dari watchlist_harian.")
    else:
        stocks = TEST_STOCKS
        logger.info(f"Watchlist kosong, menggunakan {len(stocks)} TEST_STOCKS.")

    fetch_and_save_batch(stocks)
    logger.info("✅ Daily data fetch selesai")


def fetch_full_market_scan():
    """JOB BARU: Scan 800+ saham untuk mencari Top 10."""
    logger.info("🚀 JOB: Full Market Scan (800+ Saham)")
    from data.fetcher.stock_fetcher import fetch_all_idx_tickers, fetch_and_save_batch
    from analysis.screening import run_full_screening
    
    # 1. Update list emiten
    all_tickers = fetch_all_idx_tickers()
    if not all_tickers:
        logger.error("Gagal mendapatkan daftar emiten. Aborting scan.")
        return
    
    # 2. Fetch OHLCV semua saham (Efisien: 1 batch)
    logger.info(f"Fetching OHLCV for {len(all_tickers)} stocks...")
    fetch_and_save_batch(all_tickers, include_info=False)
    
    # 3. Jalankan Screening Python
    results = run_full_screening(all_tickers)
    
    # 4. Sortir & Ambil Top 10
    results.sort(key=lambda x: (x['technical']['raw_score'] + x['volume']['raw_score']), reverse=True)
    top_10 = results[:10]
    top_10_kodes = [r['kode'] for r in top_10]
    
    # 4.5. Deep-Fetch (Fundamental, Info, News) Khusus Top 10
    logger.info(f"📥 Deep-fetching data (Fundamental & News) untuk Top 10: {top_10_kodes}")
    try:
        from data.fetcher.fundamental_fetcher import fetch_and_save_fundamentals
        from data.fetcher.news_fetcher import fetch_all_news, save_articles_to_db
        from bot.jobs_helper import process_unprocessed_news_sync # If needed, or we just rely on the next scheduler
        
        # Re-fetch info (company profile dll) supaya tidak kosong
        fetch_and_save_batch(top_10_kodes, include_info=True)
        # Fetch fundamental
        fetch_and_save_fundamentals(top_10_kodes)
        # Fetch news
        articles = fetch_all_news(top_10_kodes, max_results=5)
        save_articles_to_db(articles)
        
        # Note: Sentimen analisis akan dijalankan oleh scheduler job_fetch_news berikutnya,
        # Atau bisa dipanggil langsung jika ingin realtime. Untuk simplifikasi, biarkan scheduler yang handle.
    except Exception as e:
        logger.error(f"⚠️ Error saat deep-fetch Top 10: {e}")
    
    # 5. Simpan ke watchlist_harian
    today = date.today().isoformat()
    db.execute("DELETE FROM watchlist_harian WHERE tanggal = ?", (today,))
    
    data_to_db = []
    for i, r in enumerate(top_10, 1):
        data_to_db.append((
            today,
            r['kode'],
            i,
            r['technical']['raw_score'],
            r['volume']['raw_score'],
            r['technical']['raw_score'] + r['volume']['raw_score'],
            date.today().isoformat()
        ))
    
    db.execute_many(
        "INSERT INTO watchlist_harian VALUES (?,?,?,?,?,?,?)",
        data_to_db
    )
    logger.info(f"✅ Full market scan selesai. {len(top_10)} saham terpilih hari ini.")


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

    # Ambil dari watchlist_harian (hasil scan sore kemarin)
    # Jika kosong (misal weekend/baru install), pakai TEST_STOCKS
    rows = db.execute("SELECT kode FROM watchlist_harian ORDER BY tanggal DESC LIMIT 10")
    if rows:
        stocks = [r['kode'] for r in rows]
        logger.info(f"Menggunakan {len(stocks)} saham dari watchlist_harian terakhir.")
    else:
        stocks = TEST_STOCKS
        logger.info(f"Watchlist kosong, menggunakan {len(stocks)} TEST_STOCKS.")

    fetch_macro()  # Ambil data makro dulu

    result = run_full_analysis(stocks)
    report = format_full_report(result)

    # Note: Telegram sender dipanggil di level bot_main.py atau telegram_bot.py
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
    'fetch_full_scan': fetch_full_market_scan,
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
