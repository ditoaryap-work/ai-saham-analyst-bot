"""
analysis/swing_screening.py — Swing Trade Screening (3-7 hari hold).

Fokus: 
- Trend following (EMA 20 > EMA 50)
- Akumulasi volume besar (Vol Ratio > 1.2)
- Momentum stabil (RSI > 50)
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


def get_swing_candidates(limit: int = 150) -> list:
    """Ambil kandidat untuk swing trade berdasarkan value transaksi tertinggi."""
    rows = db.execute(
        """SELECT kode FROM harga_historis 
           WHERE tanggal >= date('now', '-3 days')
           GROUP BY kode
           ORDER BY sum(close * volume) DESC
           LIMIT ?""",
        (limit,)
    )
    if not rows:
        return []
        
    candidates = [r['kode'] for r in rows]
    logger.info(f"Swing Candidates: {len(candidates)} stocks")
    return candidates


def run_swing_screening(candidates: list = None) -> list:
    """
    Screening khusus Swing Trade.
    Syarat masuk swing:
    - EMA 20 > EMA 50 (Uptrend / early reversal)
    - Harga > EMA 20 (Strong momentum)
    - Volume > Rata-rata 20 hari
    """
    if candidates is None:
        candidates = get_swing_candidates(150)
    
    results = []
    
    for kode in candidates:
        try:
            # 1. Quick filter liquidity
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
            
            if close < 50 or volume < 1_000_000:  # Swing butuh likuiditas lebih tinggi
                continue
            
            # 2. Calculate technical indicators
            indicators = calculate_indicators(kode)
            if not indicators:
                continue
            
            # 3. Kriteria Utama Swing (Trend Following)
            ema20 = indicators.get('ema20', 0)
            ema50 = indicators.get('ema50', 0)
            rsi = indicators.get('rsi', 0)
            vol_ratio = indicators.get('vol_ratio', 0)
            
            # Skip jika tidak memenuhi syarat uptrend/momentum
            if close < ema20 or ema20 < ema50 or rsi < 50:
                continue
                
            # 4. Layer Scoring
            l2 = layer2_technical_scoring(kode, indicators)
            l3 = layer3_volume_analysis(kode, indicators)
            
            swing_score = l2['raw_score'] + l3['raw_score']
            
            # Bonus poin swing
            if vol_ratio > 1.5: swing_score += 5
            if 50 <= rsi <= 65: swing_score += 5  # Early momentum
            if ema20 > ema50 * 1.02: swing_score += 3 # Strong trend
            
            # 5. Calculate Swing Target & Stoploss (Wider than day trade)
            atr = indicators.get('atr', 0)
            s1 = indicators.get('support1', 0)
            r2 = indicators.get('resist2', 0)
            
            entry = close
            
            # Swing TP: +10-15% atau Resistance 2
            if r2 and r2 > close * 1.05:
                tp1 = r2
            elif atr > 0:
                tp1 = round(close + atr * 4) # 4x ATR for swing
            else:
                tp1 = round(close * 1.10)
                
            tp2 = round(close + atr * 6) if atr > 0 else round(close * 1.15)
            
            # Swing CL: Below Support 1 or -5%
            if s1 and s1 < close:
                cl = s1
            elif atr > 0:
                cl = round(close - atr * 2.5)
            else:
                cl = round(close * 0.95)
                
            # Prevent CL being too tight
            if (close - cl) / close < 0.03:
                cl = round(close * 0.95)
                
            tp1_pct = ((tp1 - close) / close * 100) if close > 0 else 0
            tp2_pct = ((tp2 - close) / close * 100) if close > 0 else 0
            cl_pct = ((cl - close) / close * 100) if close > 0 else 0
            
            # Harus R/R > 1.5
            potential_profit = tp1 - entry
            potential_loss = entry - cl
            
            if potential_loss <= 0: continue
            
            rr_ratio = potential_profit / potential_loss
            if rr_ratio < 1.5:
                continue
                
            results.append({
                'kode': kode,
                'close': close,
                'swing_score': swing_score,
                'l2_score': l2['raw_score'],
                'l3_score': l3['raw_score'],
                'vol_ratio': vol_ratio,
                'rr_ratio': rr_ratio,
                'entry': entry,
                'tp1': tp1,
                'tp1_pct': tp1_pct,
                'tp2': tp2,
                'tp2_pct': tp2_pct,
                'cl': cl,
                'cl_pct': cl_pct,
            })
            
        except Exception as e:
            logger.error(f"Swing screening error {kode}: {e}")
            continue
    
    # Sort by Swing score descending
    results.sort(key=lambda x: x['swing_score'], reverse=True)
    
    logger.info(f"🌊 Swing Screening: {len(results)} stocks passed, Target Top 5")
    return results[:5]


def save_swing_watchlist(results: list):
    """Simpan hasil Swing ke database."""
    today = date.today().isoformat()
    
    db.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_swing (
            tanggal TEXT,
            kode TEXT,
            ranking INTEGER,
            swing_score REAL,
            close REAL,
            tp1 REAL,
            cl REAL,
            PRIMARY KEY (tanggal, kode)
        )
    """)
    
    db.execute("DELETE FROM watchlist_swing WHERE tanggal = ?", (today,))
    
    for i, r in enumerate(results, 1):
        db.execute(
            "INSERT OR REPLACE INTO watchlist_swing VALUES (?,?,?,?,?,?,?)",
            (today, r['kode'], i, r['swing_score'], r['close'], r['tp1'], r['cl'])
        )
    
    logger.info(f"✅ Swing watchlist saved: {len(results)} stocks for {today}")
