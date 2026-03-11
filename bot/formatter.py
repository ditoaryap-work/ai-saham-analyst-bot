"""
bot/formatter.py — Format pesan Telegram.

3 format utama sesuai master prompt:
1. Briefing Pagi (07:00)
2. Update Siang (12:00)
3. Sinyal Sore BSJP (16:15)
+ On-demand: /analisa, /portfolio, /pnl
"""

import sys
from pathlib import Path
from datetime import date, datetime
import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


HARI = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']


def _jakarta_now():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def _hari_ini() -> str:
    return HARI[_jakarta_now().weekday()]


def _tanggal() -> str:
    return _jakarta_now().strftime("%d %B %Y")


def _emoji_change(change: float) -> str:
    return "🟢" if change > 0 else ("🔴" if change < 0 else "⚪")


def _emoji_label(label: str) -> str:
    return {"AMAN": "🔵", "MOMENTUM": "🟠", "SPEKULATIF": "🟡", "SKIP": "❌"}.get(label, "❓")


# ═══════════════════════════════════════════════════════
# 1. BRIEFING PAGI (07:00)
# ═══════════════════════════════════════════════════════

def format_briefing_pagi(analysis_result: dict) -> str:
    """Format briefing pagi sesuai master prompt."""
    market = analysis_result.get('market', {})
    signals = analysis_result.get('signals', {})
    track = analysis_result.get('track_record', {})

    lines = [
        f"🌅 BRIEFING SAHAM — {_hari_ini()}, {_tanggal()}",
        f"⏰ 07.00 WIB | IDX AI Trading Assistant",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📊 KONDISI PASAR HARI INI",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Market narrative
    narrative = market.get('narrative', '')
    if narrative:
        lines.append(narrative[:400])
    lines.append("")

    # Top signals
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🎯 <b>TOP SINYAL HARI INI</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ])

    rank_emoji = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}

    sorted_signals = sorted(
        signals.items(),
        key=lambda x: x[1].get('score', {}).get('total', 0),
        reverse=True,
    )

    for i, (kode, data) in enumerate(sorted_signals, 1):
        score = data.get('score', {})
        final = data.get('final', {})
        debate = data.get('debate', {})

        label = score.get('label', 'SKIP')
        emoji = _emoji_label(label)
        total = score.get('total', 0)
        close = score.get('close', 0)
        conf = final.get('confidence', debate.get('confidence', 0))

        lines.append("")
        lines.append(f"{rank_emoji.get(i, f'{i}.')} <b>{kode}</b> {emoji} {label} | Skor: {total}/100 | /c_{kode}")
        lines.append(f"   💰 Harga   : Rp {close:,.0f}")

        if final.get('entry_low') and final.get('entry_high'):
            lines.append(f"   📈 Entry   : Rp {final['entry_low']:,.0f} - {final['entry_high']:,.0f}")
            target = final.get('target', 0)
            stoploss = final.get('stoploss', 0)
            tp_pct = ((target - close) / close * 100) if close > 0 and target > 0 else 0
            cl_pct = ((stoploss - close) / close * 100) if close > 0 and stoploss > 0 else 0
            lines.append(f"   🎯 TP: Rp {target:,.0f} ({tp_pct:+.1f}%)")
            lines.append(f"   🛡️ CL: Rp {stoploss:,.0f} ({cl_pct:+.1f}%)")
            if final.get('rr_ratio'):
                lines.append(f"   ⚖️ R/R     : 1 : {final['rr_ratio']:.1f}")

        if final.get('alasan'):
            lines.append(f"   🔍 {final['alasan'][:120]}")
        lines.append(f"   📊 Confidence: {conf}%")
        lines.append("───────────────────────")

    # Track record
    if track and track.get('total_trades', 0) > 0:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📈 TRACK RECORD (30 hari)",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"Hit rate    : {track['hit_rate']:.0%} ({track['wins']}/{track['total_trades']})",
            f"Avg return  : {track['avg_return']:+.1%}",
        ])
        if track.get('best'):
            lines.append(f"Best win    : {track['best']['kode']} {track['best']['pnl_pct']:+.1%}")
        if track.get('worst'):
            lines.append(f"Worst loss  : {track['worst']['kode']} {track['worst']['pnl_pct']:+.1%}")

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💬 Klik tulisan biru (misal /c_BBCA) untuk analisanya",
        "⚠️ Bukan rekomendasi keuangan. DYOR selalu.",
    ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 2. UPDATE SIANG (12:00)
# ═══════════════════════════════════════════════════════

def format_update_siang(sinyal_pagi: dict, portfolio: dict = None) -> str:
    """Format update siang."""
    lines = [
        f"☀️ UPDATE SIANG — {_tanggal()} | 12.00 WIB",
        "",
    ]

    # Status sinyal pagi
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🔄 STATUS SINYAL PAGI",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ])

    for i, (kode, data) in enumerate(sinyal_pagi.items(), 1):
        score = data.get('score', {})
        final = data.get('final', {})
        close = score.get('close', 0)

        # Status emoji
        if final.get('entry_low') and close >= final.get('target', float('inf')):
            status = "✅ HIT TARGET"
        elif final.get('stoploss') and close <= final.get('stoploss', 0):
            status = "❌ HIT SL"
        else:
            status = "⏳ MONITOR"

        lines.append(f"{i}. {kode} : Rp {close:,.0f} {status}")

    # Portfolio alert
    if portfolio:
        alerts = portfolio.get('alerts', [])
        if alerts:
            lines.append("")
            lines.append("🔔 ALERTS:")
            for a in alerts[:3]:
                lines.append(f"   {a['message'][:100]}")

    lines.extend([
        "",
        "💬 /analisa [KODE] untuk detail real-time",
    ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 3. SINYAL SORE BSJP (16:15)
# ═══════════════════════════════════════════════════════

def format_sinyal_sore(analysis_result: dict, review_pagi: dict = None) -> str:
    """Format sinyal sore BSJP (Beli Sore Jual Pagi)."""
    signals = analysis_result.get('signals', {})

    lines = [
        f"🌆 SINYAL BSJP SORE — {_tanggal()} | 16.15 WIB",
        "   (Beli sore ini → target jual besok pagi)",
        "",
    ]

    # Review sinyal pagi (jika ada)
    if review_pagi:
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📊 REVIEW SINYAL HARI INI",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ])
        for kode, data in review_pagi.items():
            pnl = data.get('daily_pnl', 0)
            emoji = "✅" if pnl > 0 else "❌"
            lines.append(f"   {kode}: {pnl:+.1%} {emoji}")

        lines.append("")

    # Sinyal BSJP baru
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🎯 SINYAL BSJP MALAM INI",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ])

    sorted_signals = sorted(
        signals.items(),
        key=lambda x: x[1].get('score', {}).get('total', 0),
        reverse=True,
    )

    for i, (kode, data) in enumerate(sorted_signals, 1):
        score = data.get('score', {})
        final = data.get('final', {})
        debate = data.get('debate', {})

        label = score.get('label', 'SKIP')
        emoji = _emoji_label(label)
        total = score.get('total', 0)

        lines.append(f"\n{i}. <b>{kode}</b> {emoji} {label} ({total}/100) | /c_{kode}")

        if final.get('entry_low'):
            lines.append(f"   📈 Entry: Rp {final['entry_low']:,.0f}-{final['entry_high']:,.0f}")
            lines.append(f"   🎯 Target: Rp {final.get('target', 0):,.0f} | SL: Rp {final.get('stoploss', 0):,.0f}")

        if debate.get('bull_arguments'):
            lines.append(f"   📈 Bull: {debate['bull_arguments'][0][:80]}")
        if debate.get('bear_arguments'):
            lines.append(f"   📉 Bear: {debate['bear_arguments'][0][:80]}")

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💬 /c_KODE = Chart | /a_KODE = Analisa AI",
        "⚠️ Bukan rekomendasi keuangan. DYOR selalu.",
    ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 4. BSJP (Beli Sore Jual Pagi)
# ═══════════════════════════════════════════════════════

def format_bsjp(bsjp_results: list) -> str:
    """Format output BSJP recommendations."""
    lines = [
        f"🌆 <b>SINYAL BSJP</b> — {_tanggal()} | {_jakarta_now().strftime('%H:%M')} WIB",
        "   (Beli ~15:50 → target jual besok pagi)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🎯 <b>TOP BSJP PICKS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    rank_emoji = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣",
                  6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}

    for i, r in enumerate(bsjp_results, 1):
        kode = r['kode']
        close = r.get('close', 0)
        score = r.get('bsjp_score', 0)
        vol_ratio = r.get('vol_ratio', 0)
        daily_chg = r.get('daily_change', 0)

        lines.append("")
        lines.append(f"{rank_emoji.get(i, f'{i}.')} <b>{kode}</b> | Skor: {score} | /c_{kode}")
        lines.append(f"   💰 Harga: Rp {close:,.0f} ({daily_chg:+.1%}) | Vol: {vol_ratio:.1f}x")
        lines.append(f"   📈 Entry: Rp {r.get('entry', close):,.0f}")
        lines.append(f"   🎯 TP1: Rp {r['tp1']:,.0f} ({r['tp1_pct']:+.1f}%) | TP2: Rp {r['tp2']:,.0f} ({r['tp2_pct']:+.1f}%)")
        lines.append(f"   🛡️ CL: Rp {r['cl']:,.0f} ({r['cl_pct']:+.1f}%)")
        lines.append("───────────────────────")

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "⏰ Beli sebelum market tutup (~15:50)",
        "💬 /c_KODE = Chart | /a_KODE = Analisa AI",
        "⚠️ Bukan rekomendasi keuangan. DYOR selalu.",
    ])

    return "\n".join(lines)

def format_analisa(kode: str, data: dict) -> str:
    """Format /analisa [KODE] response."""
    score = data.get('score', {})
    final = data.get('final', {})
    debate = data.get('debate', {})
    tech = data.get('technical', {})
    d1 = score.get('d1_technical', {})
    d2 = score.get('d2_volume', {})
    d3 = score.get('d3_fundamental', {})
    d4 = score.get('d4_sentiment', {})

    label = score.get('label', 'SKIP')
    emoji = _emoji_label(label)

    lines = [
        f"📊 ANALISA <b>{kode}</b> — {_tanggal()}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"",
        f"{emoji} <b>{kode}</b> → {label} ({score.get('total', 0)}/100)",
        f"💰 Harga: Rp {score.get('close', 0):,.0f}",
        "",
        "📊 SCORING BREAKDOWN:",
        f"   Teknikal:    {d1.get('score', 0):.0f}/25",
        f"   Vol/Action:  {d2.get('score', 0):.0f}/25",
        f"   Fundamental: {d3.get('score', 0):.0f}/25",
        f"   Sentimen:    {d4.get('score', 0):.0f}/25",
        "",
        "🗣️ DEBATE:",
        f"   Verdict: {debate.get('debate_verdict', '-')} (conf: {debate.get('confidence', 0)}%)",
    ]

    if debate.get('bull_arguments'):
        lines.append("   📈 BULL:")
        for arg in debate['bull_arguments'][:3]:
            lines.append(f"      • {arg[:100]}")

    if debate.get('bear_arguments'):
        lines.append("   📉 BEAR:")
        for arg in debate['bear_arguments'][:3]:
            lines.append(f"      • {arg[:100]}")

    if final.get('entry_low'):
        lines.extend([
            "",
            "🎯 SIGNAL:",
            f"   Entry   : Rp {final['entry_low']:,.0f} - {final['entry_high']:,.0f}",
            f"   Target  : Rp {final.get('target', 0):,.0f}",
            f"   Stoploss: Rp {final.get('stoploss', 0):,.0f}",
        ])

    if final.get('alasan'):
        lines.extend(["", f"💡 {final['alasan'][:200]}"])
    if final.get('risk_warning'):
        lines.append(f"⚠️ {final['risk_warning'][:150]}")

    lines.append("\n⚠️ Bukan rekomendasi keuangan. DYOR selalu.")
    return "\n".join(lines)


def format_portfolio(summary: dict) -> str:
    """Format /portfolio response."""
    lines = [
        "<b>💼 PORTFOLIO</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 Total   : Rp {summary.get('total', 0):,.0f}",
        f"💵 Cash    : Rp {summary.get('cash', 0):,.0f}",
        f"📈 Invested: Rp {summary.get('invested', 0):,.0f}",
        f"📊 Return  : {summary.get('return_pct', 0):+.1%}",
        f"📦 Posisi  : {summary.get('n_positions', 0)}/{5}",
        "",
    ]

    for p in summary.get('positions', []):
        emoji = "🟢" if p['unrealized'] >= 0 else "🔴"
        lines.append(
            f"{emoji} {p['kode']}: {p['lot']} lot @ {p['harga_beli']:,.0f} "
            f"→ {p['harga_now']:,.0f} ({p['unrealized_pct']:+.1%})"
        )

    if not summary.get('positions'):
        lines.append("Belum ada posisi aktif.")

    return "\n".join(lines)


def format_track_record(track: dict) -> str:
    """Format /track response."""
    lines = [
        "<b>📈 TRACK RECORD (30 hari)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"Total trades : {track.get('total_trades', 0)}",
        f"Hit rate     : {track.get('hit_rate', 0):.0%} ({track.get('wins', 0)}/{track.get('total_trades', 0)})",
        f"Avg return   : {track.get('avg_return', 0):+.1%}",
        f"Avg win      : {track.get('avg_win', 0):+.1%}",
        f"Avg loss     : {track.get('avg_loss', 0):+.1%}",
        f"Total P&L    : Rp {track.get('total_pnl', 0):,.0f}",
    ]

    if track.get('best'):
        lines.append(f"Best  : {track['best']['kode']} {track['best']['pnl_pct']:+.1%}")
    if track.get('worst'):
        lines.append(f"Worst : {track['worst']['kode']} {track['worst']['pnl_pct']:+.1%}")

    if track.get('total_trades', 0) == 0:
        lines.append("\nBelum ada trade yang tercatat.")

    return "\n".join(lines)
