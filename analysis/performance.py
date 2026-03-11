"""
analysis/performance.py — Tracker Win-Rate AI

Menghitung akurasi rekomendasi AI dari sinyal_history vs aktual market.
"""
from typing import Dict
from loguru import logger
from datetime import date, timedelta
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db

def get_ai_performance(days: int = 30) -> Dict:
    """
    Hitung performa sinyal AI D hari terakhir.
    """
    start_date = (date.today() - timedelta(days=days)).isoformat()
    
    rows = db.execute(
        "SELECT * FROM sinyal_history WHERE tanggal >= ? ORDER BY tanggal DESC",
        (start_date,)
    )
    
    if not rows:
        return {
            'days': days,
            'total': 0,
            'hit_tp1': 0,
            'hit_tp2': 0,
            'hit_sl': 0,
            'active': 0,
            'win_rate': 0
        }
        
    total = len(rows)
    hit_tp1 = 0
    hit_tp2 = 0
    hit_sl = 0
    active = 0
    
    for r in rows:
        kode = r['kode']
        t0 = r['tanggal']
        tp1 = r['target']
        tp2 = round(tp1 * 1.05) if tp1 else 0
        sl = r['stoploss']
        
        # Ambil harga sejak tanggal rekomendasi
        hist = db.execute(
            "SELECT MAX(high) as max_h, MIN(low) as min_l FROM harga_historis WHERE kode = ? AND tanggal >= ?",
            (kode, t0)
        )
        
        if not hist or hist[0]['max_h'] is None:
            # Belum ada data pergerakan, anggap aktif
            active += 1
            continue
            
        max_h = hist[0]['max_h']
        min_l = hist[0]['min_l']
        
        # Cek kondisi
        if tp2 and max_h >= tp2:
            hit_tp2 += 1
        elif tp1 and max_h >= tp1:
            hit_tp1 += 1
        elif sl and min_l <= sl:
            hit_sl += 1
        else:
            active += 1
            
    # Win rate: (hit TP1 + hit TP2) / (total - active)
    closed = hit_tp1 + hit_tp2 + hit_sl
    win_rate = (hit_tp1 + hit_tp2) / closed if closed > 0 else 0
    
    return {
        'days': days,
        'total': total,
        'hit_tp1': hit_tp1,
        'hit_tp2': hit_tp2,
        'hit_sl': hit_sl,
        'active': active,
        'win_rate': win_rate
    }

if __name__ == "__main__":
    perf = get_ai_performance(7)
    print(perf)
