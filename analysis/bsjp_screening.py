"""
analysis/bsjp_screening.py — BSJP (Beli Sore Jual Pagi) Screening.

Versi ringan dari full screening, dioptimasi untuk kecepatan:
- Skip fundamental & sentimen
- Fokus teknikal + volume momentum intraday
- Scan Top 100-200 kandidat dari watchlist sebelumnya
- Target selesai < 8 menit

Dijalankan jam ~15:00-15:30, rekomendasi dikirim ~15:45,
user beli ~15:50 sebelum market tutup 16:00.
"""

import sys
from pathlib import Path
from datetime import date
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db
from analysis.technical import calculate_indicators
from analysis.screening import layer2_technical_scoring, layer3_volume_analysis


def get_bsjp_candidates(limit: int = 200) -> list:
    """
    Ambil kandidat BSJP dari:
    1. watchlist_harian (Top 10 semalam) + 
    2. daftar_emiten yang punya data OHLCV (sisanya)
    Total target: 100-200 kandidat.
    """
    candidates = []
    
    # 1. Prioritas: watchlist_harian semalam (pasti berkualitas)
    rows = db.execute("SELECT kode FROM watchlist_harian ORDER BY tanggal DESC LIMIT 20")
    if rows:
        candidates = [r['kode'] for r in rows]
    
    # 2. Tambah dari emiten yang punya data OHLCV terbaru
    extra = db.execute(
        """SELECT DISTINCT kode FROM harga_historis 
           WHERE tanggal >= date('now', '-3 days')
           AND kode NOT IN ({})
           ORDER BY volume DESC
           LIMIT ?""".format(','.join(['?'] * len(candidates))),
        (*candidates, limit - len(candidates))
    )
    if extra:
        candidates.extend([r['kode'] for r in extra])
    
    logger.info(f"BSJP Candidates: {len(candidates)} stocks")
    return candidates[:limit]


def run_bsjp_screening(candidates: list = None) -> list:
    """
    Quick screening untuk BSJP.
    Fokus: momentum intraday + volume spike.
    Skip: fundamental, sentimen, full Layer 1.
    """
    if candidates is None:
        candidates = get_bsjp_candidates(200)
    
    results = []
    
    for kode in candidates:
        try:
            # Quick filter: harga > 50, volume > 500K
            last = db.execute(
                """SELECT close, volume FROM harga_historis 
                   WHERE kode = ? ORDER BY tanggal DESC LIMIT 1""",
                (kode,)
            )
            if not last:
                continue
            
            row = dict(last[0])
            close = row.get('close', 0)
            volume = row.get('volume', 0)
            
            if close < 50 or volume < 500_000:
                continue
            
            # Calculate indicators
            indicators = calculate_indicators(kode)
            if not indicators:
                continue
            
            # Layer 2 scoring (teknikal)
            l2 = layer2_technical_scoring(kode, indicators)
            
            # Layer 3 scoring (volume/price action)
            l3 = layer3_volume_analysis(kode, indicators)
            
            # BSJP-specific scoring: bonus untuk momentum intraday
            bsjp_score = l2['raw_score'] + l3['raw_score']
            
            # Bonus BSJP: volume spike hari ini
            vol_ratio = indicators.get('vol_ratio', 0)
            daily_change = indicators.get('daily_change', 0)
            
            if vol_ratio > 2 and daily_change > 0:
                bsjp_score += 5  # Volume spike + naik = momentum bagus
            
            if daily_change > 0.02 and vol_ratio > 1.5:
                bsjp_score += 3  # Strong intraday move
            
            # Calculate Entry/TP/CL
            atr = indicators.get('atr', 0)
            s1 = indicators.get('support1', 0)
            r1 = indicators.get('resist1', 0)
            
            # BSJP entry = close sore ini
            entry = close
            
            # BSJP TP: target besok pagi (conservative: 1-2% atau resistance)
            if r1 and r1 > close:
                tp1 = r1
            elif atr > 0:
                tp1 = round(close + atr * 0.8)
            else:
                tp1 = round(close * 1.015)
            
            tp2 = round(close + atr * 1.5) if atr > 0 else round(close * 1.03)
            
            # BSJP CL: tight stoploss (BSJP = overnight, risk kecil)
            if s1 and atr > 0:
                cl = round(max(s1, close - atr * 1.2))
            elif atr > 0:
                cl = round(close - atr * 1.2)
            else:
                cl = round(close * 0.97)
            
            tp1_pct = ((tp1 - close) / close * 100) if close > 0 else 0
            tp2_pct = ((tp2 - close) / close * 100) if close > 0 else 0
            cl_pct = ((cl - close) / close * 100) if close > 0 else 0
            
            results.append({
                'kode': kode,
                'close': close,
                'bsjp_score': bsjp_score,
                'l2_score': l2['raw_score'],
                'l3_score': l3['raw_score'],
                'vol_ratio': vol_ratio,
                'daily_change': daily_change,
                'entry': entry,
                'tp1': tp1,
                'tp1_pct': tp1_pct,
                'tp2': tp2,
                'tp2_pct': tp2_pct,
                'cl': cl,
                'cl_pct': cl_pct,
            })
            
        except Exception as e:
            logger.error(f"BSJP screening error {kode}: {e}")
            continue
    
    # Sort by BSJP score descending
    results.sort(key=lambda x: x['bsjp_score'], reverse=True)
    
    logger.info(f"BSJP Screening: {len(results)} stocks scored, Top 10 selected")
    return results[:10]


def save_bsjp_watchlist(results: list):
    """Simpan hasil BSJP ke database untuk referensi."""
    today = date.today().isoformat()
    
    # Buat tabel jika belum ada
    db.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_bsjp (
            tanggal TEXT,
            kode TEXT,
            ranking INTEGER,
            bsjp_score REAL,
            close REAL,
            tp1 REAL,
            cl REAL,
            PRIMARY KEY (tanggal, kode)
        )
    """)
    
    db.execute("DELETE FROM watchlist_bsjp WHERE tanggal = ?", (today,))
    
    for i, r in enumerate(results, 1):
        db.execute(
            "INSERT OR REPLACE INTO watchlist_bsjp VALUES (?,?,?,?,?,?,?)",
            (today, r['kode'], i, r['bsjp_score'], r['close'], r['tp1'], r['cl'])
        )
    
    logger.info(f"✅ BSJP watchlist saved: {len(results)} stocks for {today}")
