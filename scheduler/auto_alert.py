"""
scheduler/auto_alert.py — Institutional Grade (Fitur A: Auto-Target Alert)

Mengecek harga realtime setiap 15 menit, TAPI HANYA untuk:
1. Saham di portofolio (posisi_aktif)
2. Saham rekomendasi Sinyal Pagi hari ini (sinyal_history)

Tujuan:
- Hemat RAM & API Limit (hanya fetch ~10-20 saham, bukan 800).
- Ping user via Telegram jika HIT TP1, TP2, atau SL di tengah jam kerja.
"""

import sys
from pathlib import Path
from datetime import date
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db
from data.fetcher.stock_fetcher import fetch_and_save_batch

def init_alert_db():
    db.execute("""
        CREATE TABLE IF NOT EXISTS alerts_sent (
            tanggal DATE NOT NULL,
            kode TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            PRIMARY KEY (tanggal, kode, alert_type)
        )
    """)

def check_and_send_alert(bot, chat_id, kode, alert_type, message):
    today = date.today().isoformat()
    # Cek apakah sudah pernah kirim alert ini hari ini
    rows = db.execute(
        "SELECT 1 FROM alerts_sent WHERE tanggal = ? AND kode = ? AND alert_type = ?",
        (today, kode, alert_type)
    )
    if not rows:
        # Belum pernah kirim
        import asyncio
        asyncio.create_task(bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML'))
        db.execute(
            "INSERT INTO alerts_sent (tanggal, kode, alert_type) VALUES (?, ?, ?)",
            (today, kode, alert_type)
        )
        logger.info(f"Auto-Alert Sent: {kode} - {alert_type}")


def run_auto_target_alert(bot, chat_id):
    """Jalankan pengecekan target harga dan kirim alert jika hit."""
    init_alert_db()
    today = date.today().isoformat()
    
    # 1. Kumpulkan daftar saham yang perlu dicek (Posisi Aktif + Sinyal Pagi)
    posisi_rows = db.execute("SELECT DISTINCT kode FROM posisi_aktif")
    sinyal_rows = db.execute(
        "SELECT DISTINCT kode FROM sinyal_history WHERE tanggal = ? AND status = 'ACTIVE'",
        (today,)
    )
    
    kodes = set()
    if posisi_rows:
        kodes.update([r['kode'] for r in posisi_rows])
    if sinyal_rows:
        kodes.update([r['kode'] for r in sinyal_rows])
        
    candidates = list(kodes)
    if not candidates:
        return # Tidak ada yang perlu dicek
        
    # 2. Fetch harga live HANYA untuk kandidat tersebut
    logger.info(f"Auto-Alert: Fetching fresh price for {len(candidates)} active tickers...")
    fetch_and_save_batch(candidates, include_info=False)
    
    # 3. Evaluasi Posisi Aktif
    if posisi_rows:
        rows = db.execute("SELECT * FROM posisi_aktif")
        for p in rows:
            kode = p['kode']
            # Get latest price
            latest = db.execute("SELECT close FROM harga_historis WHERE kode = ? ORDER BY tanggal DESC LIMIT 1", (kode,))
            if not latest: continue
            
            harga_now = latest[0]['close']
            
            if p['stoploss_set'] and harga_now <= p['stoploss_set']:
                msg = f"⚠️ <b>PORTFOLIO ALERT</b>\n{kode} kena STOPLOSS!\nHarga Rp {harga_now:,.0f} ≤ SL Rp {p['stoploss_set']:,.0f}. SEGERA JUAL!"
                check_and_send_alert(bot, chat_id, kode, "PORTFOLIO_SL", msg)
                
            if p['target_set'] and harga_now >= p['target_set']:
                msg = f"🎯 <b>PORTFOLIO ALERT</b>\n{kode} HIT TARGET!\nHarga Rp {harga_now:,.0f} ≥ Target Rp {p['target_set']:,.0f}. Pertimbangkan take profit."
                check_and_send_alert(bot, chat_id, kode, "PORTFOLIO_TP", msg)

    # 4. Evaluasi Rekomendasi Hari Ini
    if sinyal_rows:
        rows = db.execute(
            "SELECT kode, entry_high, entry_low, target as tp1, stoploss as cl FROM sinyal_history WHERE tanggal = ? AND status = 'ACTIVE'",
            (today,)
        )
        for s in rows:
            kode = s['kode']
            latest = db.execute("SELECT close FROM harga_historis WHERE kode = ? ORDER BY tanggal DESC LIMIT 1", (kode,))
            if not latest: continue
            
            harga_now = latest[0]['close']
            tp1 = s['tp1']
            tp2 = round(tp1 * 1.05) if tp1 else 0
            cl = s['cl']
            
            # Cek Break SL
            if cl and harga_now <= cl:
                msg = f"⚠️ <b>SINYAL ALERT</b>\nRekomendasi Sinyal {kode} kena STOPLOSS!\nHarga Rp {harga_now:,.0f} ≤ SL Rp {cl:,.0f}."
                check_and_send_alert(bot, chat_id, kode, "SINYAL_SL", msg)
            # Cek Break TP2
            elif tp2 and harga_now >= tp2:
                msg = f"🚀 <b>SINYAL ALERT</b>\nRekomendasi Sinyal {kode} terbang HIT TP2!\nHarga Rp {harga_now:,.0f} ≥ TP2 Rp {tp2:,.0f}."
                check_and_send_alert(bot, chat_id, kode, "SINYAL_TP2", msg)
            # Cek Break TP1
            elif tp1 and harga_now >= tp1:
                msg = f"🎯 <b>SINYAL ALERT</b>\nRekomendasi Sinyal {kode} HIT TP1!\nHarga Rp {harga_now:,.0f} ≥ TP1 Rp {tp1:,.0f}."
                check_and_send_alert(bot, chat_id, kode, "SINYAL_TP1", msg)
