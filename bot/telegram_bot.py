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
        result = run_full_analysis(TEST_STOCKS)
        result['track_record'] = get_track_record(30)
        text = format_briefing_pagi(result)
        await send_message(text, context.bot)
    except Exception as e:
        logger.error(f"JOB briefing error: {e}")
        await send_message(f"⚠️ Error briefing pagi: {str(e)[:200]}", context.bot)


async def job_update_siang(context: ContextTypes.DEFAULT_TYPE):
    """12:00 — Update status sinyal pagi."""
    logger.info("⏰ JOB: Update Siang")
    try:
        from bot.formatter import format_update_siang
        from portfolio.tracker import get_portfolio_summary, check_alerts

        summary = get_portfolio_summary()
        alerts = check_alerts()
        text = format_update_siang({}, {'alerts': alerts})
        await send_message(text, context.bot)
    except Exception as e:
        logger.error(f"JOB siang error: {e}")
        await send_message(f"⚠️ Error update siang: {str(e)[:200]}", context.bot)


async def job_sinyal_sore(context: ContextTypes.DEFAULT_TYPE):
    """16:15 — Sinyal BSJP sore."""
    logger.info("⏰ JOB: Sinyal Sore BSJP")
    try:
        from ai.agents import run_full_analysis
        from bot.formatter import format_sinyal_sore
        from config.settings import TEST_STOCKS

        result = run_full_analysis(TEST_STOCKS)
        text = format_sinyal_sore(result)
        await send_message(text, context.bot)
    except Exception as e:
        logger.error(f"JOB sore error: {e}")
        await send_message(f"⚠️ Error sinyal sore: {str(e)[:200]}", context.bot)


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
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=12, minute=0, day_of_week='mon-fri'), args=[job_update_siang, bot], name='update_siang')
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=16, minute=15, day_of_week='mon-fri'), args=[job_sinyal_sore, bot], name='sinyal_sore')
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=16, minute=30, day_of_week='mon-fri'), args=[job_fetch_ohlcv, bot], name='fetch_ohlcv')

    # Setiap 2 jam: fetch news
    scheduler.add_job(_wrap, trigger=CronTrigger(hour='6,8,10,12,14,16,18,20,22'), args=[job_fetch_news, bot], name='fetch_news')

    # Setiap hari: fundamental jam 22:00
    scheduler.add_job(_wrap, trigger=CronTrigger(hour=22, minute=0), args=[job_fetch_fundamental, bot], name='fetch_fundamental')

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
        cmd_scanner
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
    ]
    for name, handler in commands:
        app.add_handler(CommandHandler(name, handler))

    # ── Button text handler (Reply Keyboard) ─────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_text))

    logger.info(f"✅ {len(commands)} commands + button handler registered")
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
