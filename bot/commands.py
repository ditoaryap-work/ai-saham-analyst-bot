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

# ── Config & Constants ──
from config.settings import MAX_POSISI, TEST_STOCKS
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
# REPLY KEYBOARDS (Menu & Sub-Menu)
# ═══════════════════════════════════════════════════════

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Market"), KeyboardButton("🎯 Sinyal Pagi")],
        [KeyboardButton("🌆 BSJP Sore"), KeyboardButton("🌊 Swing Trade")],
        [KeyboardButton("💼 Portfolio"), KeyboardButton("⚙️ Setting")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

SINYAL_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔄 Update Sinyal Pagi"), KeyboardButton("🎯 Sinyal Pagi Ini")],
        [KeyboardButton("📈 Cek Performa AI"), KeyboardButton("🔙 Kembali")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

BSJP_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔄 Update BSJP Sore"), KeyboardButton("🌆 BSJP Hari Ini")],
        [KeyboardButton("ℹ️ Bantuan BSJP"), KeyboardButton("🔙 Kembali")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

SWING_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔄 Update Swing Data"), KeyboardButton("🌊 Swing Hari Ini")],
        [KeyboardButton("ℹ️ Bantuan Swing"), KeyboardButton("🔙 Kembali")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

def _reply(text: str):
    """Helper: tambahkan keyboard utama ke setiap reply."""
    return {'text': text, 'reply_markup': MAIN_KEYBOARD}


async def handle_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tombol Reply Keyboard yang ditekan user."""
    text = update.message.text.strip()

    # --- MENU UTAMA ---
    if text == "📊 Market":
        await cmd_market(update, context)
        
    elif text == "🎯 Sinyal Pagi":
        await update.message.reply_text("🎯 <b>Pusat Komando Sinyal Pagi</b>\nPilih menu di bawah:", parse_mode='HTML', reply_markup=SINYAL_KEYBOARD)
    elif text == "🌆 BSJP Sore":
        await update.message.reply_text("🌆 <b>Pusat Komando BSJP Sore</b>\nPilih menu di bawah:", parse_mode='HTML', reply_markup=BSJP_KEYBOARD)
    elif text == "🌊 Swing Trade":
        await update.message.reply_text("🌊 <b>Pusat Komando Swing Trade</b>\nPilih menu di bawah:", parse_mode='HTML', reply_markup=SWING_KEYBOARD)
    elif text == "🔙 Kembali":
        await update.message.reply_text("🏠 <b>Kembali ke Menu Utama</b>", parse_mode='HTML', reply_markup=MAIN_KEYBOARD)

    # --- SUB-MENU: SINYAL PAGI ---
    elif text == "🎯 Sinyal Pagi Ini":
        await cmd_sinyal(update, context)
    elif text == "🔄 Update Sinyal Pagi":
        await update.message.reply_text("⏳ Update Sinyal Pagi (Fetch Fresh)...")
        await cmd_sinyal(update, context)
    elif text == "📈 Cek Performa AI":
        await cmd_performance_check(update, context)

    # --- SUB-MENU: BSJP SORE ---
    elif text == "🌆 BSJP Hari Ini":
        await cmd_bsjp(update, context)
    elif text == "🔄 Update BSJP Sore":
        await update.message.reply_text("⏳ Manual trigger update BSJP (pastikan market buka)...")
        await cmd_bsjp(update, context)
    elif text == "ℹ️ Bantuan BSJP":
        await update.message.reply_text(
            "<b>Beli Sore Jual Pagi (BSJP):</b>\n"
            "Strategi momentum cepat. Beli saham ini sekitar jam <b>15:50</b> WIB, lalu antri jual besok pagi saat market buka (09:00 - 09:30).",
            parse_mode='HTML', reply_markup=BSJP_KEYBOARD
        )
        
    # --- SUB-MENU: SWING TRADE ---
    elif text == "🌊 Swing Hari Ini":
        await cmd_swing(update, context)
    elif text == "🔄 Update Swing Data":
        await update.message.reply_text("⏳ Manual trigger update Swing (Running scan)...")
        await cmd_swing(update, context)
    elif text == "ℹ️ Bantuan Swing":
        await update.message.reply_text(
            "<b>Swing Trade:</b>\n"
            "Strategi hold saham selama <b>3-7 hari</b> ke depan.\n"
            "Perhatikan area Support/Resisten untuk melakukan cicil beli bertahap (max 3x peluru).",
            parse_mode='HTML', reply_markup=SWING_KEYBOARD
        )

    # --- MENU LAINNYA ---
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
                "🤖 Gunakan tombol menu yang tersedia, atau ketik /help",
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
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=MAIN_KEYBOARD)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Daftar command."""
    text = (
        "📖 *PANDUAN COMMAND*\n\n"
        "*Analisa & Sinyal:*\n"
        "/a_`KODE` — Analisa AI lengkap (contoh: /a_BBCA)\n"
        "/c_`KODE` — Chart teknikal saja (contoh: /c_BBCA)\n"
        "/bandingkan `K1 K2` — Bandingkan 2 saham\n"
        "/sinyal — Sinyal Pagi (Hold harian)\n"
        "/bsjp — Sinyal BSJP (Beli sore jual pagi)\n"
        "/swing — Sinyal Swing (Hold 3-7 hari)\n"
        "/market — Kondisi pasar IHSG & Global\n\n"
        "*Portfolio:*\n"
        "/portfolio — Lihat posisi berjalan\n"
        "/pnl — Profit & Loss hari ini\n"
        "/beli `KODE LOT HARGA` — Input posisi beli\n"
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
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=MAIN_KEYBOARD)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode='HTML', reply_markup=MAIN_KEYBOARD)


async def _send_top_chart(result: dict, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kirim chart teknikal otomatis untuk saham #1 direkomendasikan."""
    try:
        from loguru import logger
        if not result or 'ranking' not in result or not result['ranking']:
            return
            
        top_kode = result['ranking'][0]['kode']
        from analysis.charts import generate_chart
        
        chart_path = generate_chart(top_kode)
        if chart_path:
            with open(chart_path, 'rb') as f:
                await update.message.reply_photo(
                    photo=f, 
                    caption=f"📈 <b>{top_kode}</b> - Top #1 Sinyal Pagi Ini", 
                    parse_mode='HTML'
                )
    except Exception as e:
        from loguru import logger
        logger.error(f"Error _send_top_chart: {e}")


async def cmd_sinyal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sinyal hari ini (diambil dari watchlist_harian hasil scanner)."""
    msg = await update.message.reply_text("🎯 Mengambil rekomendasi Top 10 hari ini...", reply_markup=MAIN_KEYBOARD)

    try:
        from ai.agents import run_full_analysis
        
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
        lines = [f"🎯 <b>SINYAL HARI INI</b> — {tanggal_sekarang}\n<i>{source_text}</i>\n"]
        rank_emoji = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}

        for i, r in enumerate(results, 1):
            e = r.get('emoji', '❓')
            close = r.get('close', 0)
            line = f"{rank_emoji.get(i, str(i)+'.')} <b>{r['kode']}</b> {e} {r['label']} ({r['total']:.1f} pt) | /c_{r['kode']}"
            line += f"\n   💰 Harga: Rp {close:,.0f}"
            
            if r.get('entry_low'):
                line += f"\n   📈 Entry: Rp {r['entry_low']:,.0f} - {r['entry_high']:,.0f}"
                line += f"\n   🎯 TP1: Rp {r['tp1']:,.0f} ({r['tp1_pct']:+.1f}%) | TP2: Rp {r['tp2']:,.0f} ({r['tp2_pct']:+.1f}%)"
                line += f"\n   🛡️ CL: Rp {r['cl']:,.0f} ({r['cl_pct']:+.1f}%)"
            
            lines.append(line)

        lines.append("\n💡 /c_KODE = Chart | /a_KODE = Analisa AI")
        text = "\n".join(lines)

        result = run_full_analysis(stocks)
        result['track_record'] = get_track_record(30)
        
        # Kirim chart top #1 dulu
        await _send_top_chart(result, update, context)

        text = format_briefing_pagi(result)
        try:
            await msg.delete()
        except:
            pass
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=SINYAL_KEYBOARD)
    except Exception as e:
        logger.error(f"Error Sinyal: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=SINYAL_KEYBOARD)


async def cmd_bsjp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """BSJP (Beli Sore Jual Pagi) — Quick screening for overnight trades."""
    try:
        from analysis.bsjp_screening import run_bsjp_screening, get_bsjp_candidates
        from bot.formatter import format_bsjp

        msg = await update.message.reply_text("⏳ Mencari kandidat BSJP (Volume Spike)...", reply_markup=BSJP_KEYBOARD)

        candidates = get_bsjp_candidates(200)
        results = run_bsjp_screening(candidates)

        if not results:
            await update.message.reply_text("🌆 Tidak ada saham yang memenuhi kriteria BSJP saat ini.", reply_markup=BSJP_KEYBOARD)
            return

        # Kirim chart top #1 bsjp
        top_kode = results[0]['kode']
        from utils.chart_generator import generate_advanced_chart
        chart_path = generate_advanced_chart(top_kode, days=60)
        if chart_path:
            try:
                with open(chart_path, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=photo,
                        caption=f"📈 BSJP Top #1: <b>{top_kode}</b>",
                        parse_mode='HTML'
                    )
            except:
                pass

        text = format_bsjp(results)
        try:
            await msg.delete()
        except:
            pass
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=BSJP_KEYBOARD)
    except Exception as e:
        logger.error(f"Error BSJP: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=BSJP_KEYBOARD)


async def cmd_swing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Swing Trade (Hold 3-7 hari) — Trend following & Accumulation screening."""
    try:
        from analysis.swing_screening import run_swing_screening, get_swing_candidates
        from bot.formatter import format_swing

        msg = await update.message.reply_text("⏳ Menganalisa setup Swing Trade (hold mingguan)...", reply_markup=SWING_KEYBOARD)

        candidates = get_swing_candidates(150)
        results = run_swing_screening(candidates)

        if not results:
            await update.message.reply_text("🌊 Tidak ada setup swing yang terkonfirmasi hari ini.", reply_markup=SWING_KEYBOARD)
            return

        # Kirim chart top #1 swing
        top_kode = results[0]['kode']
        from utils.chart_generator import generate_advanced_chart
        chart_path = generate_advanced_chart(top_kode, days=150)
        if chart_path:
            try:
                with open(chart_path, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=photo,
                        caption=f"📈 Swing Top #1: <b>{top_kode}</b>",
                        parse_mode='HTML'
                    )
            except Exception as e:
                logger.error(f"Gagal mengirim chart Swing {top_kode}: {e}")
            finally:
                import os
                if os.path.exists(chart_path):
                    os.remove(chart_path)

        text = format_swing(results)
        try:
            await msg.delete()
        except:
            pass
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        logger.error(f"Error Swing: {e}")
        await update.message.reply_text(f"❌ Error Swing: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


async def cmd_quick_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /c_KODE -> kirim GAMBAR CHART saja (tanpa AI analysis)."""
    text = update.message.text
    if "@" in text:
        text = text.split("@")[0]
    kode = text.replace("/c_", "", 1).replace("/C_", "", 1).upper()
    
    if not kode:
        return

    await update.message.reply_text(f"📈 Generating chart <b>{kode}</b>...", parse_mode='HTML')
    
    try:
        from utils.chart_generator import generate_advanced_chart
        from analysis.scoring import calculate_composite_score
        
        # Hitung skor teknikal cepat untuk dapatkan rentang harga
        score_data = calculate_composite_score(kode)
        
        chart_path = generate_advanced_chart(kode, days=150)
        if chart_path:
            try:
                caption = (
                    f"📈 <b>{kode}</b> — Chart Teknikal\n"
                    f"Status: {score_data.get('emoji', '❓')} {score_data.get('label', 'UNKNOWN')}\n"
                    f"─────────────────────\n"
                )
                
                # Tambahkan insight cepat (mini reasoning) - Fitur Pintar
                tech_details = score_data.get('d1_technical', {}).get('details', [])
                if tech_details:
                    caption += f"📌 <b>Insight Cepat:</b> {tech_details[0]}\n"
                    if len(tech_details) > 1:
                        caption += f"   • {tech_details[1]}\n"
                    caption += f"─────────────────────\n"

                if score_data.get('label') == 'SKIP':
                    caption += f"⚠️ <b>STATUS SKIP - SANGAT BERISIKO</b>\n─────────────────────\n"
                    
                if score_data.get('entry_low'):
                    tp1 = score_data.get('tp1', 0)
                    tp2 = score_data.get('tp2', 0)
                    sl = score_data.get('cl', 0)
                    caption += (
                        f"[ Harga  ] Rp {score_data.get('close', 0):,.0f}\n"
                        f"[ Entry  ] Rp {score_data['entry_low']:,.0f} - {score_data['entry_high']:,.0f}\n"
                        f"[ TP1    ] Rp {tp1:,.0f} ({score_data.get('tp1_pct', 0):+.1f}%)\n"
                        f"[ TP2    ] Rp {tp2:,.0f} ({score_data.get('tp2_pct', 0):+.1f}%)\n"
                        f"[ SL     ] Rp {sl:,.0f} ({score_data.get('cl_pct', 0):+.1f}%)\n"
                        f"─────────────────────\n"
                    )

                
                caption += f"💡 Ketik /a_{kode} untuk analisa AI lengkap"

                with open(chart_path, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=photo,
                        caption=caption,
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.error(f"Gagal mengirim chart {kode}: {e}")
                await update.message.reply_text(f"❌ Gagal mengirim chart {kode}", reply_markup=MAIN_KEYBOARD)
            finally:
                import os
                if os.path.exists(chart_path):
                    os.remove(chart_path)
        else:
            await update.message.reply_text(
                f"❌ Data chart <b>{kode}</b> tidak tersedia. Pastikan kode saham benar.",
                parse_mode='HTML', reply_markup=MAIN_KEYBOARD
            )
    except Exception as e:
        logger.error(f"Error quick chart {kode}: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


async def cmd_quick_analisa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /a_KODE -> redirect ke /analisa KODE (5 Agent AI lengkap)."""
    text = update.message.text
    if "@" in text:
        text = text.split("@")[0]
    kode = text.replace("/a_", "", 1).replace("/A_", "", 1).upper()
    
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
        parse_mode='HTML', reply_markup=MAIN_KEYBOARD,
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
                            caption=f"📈 <b>{kode}</b> — Auto-Chart (EMA, BB, Volume, MACD, StochRSI)",
                            parse_mode="HTML"
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

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=MAIN_KEYBOARD)


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
        lines.append(f"🏆 <b>Pemenang: {winner}</b>")

        await update.message.reply_text("\n".join(lines), parse_mode='HTML', reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kondisi pasar mengunduh data terbaru secara real-time."""
    message = await update.message.reply_text(
        "⏳ <b>Mengambil data pasar terbaru...</b>\nMohon tunggu beberapa detik.",
        parse_mode='HTML'
    )
    
    try:
        from data.fetcher.macro_fetcher import fetch_and_save_macro
        from datetime import datetime
        import pytz

        # Ambil data terbaru langsung dari internet
        logger.info("Market Command: Fetching fresh macro data...")
        m = fetch_and_save_macro()
        
        try:
            await message.delete()
        except:
            pass

        if not m:
            await update.message.reply_text("❌ Gagal mengunduh data makro.", reply_markup=MAIN_KEYBOARD)
            return

        label = m.get('market_label', 'UNKNOWN')
        emoji_map = {'BULLISH': '🟢', 'MIXED': '🟡', 'BEARISH': '🔴', 'EXTREME': '⚫'}
        
        tz = pytz.timezone('Asia/Jakarta')
        now = datetime.now(tz).strftime('%d %b %Y | %H:%M WIB')

        text = (
            f"📊 <b>KONDISI PASAR SAAT INI</b>\n"
            f"🕒 {now}\n\n"
            f"{emoji_map.get(label, '❓')} <b>{label}</b>\n\n"
            f"IHSG      : {m.get('ihsg_change', 0):+.2%}\n"
            f"Nikkei    : {m.get('nikkei_change', 0):+.2%}\n"
            f"Hang Seng : {m.get('hsi_change', 0):+.2%}\n"
            f"STI       : {m.get('sti_change', 0):+.2%}\n"
            f"Gold      : {m.get('gold_change', 0):+.2%}\n"
            f"Oil       : {m.get('oil_change', 0):+.2%}"
        )
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        logger.error(f"Error cmd_market: {e}")
        try:
            await message.delete()
        except:
            pass
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

        await update.message.reply_text(text, parse_mode='HTML', reply_markup=MAIN_KEYBOARD)
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

        await update.message.reply_text(text, parse_mode='HTML', reply_markup=MAIN_KEYBOARD)
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

        await update.message.reply_text(text, parse_mode='HTML', reply_markup=MAIN_KEYBOARD)
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
    modal = get_modal_awal()
    text = (
        f"⚙️ *SETTING*\n\n"
        f"Modal awal  : Rp {modal:,.0f}\n"
        f"Max posisi  : {MAX_POSISI}\n"
        f"Test stocks : {', '.join(TEST_STOCKS)}\n\n"
        f"_Ubah modal dengan perintah /setmodal <angka>._"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Baca Panduan Lengkap (/help)", callback_data="help")]
    ])
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)


async def cmd_setmodal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set modal awal portofolio."""
    try:
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ Format: /setmodal 5000000", reply_markup=MAIN_KEYBOARD)
            return
            
        nominal = float(args[0].replace('.', '').replace(',', ''))
        if nominal < 100000:
            await update.message.reply_text("⚠️ Modal minimal Rp 100.000", reply_markup=MAIN_KEYBOARD)
            return
            
        set_modal_awal(nominal)
        await update.message.reply_text(f"✅ Modal berhasil diubah menjadi: Rp {nominal:,.0f}", reply_markup=MAIN_KEYBOARD)
    except ValueError:
        await update.message.reply_text("⚠️ Nominal harus berupa angka valid.", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        logger.error(f"Error setmodal: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


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

async def cmd_performance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler Cek Performa AI (Fase 13)"""
    try:
        from analysis.performance import get_ai_performance
        from bot.formatter import format_ai_performance
        
        msg = await update.message.reply_text("⏳ Menghitung statistik win-rate AI 1-30 hari...", reply_markup=SINYAL_KEYBOARD)
        
        # Hitung untuk 1, 3, 7, 30 hari
        data_1d = get_ai_performance(1)
        data_3d = get_ai_performance(3)
        data_7d = get_ai_performance(7)
        data_30d = get_ai_performance(30)
        
        text = format_ai_performance({
            '1 Hari': data_1d,
            '3 Hari': data_3d,
            '7 Hari': data_7d,
            '30 Hari': data_30d
        })
        
        try:
            await msg.delete()
        except:
            pass
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=SINYAL_KEYBOARD)
    except Exception as e:
        logger.error(f"Error cmd_performance_check: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=SINYAL_KEYBOARD)
