"""
bot/telegram_bot.py — Main bot: Telegram + APScheduler (ALL-IN-ONE).

Tidak perlu n8n. PM2 cukup untuk keep-alive di VPS.
Jadwal otomatis:
  07:00 WIB → Briefing Pagi
  12:00 WIB → Update Siang
  16:15 WIB → Sinyal Sore BSJP
  16:30 WIB → Fetch OHLCV
  22:00 WIB → Fetch Fundamental
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loguru import logger
from telegram import Bot, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, VPS_TIMEZONE
from data.database import db
from bot.commands import (
    cmd_start, cmd_help, cmd_analisa, cmd_bandingkan,
    cmd_market, cmd_portfolio, cmd_pnl, cmd_beli,
    cmd_jual, cmd_track, cmd_setting, handle_button_text,
)


# ═══════════════════════════════════════════════════════
# SEND MESSAGE (untuk scheduler)
# ═══════════════════════════════════════════════════════

async def send_message(text: str, bot: Bot, chat_id: str = None):
    """Kirim pesan ke Telegram. Auto-split jika > 4096 chars."""
    cid = chat_id or TELEGRAM_CHAT_ID
    if len(text) > 4096:
        for i in range(0, len(text), 4096):
            await bot.send_message(chat_id=cid, text=text[i:i+4096])
    else:
        await bot.send_message(chat_id=cid, text=text)
    logger.info(f"📨 Pesan terkirim ({len(text)} chars)")


async def send_top_chart(result_data: dict, bot: Bot, chat_id: str = None):
    """Mencari Top #1 saham dari result_data, buat chart, lalu kirim ke Telegram."""
    cid = chat_id or TELEGRAM_CHAT_ID
    if not result_data.get('signals'):
        return

    sorted_signals = sorted(
        result_data['signals'].items(),
        key=lambda x: x[1].get('score', {}).get('total', 0),
        reverse=True,
    )
    
    if not sorted_signals:
        return
        
    top_kode = sorted_signals[0][0]
    
    from utils.chart_generator import generate_advanced_chart
    chart_path = generate_advanced_chart(top_kode, days=150)
    
    if chart_path:
        try:
            with open(chart_path, 'rb') as photo:
                await bot.send_photo(
                    chat_id=cid,
                    photo=photo,
                    caption=f"📈 Chart Top #1 Pilihan AI: <b>{top_kode}</b>",
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Gagal send top chart {top_kode}: {e}")
        finally:
            import os
            if os.path.exists(chart_path):
                os.remove(chart_path)


# ═══════════════════════════════════════════════════════
# SCHEDULED JOBS
# ═══════════════════════════════════════════════════════

async def job_briefing_pagi(context: ContextTypes.DEFAULT_TYPE):
    """07:00 — Briefing pagi + sinyal."""
    logger.info("⏰ JOB: Briefing Pagi")
    try:
        from data.fetcher.macro_fetcher import fetch_and_save_macro
        from ai.agents import run_full_analysis, format_full_report
        from bot.formatter import format_briefing_pagi
        from portfolio.tracker import get_track_record
        from config.settings import TEST_STOCKS

        fetch_and_save_macro()

        # Ambil Top 5-10 dari scan market terakhir
        rows = db.execute("SELECT kode FROM watchlist_harian ORDER BY tanggal DESC LIMIT 10")
        if rows:
            stocks = [r['kode'] for r in rows]
            logger.info(f"Using {len(stocks)} stocks from watchlist_harian for briefing")
        else:
            stocks = TEST_STOCKS
            logger.warning("Watchlist harian kosong, menggunakan TEST_STOCKS")

        result = run_full_analysis(stocks)
        result['track_record'] = get_track_record(30)
        
        # Kirim chart top #1 dulu
        await send_top_chart(result, context.bot)
        
        text = format_briefing_pagi(result)
        await send_message(text, context.bot)
    except Exception as e:
        logger.error(f"JOB briefing error: {e}")
        await send_message(f"⚠️ Error briefing pagi: {str(e)[:200]}", context.bot)


async def job_swing_pagi(context: ContextTypes.DEFAULT_TYPE):
    """07:30 Senin — Swing Trade screening mingguan."""
    logger.info("⏰ JOB: Swing Trade Mingguan (Senin Pagi)")
    try:
        from analysis.swing_screening import run_swing_screening, save_swing_watchlist, get_swing_candidates
        from data.fetcher.stock_fetcher import fetch_and_save_batch
        from bot.formatter import format_swing

        logger.info("🌊 Swing: Fetching fresh OHLCV data...")
        candidates = get_swing_candidates(150)
        fetch_and_save_batch(candidates, include_info=False)
        
        logger.info("🔍 Swing: Running screening...")
        results = run_swing_screening(candidates)
        
        if not results:
            await send_message("🌊 Swing: Tidak ada setup swing kuat minggu ini.", context.bot)
            return
            
        save_swing_watchlist(results)
        
        # Broadcast chart top #1
        top_kode = results[0]['kode']
        from utils.chart_generator import generate_advanced_chart
        chart_path = generate_advanced_chart(top_kode, days=150)
        if chart_path:
            try:
                with open(chart_path, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=TELEGRAM_CHAT_ID,
                        photo=photo,
                        caption=f"📈 Swing Top #1: <b>{top_kode}</b>",
                        parse_mode='HTML'
                    )
            except Exception as e:
                logger.error(f"Gagal send Swing chart {top_kode}: {e}")
            finally:
                import os
                if os.path.exists(chart_path):
                    os.remove(chart_path)
                    
        text = format_swing(results)
        await send_message(text, context.bot)
        logger.info(f"✅ Swing broadcast selesai: {len(results)} stocks")
    except Exception as e:
        logger.error(f"JOB Swing error: {e}")
        await send_message(f"⚠️ Error Swing: {str(e)[:200]}", context.bot)


async def job_update_siang(context: ContextTypes.DEFAULT_TYPE):
    """12:00 — Evaluasi/alert portfolio di jam istirahat."""
    logger.info("⏰ JOB: Update Siang (Cek Sinyal Pagi)")
    try:
        from bot.formatter import format_update_siang
        from data.database import db
        from data.fetcher.stock_fetcher import fetch_and_save_batch
        from datetime import date

        today = date.today().isoformat()
        
        # 1. Ambil target pagi dari sinyal_history (Top 10)
        rows = db.execute(
            "SELECT kode, entry_high as base_close, target as tp1, stoploss as cl FROM sinyal_history WHERE tanggal = ? AND status = 'ACTIVE' ORDER BY skor_total DESC LIMIT 10",
            (today,)
        )
        if not rows:
            logger.warning("Tidak ada data sinyal_history pagi untuk di update siang ini.")
            return

        candidates = [r['kode'] for r in rows]
        
        # 2. Ambil harga live (fresh fetch jam 12:00)
        fetch_and_save_batch(candidates, include_info=False)
        
        results = []
        for r in rows:
            kode = r['kode']
            # Ambil close terbaru yang baru saja di fetch
            live_data = db.execute(
                "SELECT close FROM harga_historis WHERE kode = ? ORDER BY tanggal DESC LIMIT 1",
                (kode,)
            )
            live_close = live_data[0]['close'] if live_data else r['base_close']
            tp2 = round(r['tp1'] * 1.05) if r['tp1'] else 0
            
            results.append({
                'kode': kode,
                'entry_low': r['base_close'], # Harga rujukan pagi
                'close': live_close,     # Harga update siang
                'tp1': r['tp1'],
                'tp2': tp2,
                'cl': r['cl']
            })
            
        text = format_update_siang(results)
        await send_message(text, context.bot)
        logger.info(f"✅ Update Siang broadcast selesai untuk {len(results)} saham")
    except Exception as e:
        logger.error(f"JOB siang error: {e}")
        await send_message(f"⚠️ Error update siang: {str(e)[:200]}", context.bot)

async def job_bsjp_fetch(context: ContextTypes.DEFAULT_TYPE):
    """14:30 — Download fresh data 800 emiten buat persiapan BSJP."""
    logger.info("⏰ JOB: BSJP Fresh Market Data Fetch")
    await send_message("⏳ <b>Persiapan BSJP Sore:</b>\nMengunduh data terbaru untuk seluruh saham...", context.bot)
    try:
        from data.fetcher.stock_fetcher import get_all_stock_codes, fetch_and_save_batch
        codes = get_all_stock_codes()
        fetch_and_save_batch(codes, include_info=False)
        logger.info("✅ BSJP fresh data download complete")
    except Exception as e:
        logger.error(f"JOB BSJP Fetch error: {e}")

async def job_bsjp_broadcast(context: ContextTypes.DEFAULT_TYPE):
    """15:00 — Screen BSJP & Broadcast."""
    logger.info("⏰ JOB: BSJP Sore (Scan + Broadcast)")
    try:
        from analysis.bsjp_screening import run_bsjp_screening, save_bsjp_watchlist, get_bsjp_candidates
        from bot.formatter import format_bsjp

        # Ambil Top 200 kandidat aja dari 800
        candidates = get_bsjp_candidates(200)
        
        # Step 2: Quick scan BSJP
        logger.info("🔍 BSJP: Running quick screening...")
        results = run_bsjp_screening(candidates)
        
        if not results:
            await send_message("🌆 BSJP: Tidak ada kandidat yang memenuhi kriteria hari ini.", context.bot)
            return
        
        save_bsjp_watchlist(results)
        
        # Step 3: Broadcast chart top #1 + results
        top_kode = results[0]['kode']
        from utils.chart_generator import generate_advanced_chart
        chart_path = generate_advanced_chart(top_kode, days=60)
        if chart_path:
            try:
                cid = TELEGRAM_CHAT_ID
                with open(chart_path, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=cid,
                        photo=photo,
                        caption=f"📈 BSJP Top #1: <b>{top_kode}</b>",
                        parse_mode='HTML'
                    )
            except Exception as e:
                logger.error(f"Gagal send BSJP chart {top_kode}: {e}")
            finally:
                import os
                if os.path.exists(chart_path):
                    os.remove(chart_path)
        
        text = format_bsjp(results)
        await send_message(text, context.bot)
        logger.info(f"✅ BSJP broadcast selesai: {len(results)} stocks")
    except Exception as e:
        logger.error(f"JOB BSJP error: {e}")
        await send_message(f"⚠️ Error BSJP: {str(e)[:200]}", context.bot)


async def job_fetch_ohlcv(context: ContextTypes.DEFAULT_TYPE):
    """16:30 — Fetch data harga setelah bursa tutup."""
    logger.info("⏰ JOB: Fetch OHLCV")
    try:
        from data.fetcher.stock_fetcher import fetch_and_save_batch
        from config.settings import TEST_STOCKS
        fetch_and_save_batch(TEST_STOCKS)
        logger.info("✅ OHLCV fetch selesai")
    except Exception as e:
        logger.error(f"JOB fetch error: {e}")
        await send_message(f"⚠️ Error fetch data: {str(e)[:200]}", context.bot)


async def job_fetch_news(context: ContextTypes.DEFAULT_TYPE):
    """Setiap 2 jam — Fetch berita + sentimen."""
    logger.info("⏰ JOB: Fetch News + Sentiment")
    try:
        from data.fetcher.news_fetcher import fetch_all_news, save_articles_to_db
        from ai.sentiment import process_unprocessed_news
        articles = fetch_all_news()
        save_articles_to_db(articles)
        process_unprocessed_news(limit=20)
    except Exception as e:
        logger.error(f"JOB news error: {e}")


async def job_fetch_fundamental(context: ContextTypes.DEFAULT_TYPE):
    """22:00 — Fetch data fundamental."""
    logger.info("⏰ JOB: Fetch Fundamentals")
    try:
        from data.fetcher.fundamental_fetcher import fetch_and_save_fundamentals
        from config.settings import TEST_STOCKS
        fetch_and_save_fundamentals(TEST_STOCKS)
    except Exception as e:
        logger.error(f"JOB fundamental error: {e}")


async def job_full_market_scan(context: ContextTypes.DEFAULT_TYPE):
    """21:00 (Senin-Jumat) — Scan market penuh (800+ saham)."""
    logger.info("⏰ JOB: Full Market Scan")
    try:
        from scheduler.jobs import fetch_full_market_scan
        fetch_full_market_scan()
        logger.info("✅ Full market scan completed")
    except Exception as e:
        logger.error(f"JOB scanner error: {e}")
        await send_message(f"⚠️ Error scanner: {str(e)[:200]}", context.bot)

async def job_auto_alert(context: ContextTypes.DEFAULT_TYPE):
    """Setiap 15 menit jam kerja — Cek TP/SL untuk Portofolio & Sinyal."""
    logger.info("⏰ JOB: Auto-Target Alert")
    try:
        from scheduler.auto_alert import run_auto_target_alert
        from config.settings import TELEGRAM_CHAT_ID
        run_auto_target_alert(context.bot, TELEGRAM_CHAT_ID)
    except Exception as e:
        logger.error(f"JOB auto alert error: {e}")

async def job_weekly_reflection(context: ContextTypes.DEFAULT_TYPE):
    """Minggu 09:00 — AI melakukan evaluasi diri dan generate pedoman baru."""
    logger.info("⏰ JOB: Weekly Reflection (AI Self-Learning)")
    try:
        from analysis.reflection import run_weekly_reflection
        lessons = run_weekly_reflection()
        if lessons:
            text = (
                "🧠 <b>AI WEEKLY REFLECTION</b>\n"
                "<i>Self-Learning Loop Activated</i>\n"
                "─────────────────────\n\n"
                f"{lessons}\n\n"
                "💡 <i>Pedoman ini akan otomatis disuntikkan ke analisa AI minggu depan.</i>"
            )
            await send_message(text, context.bot)
        else:
            logger.info("Weekly reflection tidak menghasilkan lessons baru.")
    except Exception as e:
        logger.error(f"JOB Weekly Reflection error: {e}")


# ═══════════════════════════════════════════════════════
# BUILD APPLICATION
# ═══════════════════════════════════════════════════════

async def post_init(application):
    """Callback: start scheduler SETELAH event loop ready."""
    bot = application.bot

    scheduler = AsyncIOScheduler(timezone=VPS_TIMEZONE)

    # Wrapper: bungkus job agar punya akses ke bot
    async def _wrap(job_func, bot_ref):
        class FakeCtx:
            def __init__(self, b): self.bot = b
        await job_func(FakeCtx(bot_ref))

    # Senin-Jumat
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=7, minute=0, day_of_week='mon-fri'), args=[job_briefing_pagi, bot], name='briefing_pagi')
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=7, minute=30, day_of_week='mon'), args=[job_swing_pagi, bot], name='swing_senin')
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=12, minute=0, day_of_week='mon-fri'), args=[job_update_siang, bot], name='update_siang')
    
    # BSJP Pipeline
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=14, minute=30, day_of_week='mon-fri'), args=[job_bsjp_fetch, bot], name='bsjp_fetch')
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=15, minute=0, day_of_week='mon-fri'), args=[job_bsjp_broadcast, bot], name='bsjp_broadcast')
    
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=16, minute=30, day_of_week='mon-fri'), args=[job_fetch_ohlcv, bot], name='fetch_ohlcv')

    # Setiap 2 jam: fetch news
    scheduler.add_job(_wrap, trigger=CronTrigger(hour='6,8,10,12,14,16,18,20,22'), args=[job_fetch_news, bot], name='fetch_news')

    # Auto-Target Alert (Tiap 15 Menit hari kerja 09:00 - 15:45)
    scheduler.add_job(_wrap, trigger=CronTrigger(day_of_week='mon-fri', hour='9-15', minute='0,15,30,45'), args=[job_auto_alert, bot], name='auto_alert')

    # Setiap hari: fundamental & Full Market Scan jam 21:00 - 22:00
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=21, minute=0, day_of_week='mon-fri'), args=[job_full_market_scan, bot], name='full_market_scan')
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=22, minute=0), args=[job_fetch_fundamental, bot], name='fetch_fundamental')

    # Weekly Reflection (Minggu 09:00)
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=9, minute=0, day_of_week='sun'), args=[job_weekly_reflection, bot], name='weekly_reflection')

    scheduler.start()
    logger.info(f"⏰ Scheduler started ({len(scheduler.get_jobs())} jobs)")
    for job in scheduler.get_jobs():
        logger.info(f"   📅 {job.name}: {job.trigger}")


def build_app():
    """Build Telegram app + command handlers + scheduler."""
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # ── Command handlers ────────────────────
    from bot.commands import (
        cmd_start, cmd_help, cmd_analisa, cmd_bandingkan,
        cmd_market, cmd_portfolio, cmd_pnl, cmd_beli,
        cmd_jual, cmd_track, cmd_setting, handle_button_text,
        cmd_fetch_macro, cmd_fetch_ohlcv, cmd_fetch_fundamental, cmd_fetch_news,
        cmd_scanner, handle_callback_query, cmd_quick_chart, cmd_quick_analisa,
        cmd_sinyal, cmd_bsjp, cmd_swing, cmd_performance_check
    )

    commands = [
        ("start", cmd_start),
        ("help", cmd_help),
        ("analisa", cmd_analisa),
        ("bandingkan", cmd_bandingkan),
        ("market", cmd_market),
        ("portfolio", cmd_portfolio),
        ("pnl", cmd_pnl),
        ("beli", cmd_beli),
        ("jual", cmd_jual),
        ("track", cmd_track),
        ("setting", cmd_setting),
        ("fetch_macro", cmd_fetch_macro),
        ("fetch_ohlcv", cmd_fetch_ohlcv),
        ("fetch_fundamental", cmd_fetch_fundamental),
        ("fetch_news", cmd_fetch_news),
        ("scanner", cmd_scanner),
        ("sinyal", cmd_sinyal),
        ("bsjp", cmd_bsjp),
        ("swing", cmd_swing),
        ("performa", cmd_performance_check),
        ("setmodal", cmd_setmodal),
    ]
    for name, handler in commands:
        app.add_handler(CommandHandler(name, handler))

    # ── Button text handler (Reply Keyboard) ─────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_text))
    
    # ── Dynamic Chart Command (/c_KODE) ──────────
    app.add_handler(MessageHandler(filters.Regex(r'^/[cC]_[a-zA-Z0-9]+'), cmd_quick_chart))

    # ── Dynamic AI Analisa Command (/a_KODE) ─────
    app.add_handler(MessageHandler(filters.Regex(r'^/[aA]_[a-zA-Z0-9]+'), cmd_quick_analisa))

    # ── Inline Keyboard Callback handler ────────
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    logger.info(f"✅ {len(commands)} commands + button & callback handlers registered")
    return app


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IDX AI Trading Bot")
    parser.add_argument('--test', action='store_true', help='Kirim pesan test')
    parser.add_argument('--run', action='store_true', help='Jalankan bot (polling)')
    args = parser.parse_args()

    db.create_all_tables()

    if args.test:
        async def _test():
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            await send_message(
                "🤖 *IDX AI Trading Assistant*\n\n"
                "✅ Bot berhasil terkoneksi!\n"
                "Ketik /start untuk mulai.",
                bot,
            )
        asyncio.run(_test())
        print("✅ Pesan test terkirim!")

    elif args.run:
        logger.info("🤖 Starting IDX AI Trading Bot...")
        app = build_app()
        app.run_polling(drop_pending_updates=True)

    else:
        parser.print_help()
