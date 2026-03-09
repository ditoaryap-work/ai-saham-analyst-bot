"""
bot/commands.py — Telegram command handlers + Reply Keyboard.

Menu tombol di bawah chat:
Row 1: [ 📊 Market ] [ 🎯 Sinyal Hari Ini ]
Row 2: [ 💼 Portfolio ] [ 📈 Track Record ]
Row 3: [ 🔍 Analisa Saham ] [ ⚙️ Setting ]
"""

import sys
from pathlib import Path

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
        "/market — Kondisi pasar\n\n"
        "*Portfolio:*\n"
        "/portfolio — Lihat posisi\n"
        "/pnl — P&L hari ini\n"
        "/beli `KODE LOT HARGA` — Input beli\n"
        "/jual `KODE LOT HARGA` — Input jual\n"
        "/track — Track record 30 hari\n\n"
        "💡 *Atau gunakan tombol menu di bawah!*"
    )
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)


async def cmd_sinyal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sinyal hari ini (quick scoring tanpa AI agent penuh)."""
    await update.message.reply_text("🔍 Menghitung skor saham...", reply_markup=MAIN_KEYBOARD)

    try:
        results = []
        for kode in TEST_STOCKS:
            score = calculate_composite_score(kode)
            results.append(score)

        results.sort(key=lambda x: x['total'], reverse=True)

        lines = ["🎯 *SINYAL HARI INI*\n"]
        rank_emoji = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}

        for i, r in enumerate(results, 1):
            e = r.get('emoji', '❓')
            lines.append(
                f"{rank_emoji.get(i, str(i)+'.')} {e} *{r['kode']}* — {r['label']} ({r['total']}/100)\n"
                f"   T:{r['d1_technical']['score']:.0f} V:{r['d2_volume']['score']:.0f} "
                f"F:{r['d3_fundamental']['score']:.0f} S:{r['d4_sentiment']['score']:.0f}"
            )

        lines.append("\n💡 Ketik /analisa KODE untuk detail lengkap AI")
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        logger.error(f"Error sinyal: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=MAIN_KEYBOARD)


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
        else:
            text = f"❌ Gagal menganalisa {kode}. Pastikan kode saham benar."
    except Exception as e:
        logger.error(f"Error analisa {kode}: {e}")
        text = f"❌ Error analisa {kode}: {str(e)[:150]}"

    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


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
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
