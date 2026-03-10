"""
bot/commands.py — Telegram command handlers + Reply Keyboard.

Menu tombol di bawah chat:
Row 1: [ 📊 Market ] [ 🎯 Sinyal Hari Ini ]
Row 2: [ 💼 Portfolio ] [ 📈 Track Record ]
Row 3: [ 🔍 Analisa Saham ] [ ⚙️ Setting ]
"""

import sys
from pathlib import Path
from datetime import datetime
import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from loguru import logger

from config.settings import MODAL_AWAL, MAX_POSISI, TEST_STOCKS
from data.database import db
from analysis.technical import calculate_indicators
from analysis.scoring import calculate_composite_score, format_score_report
from portfolio.tracker import (
    buy_position, sell_position, get_portfolio_summary,
    check_alerts, get_track_record,
)
from bot.formatter import (
    format_analisa, format_portfolio, format_track_record,
)

# ── Import Fetchers untuk Admin Commands ──
from data.fetcher.macro_fetcher import fetch_and_save_macro
from data.fetcher.stock_fetcher import fetch_and_save_batch
from data.fetcher.fundamental_fetcher import fetch_and_save_fundamentals
from data.fetcher.news_fetcher import fetch_all_news, save_articles_to_db
from ai.sentiment import process_unprocessed_news


# ═══════════════════════════════════════════════════════
# REPLY KEYBOARD (Menu Tombol Permanen)
# ═══════════════════════════════════════════════════════

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Market"), KeyboardButton("🎯 Sinyal Hari Ini")],
        [KeyboardButton("💼 Portfolio"), KeyboardButton("📈 Track Record")],
        [KeyboardButton("🔍 Analisa Saham"), KeyboardButton("⚙️ Setting")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


def _reply(text: str):
    """Helper: tambahkan keyboard ke setiap reply."""
    return {'text': text, 'reply_markup': MAIN_KEYBOARD}


# ═══════════════════════════════════════════════════════
# BUTTON TEXT HANDLER (baca tombol yang ditekan)
# ═══════════════════════════════════════════════════════

async def handle_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tombol Reply Keyboard yang ditekan user."""
    text = update.message.text.strip()

    if text == "📊 Market":
        await cmd_market(update, context)
    elif text == "🎯 Sinyal Hari Ini":
        await cmd_sinyal(update, context)
    elif text == "💼 Portfolio":
        await cmd_portfolio(update, context)
    elif text == "📈 Track Record":
        await cmd_track(update, context)
    elif text == "🔍 Analisa Saham":
        await update.message.reply_text(
            "🔍 Ketik kode saham yang ingin dianalisa:\n\n"
            "Contoh: /analisa BBCA\n\n"
            "Atau pilih saham populer:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("BBCA", callback_data="analisa_BBCA"),
                    InlineKeyboardButton("BBRI", callback_data="analisa_BBRI"),
                    InlineKeyboardButton("BMRI", callback_data="analisa_BMRI"),
                ],
                [
                    InlineKeyboardButton("TLKM", callback_data="analisa_TLKM"),
                    InlineKeyboardButton("ASII", callback_data="analisa_ASII"),
                    InlineKeyboardButton("UNVR", callback_data="analisa_UNVR"),
                ],
            ]),
        )
    elif text == "⚙️ Setting":
        await cmd_setting(update, context)
    else:
        # Cek apakah user mengetik kode saham
        if text.isalpha() and len(text) == 4:
            context.args = [text.upper()]
            await cmd_analisa(update, context)
        else:
            await update.message.reply_text(
                "🤖 Gunakan tombol di bawah atau ketik /help",
                reply_markup=MAIN_KEYBOARD,
            )


# ═══════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome + tampilkan Reply Keyboard."""
    text = (
        "🤖 *IDX AI Trading Assistant*\n\n"
        "Selamat datang! Saya asisten trading AI\n"
        "untuk pasar saham Indonesia 🇮🇩\n\n"
        "🧠 *Fitur AI:*\n"
        "• 5 Agent AI (termasuk Bull vs Bear debate)\n"
        "• Scoring 100 poin (4 dimensi)\n"
        "• Portfolio tracker + P&L\n"
        "• Sinyal otomatis 3x/hari\n\n"
        "👇 *Gunakan tombol di bawah untuk mulai:*"
    )
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Daftar command."""
    text = (
        "📖 *PANDUAN COMMAND*\n\n"
        "*Analisa:*\n"
        "/analisa `KODE` — Analisa 5-agent AI\n"
        "/bandingkan `K1 K2` — Bandingkan 2 saham\n"
        "/sinyal — Sinyal Top 10 harian\n"
        "/market — Kondisi pasar\n\n"
        "*Portfolio:*\n"
        "/portfolio — Lihat posisi\n"
        "/pnl — P&L hari ini\n"
        "/beli `KODE LOT HARGA` — Input beli\n"
        "/jual `KODE LOT HARGA` — Input jual\n"
        "/track — Track record 30 hari\n\n"
        "🛠 *Admin/Manual Fetch:*\n"
        "/scanner — Full market scan (800+ saham)\n"
        "/fetch\\_macro — Download IHSG/Global\n"
        "/fetch\\_ohlcv — Download harga harian\n"
        "/fetch\\_fundamental — Download LK\n"
        "/fetch\\_news — Download berita & sentimen\n\n"
        "💡 *Atau gunakan tombol menu di bawah!*"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)


async def cmd_sinyal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sinyal hari ini (diambil dari watchlist_harian hasil scanner)."""
    await update.message.reply_text("🎯 Mengambil rekomendasi Top 10 hari ini...", reply_markup=MAIN_KEYBOARD)

    try:
        # 1. Cek watchlist_harian terbaru
        rows = db.execute("SELECT kode FROM watchlist_harian ORDER BY tanggal DESC LIMIT 10")
        if rows:
            stocks = [r['kode'] for r in rows]
            source_text = "berdasarkan *Full Market Scan*"
        else:
            stocks = TEST_STOCKS
            source_text = "berdasarkan *Test Stocks* (Scan belum dijalankan)"

        results = []
        for kode in stocks:
            score = calculate_composite_score(kode)
            results.append(score)

        results.sort(key=lambda x: x['total'], reverse=True)

        tanggal_sekarang = datetime.now(pytz.timezone('Asia/Jakarta')).strftime('%d %B %Y | %H:%M WIB')
        lines = [f"🎯 *SINYAL HARI INI* — {tanggal_sekarang}\n_{source_text}_\n"]
        rank_emoji = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}

        for i, r in enumerate(results, 1):
            e = r.get('emoji', '❓')
            lines.append(
                f"{rank_emoji.get(i, str(i)+'.')} /c_{r['kode']} {e} {r['label']} ({r['total']:.1f} pt)"
            )

        lines.append("\n💡 Klik tulisan biru (misal /c_BBCA) untuk lihat Chart & Analisa")
        text = "\n".join(lines)

        top_kode = results[0]['kode'] if results else None
        
        if top_kode:
            from utils.chart_generator import generate_advanced_chart
            chart_path = generate_advanced_chart(top_kode, days=150)
            if chart_path:
                try:
                    with open(chart_path, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=update.effective_chat.id,
                            photo=photo,
                            caption=f"📈 Chart Top #1 Pilihan AI: *{top_kode}*",
                            parse_mode="Markdown"
                        )
                except Exception as e:
                    logger.error(f"Gagal mengirim chart top_kode {top_kode}: {e}")
                finally:
                    import os
                    if os.path.exists(chart_path):
                        os.remove(chart_path)

        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        logger.error(f"Error sinyal: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


async def cmd_quick_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command dinamis /c_KODE -> redirect ke /analisa KODE"""
    text = update.message.text
    if "@" in text:
        text = text.split("@")[0]
    kode = text.replace("/c_", "", 1).replace("/C_", "", 1).upper()
    
    if not kode:
        return
        
    context.args = [kode]
    await cmd_analisa(update, context)


async def cmd_analisa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analisa lengkap 1 saham via 5 agent AI."""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Ketik kode saham setelah command:\n/analisa BBCA",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    kode = context.args[0].upper()
    await update.message.reply_text(
        f"🔍 Menganalisa *{kode}*...\n⏳ 5 Agent AI sedang bekerja (30-60 detik)",
        parse_mode='Markdown', reply_markup=MAIN_KEYBOARD,
    )

    try:
        from ai.agents import run_full_analysis
        result = run_full_analysis([kode])

        if kode in result.get('signals', {}):
            data = result['signals'][kode]
            text = format_analisa(kode, data)
            
            # Tambahkan Auto-Chart Image
            from utils.chart_generator import generate_advanced_chart
            chart_path = generate_advanced_chart(kode, days=150)
            if chart_path:
                try:
                    with open(chart_path, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=update.effective_chat.id,
                            photo=photo,
                            caption=f"📈 *{kode}* — Auto-Chart (EMA, BB, Volume, MACD, StochRSI)",
                            parse_mode="Markdown"
                        )
                except Exception as e:
                    logger.error(f"Gagal mengirim chart {kode}: {e}")
                finally:
                    # Optional: hapus gambar jika tidak ingin memakan tempat
                    import os
                    if os.path.exists(chart_path):
                        os.remove(chart_path)
            
        else:
            text = f"❌ Gagal menganalisa {kode}. Pastikan kode saham benar."
    except Exception as e:
        logger.error(f"Error analisa {kode}: {e}")
        text = f"❌ Error analisa {kode}: {str(e)[:150]}"

    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)


async def cmd_bandingkan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bandingkan 2 saham."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Format: /bandingkan BBCA BMRI", reply_markup=MAIN_KEYBOARD)
        return

    k1 = context.args[0].upper()
    k2 = context.args[1].upper()
    await update.message.reply_text(f"⚔️ Membandingkan {k1} vs {k2}...", reply_markup=MAIN_KEYBOARD)

    try:
        from ai.agents import run_full_analysis
        result = run_full_analysis([k1, k2])
        signals = result.get('signals', {})

        lines = [f"⚔️ *{k1} vs {k2}*\n"]
        for kode in [k1, k2]:
            if kode in signals:
                s = signals[kode].get('score', {})
                d = signals[kode].get('debate', {})
                e = s.get('emoji', '❓')
                lines.append(
                    f"{e} *{kode}*: {s.get('total', 0)}/100 ({s.get('label', 'SKIP')})\n"
                    f"   T:{s.get('d1_technical',{}).get('score',0):.0f} "
                    f"V:{s.get('d2_volume',{}).get('score',0):.0f} "
                    f"F:{s.get('d3_fundamental',{}).get('score',0):.0f} "
                    f"S:{s.get('d4_sentiment',{}).get('score',0):.0f}\n"
                    f"   Debate: {d.get('debate_verdict', '-')}\n"
                )

        s1 = signals.get(k1, {}).get('score', {}).get('total', 0)
        s2 = signals.get(k2, {}).get('score', {}).get('total', 0)
        winner = k1 if s1 > s2 else k2
        lines.append(f"🏆 *Pemenang: {winner}*")

        await update.message.reply_text("\n".join(lines), parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kondisi pasar."""
    try:
        macro = db.execute("SELECT * FROM makro_data ORDER BY tanggal DESC LIMIT 1")
        if not macro:
            await update.message.reply_text(
                "❌ Data makro belum tersedia.\nJalankan fetch dulu.", reply_markup=MAIN_KEYBOARD)
            return

        m = dict(macro[0])
        label = m.get('market_label', 'UNKNOWN')
        emoji_map = {'BULLISH': '🟢', 'MIXED': '🟡', 'BEARISH': '🔴', 'EXTREME': '⚫'}

        text = (
            f"📊 *KONDISI PASAR*\n"
            f"📅 {m.get('tanggal', '-')}\n\n"
            f"{emoji_map.get(label, '❓')} *{label}*\n\n"
            f"IHSG      : {m.get('ihsg_change', 0):+.2%}\n"
            f"Nikkei    : {m.get('nikkei_change', 0):+.2%}\n"
            f"Hang Seng : {m.get('hsi_change', 0):+.2%}\n"
            f"STI       : {m.get('sti_change', 0):+.2%}\n"
            f"Gold      : {m.get('gold_change', 0):+.2%}\n"
            f"Oil       : {m.get('oil_change', 0):+.2%}"
        )
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lihat portfolio."""
    try:
        summary = get_portfolio_summary()
        text = format_portfolio(summary)

        alerts = check_alerts()
        if alerts:
            text += "\n\n🔔 *ALERTS:*"
            for a in alerts[:3]:
                text += f"\n{a['message'][:100]}"

        await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """P&L hari ini."""
    try:
        summary = get_portfolio_summary()
        track = get_track_record(days=1)

        text = (
            f"💰 *P&L HARI INI*\n\n"
            f"Unrealized : Rp {summary.get('total_unrealized', 0):,.0f}\n"
            f"Posisi aktif: {summary.get('n_positions', 0)}\n"
        )
        if track['total_trades'] > 0:
            text += f"\nRealized: Rp {track['total_pnl']:,.0f}"

        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


async def cmd_beli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Input posisi beli: /beli BBCA 10 9200"""
    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ Format: /beli KODE LOT HARGA\n"
            "Contoh: /beli BBCA 10 9200", reply_markup=MAIN_KEYBOARD)
        return

    try:
        kode = context.args[0].upper()
        lot = int(context.args[1])
        harga = float(context.args[2])

        result = buy_position(kode, lot, harga)

        if result['success']:
            text = (
                f"✅ *BELI {kode}*\n\n"
                f"Lot    : {lot} ({lot * 100} lembar)\n"
                f"Harga  : Rp {harga:,.0f}\n"
                f"Cost   : Rp {result['cost']:,.0f}\n"
                f"Sisa   : Rp {result['sisa_cash']:,.0f}"
            )
        else:
            text = f"❌ {result['error']}"

        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ Format salah. Contoh: /beli BBCA 10 9200", reply_markup=MAIN_KEYBOARD)


async def cmd_jual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Input posisi jual: /jual BBCA 10 9400"""
    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ Format: /jual KODE LOT HARGA\n"
            "Contoh: /jual BBCA 10 9400", reply_markup=MAIN_KEYBOARD)
        return

    try:
        kode = context.args[0].upper()
        lot = int(context.args[1])
        harga = float(context.args[2])

        result = sell_position(kode, lot, harga)

        if result['success']:
            emoji = "🟢" if result['pnl'] > 0 else "🔴"
            text = (
                f"✅ *JUAL {kode}* {emoji}\n\n"
                f"Lot    : {lot}\n"
                f"Beli   : Rp {result['harga_beli']:,.0f}\n"
                f"Jual   : Rp {harga:,.0f}\n"
                f"P&L    : Rp {result['pnl']:,.0f} ({result['pnl_pct']:+.1%})\n"
                f"Sisa   : Rp {result['sisa_cash']:,.0f}"
            )
        else:
            text = f"❌ {result['error']}"

        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ Format salah. Contoh: /jual BBCA 10 9400", reply_markup=MAIN_KEYBOARD)


async def cmd_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track record 30 hari."""
    try:
        track = get_track_record(30)
        text = format_track_record(track)
        await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


async def cmd_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lihat setting."""
    text = (
        f"⚙️ *SETTING*\n\n"
        f"Modal awal  : Rp {MODAL_AWAL:,.0f}\n"
        f"Max posisi  : {MAX_POSISI}\n"
        f"Test stocks : {', '.join(TEST_STOCKS)}\n\n"
        f"_Ubah via file .env dan restart bot._"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Baca Panduan Lengkap (/help)", callback_data="help")]
    ])
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle respons dari InlineKeyboardButton."""
    query = update.callback_query
    await query.answer()  # Wajib panggil ini agar indikator loading di tombol hilang
    
    data = query.data
    logger.info(f"Callback Query: {data}")
    
    if data == "help":
        await cmd_help(update, context)
    elif data.startswith("analisa_"):
        kode = data.split("_")[1]
        context.args = [kode]
        # Agar update.message dikenali walau dari callback
        update.message = query.message 
        await cmd_analisa(update, context)


# ═══════════════════════════════════════════════════════
# ADMIN DATA FETCH COMMANDS
# ═══════════════════════════════════════════════════════

async def cmd_fetch_macro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Mengunduh data makro (IHSG, Nikkei, dsb)...")
    try:
        fetch_and_save_macro()
        await update.message.reply_text("✅ Data makro berhasil diunduh dan disimpan.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

async def cmd_fetch_ohlcv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⏳ Mengunduh data OHLCV untuk {len(TEST_STOCKS)} saham...")
    try:
        fetch_and_save_batch(TEST_STOCKS)
        await update.message.reply_text("✅ Data harga harian (OHLCV) berhasil diunduh.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

async def cmd_fetch_fundamental(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⏳ Mengunduh data fundamental untuk {len(TEST_STOCKS)} saham...")
    try:
        fetch_and_save_fundamentals(TEST_STOCKS)
        await update.message.reply_text("✅ Data fundamental berhasil diunduh.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

async def cmd_fetch_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Mengunduh berita dan memproses sentimen AI...")
    try:
        articles = fetch_all_news()
        save_articles_to_db(articles)
        processed_count = process_unprocessed_news(limit=20)
        await update.message.reply_text(f"✅ {len(articles)} berita diunduh, {processed_count} diklasifikasi AI.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")


async def cmd_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger Full Market Scan (800+ saham)."""
    await update.message.reply_text(
        "🚀 *MEMULAI FULL MARKET SCAN*\n"
        "📦 Memproses 800+ saham IHSG...\n"
        "⏳ Estimasi waktu: 5-10 menit di VPS.\n"
        "💡 Hasil akan muncul otomatis di menu 'Sinyal Hari Ini' setelah selesai.",
        parse_mode='Markdown', reply_markup=MAIN_KEYBOARD
    )
    try:
        from scheduler.jobs import fetch_full_market_scan
        # Jalankan secara sync untuk sekarang agar user tau statusnya (atau bisa async di VPS)
        # Di sini kita panggil langsung function-nya
        fetch_full_market_scan()
        await update.message.reply_text("✅ Full market scan SELESAI! Silakan cek menu Sinyal Hari Ini.")
    except Exception as e:
        logger.error(f"Error scanner: {e}")
        await update.message.reply_text(f"❌ Error scanner: {str(e)[:100]}")
