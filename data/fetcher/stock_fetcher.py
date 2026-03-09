"""
stock_fetcher.py — Ambil data OHLCV saham IDX via yfinance.

Fitur:
- Fetch OHLCV historis (default 1 tahun)
- Fetch daftar emiten dari yfinance
- Batch processing dengan delay untuk hindari rate limit
- Simpan ke SQLite via database.py
"""

import sys
import time
from pathlib import Path
from datetime import datetime, date

from yahooquery import Ticker
import pandas as pd
from loguru import logger

# Setup path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    YFINANCE_DELAY, YFINANCE_BATCH_SIZE, YFINANCE_TICKER_SUFFIX, TEST_STOCKS
)
from data.database import db
from utils.helpers import to_yf_ticker, from_yf_ticker, batch_list, delay


def fetch_ohlcv(kode: str, period: str = "1y") -> pd.DataFrame:
    """
    Fetch data OHLCV untuk satu saham dari yfinance.
    
    Args:
        kode: Kode saham IDX (tanpa .JK), misal 'BBCA'
        period: Periode data ('1d','5d','1mo','3mo','6mo','1y','2y','5y','max')
    
    Returns:
        DataFrame dengan kolom: kode, tanggal, open, high, low, close, volume, value
    """
    ticker_symbol = to_yf_ticker(kode)
    
    try:
        ticker = Ticker(ticker_symbol, asynchronous=False)
        hist = ticker.history(period=period)
        
        if isinstance(hist, dict) or hist.empty:
            logger.warning(f"[{kode}] Data OHLCV kosong atau error dari yq.")
            return pd.DataFrame()
            
        hist = hist.reset_index()
        
        # Bersihkan dan format data
        df = hist[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        
        # Rename kolom
        df.columns = ['tanggal', 'open', 'high', 'low', 'close', 'volume']
        
        # Konversi timezone-aware datetime ke date string
        df['tanggal'] = pd.to_datetime(df['tanggal']).dt.strftime('%Y-%m-%d')
        
        # Tambah kolom
        df['kode'] = kode.upper()
        df['value'] = df['close'] * df['volume']  # Estimasi nilai transaksi
        
        # Reorder kolom sesuai tabel DB
        df = df[['kode', 'tanggal', 'open', 'high', 'low', 'close', 'volume', 'value']]
        
        logger.info(f"[{kode}] Berhasil fetch {len(df)} hari data OHLCV.")
        return df
        
    except Exception as e:
        logger.error(f"[{kode}] Gagal fetch OHLCV: {e}")
        return pd.DataFrame()


def save_ohlcv_to_db(df: pd.DataFrame) -> int:
    """
    Simpan DataFrame OHLCV ke tabel harga_historis (upsert).
    Returns jumlah baris yang disimpan.
    """
    if df.empty:
        return 0
    
    rows = df.values.tolist()
    
    db.execute_many(
        """INSERT OR REPLACE INTO harga_historis 
           (kode, tanggal, open, high, low, close, volume, value)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    
    kode = df['kode'].iloc[0]
    logger.info(f"[{kode}] {len(rows)} baris disimpan ke DB.")
    return len(rows)


def fetch_emiten_info(kode: str) -> dict:
    """
    Fetch info emiten (sektor, market cap, dll) dari yfinance.
    Returns dict untuk tabel daftar_emiten.
    """
    ticker_symbol = to_yf_ticker(kode)
    
    try:
        ticker = Ticker(ticker_symbol, asynchronous=False)
        
        # Fetch data dictionary
        price_data = ticker.price
        profile_data = ticker.summary_profile
        
        # Extract for the specific symbol
        p_info = price_data.get(ticker_symbol, {})
        sp_info = profile_data.get(ticker_symbol, {})
        
        if isinstance(p_info, str): # usually means error like "No fundamental data..."
            logger.warning(f"[{kode}] Gagal fetch info emiten dari yq: {p_info}")
            return {}
            
        return {
            'kode': kode.upper(),
            'nama': p_info.get('longName') or p_info.get('shortName', kode),
            'sektor': sp_info.get('sector', ''),
            'subsektor': sp_info.get('industry', ''),
            'papan': '',  # yfinance tidak menyediakan info papan
            'listed_date': None,
            'market_cap': p_info.get('marketCap', 0),
            'is_suspended': 0,
            'last_update': date.today().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"[{kode}] Gagal fetch info emiten: {e}")
        return {}


def save_emiten_to_db(emiten: dict) -> bool:
    """Simpan/update info emiten ke tabel daftar_emiten."""
    if not emiten:
        return False
    
    db.execute(
        """INSERT OR REPLACE INTO daftar_emiten 
           (kode, nama, sektor, subsektor, papan, listed_date, 
            market_cap, is_suspended, last_update)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            emiten['kode'], emiten['nama'], emiten['sektor'],
            emiten['subsektor'], emiten['papan'], emiten['listed_date'],
            emiten['market_cap'], emiten['is_suspended'], emiten['last_update'],
        ),
    )
    return True


def fetch_and_save_batch(stock_list: list, period: str = "1y"):
    """
    Fetch dan simpan OHLCV + info emiten untuk batch saham.
    
    Args:
        stock_list: List kode saham ['BBCA', 'TLKM', ...]
        period: Periode history yfinance
    """
    total = len(stock_list)
    success = 0
    failed = []
    
    batches = batch_list(stock_list, YFINANCE_BATCH_SIZE)
    
    logger.info(f"Mulai fetch {total} saham dalam {len(batches)} batch...")
    
    for batch_idx, batch in enumerate(batches, 1):
        logger.info(f"Batch {batch_idx}/{len(batches)}: {len(batch)} saham")
        
        for kode in batch:
            try:
                # 1. Fetch OHLCV
                df = fetch_ohlcv(kode, period)
                if not df.empty:
                    save_ohlcv_to_db(df)
                
                # 2. Fetch info emiten
                info = fetch_emiten_info(kode)
                if info:
                    save_emiten_to_db(info)
                
                success += 1
                delay(YFINANCE_DELAY)
                
            except Exception as e:
                logger.error(f"[{kode}] Error: {e}")
                failed.append(kode)
        
        # Delay antar batch lebih lama
        if batch_idx < len(batches):
            logger.info(f"Delay antar batch (2 detik)...")
            time.sleep(2)
    
    # Summary
    logger.info("=" * 50)
    logger.info(f"FETCH SELESAI: {success}/{total} berhasil")
    if failed:
        logger.warning(f"GAGAL ({len(failed)}): {', '.join(failed)}")
    logger.info("=" * 50)
    
    return success, failed


# ── Entry point untuk testing ────────────────────────
if __name__ == "__main__":
    print("\n🚀 Stock Fetcher — Test dengan 5 saham LQ45\n")
    
    db.create_all_tables()
    
    success, failed = fetch_and_save_batch(TEST_STOCKS, period="1y")
    
    # Verifikasi data di DB
    print("\n📊 Verifikasi Data di Database:")
    print("-" * 50)
    
    for kode in TEST_STOCKS:
        rows = db.execute(
            "SELECT COUNT(*) as cnt, MIN(tanggal) as first, MAX(tanggal) as last "
            "FROM harga_historis WHERE kode = ?",
            (kode,),
        )
        r = dict(rows[0])
        
        emiten = db.execute(
            "SELECT nama, sektor, market_cap FROM daftar_emiten WHERE kode = ?",
            (kode,),
        )
        
        if r['cnt'] > 0:
            e = dict(emiten[0]) if emiten else {}
            nama = e.get('nama', '-')
            sektor = e.get('sektor', '-')
            mcap = e.get('market_cap', 0)
            mcap_str = f"Rp {mcap/1e12:.1f}T" if mcap else "-"
            
            print(f"  ✅ {kode} ({nama})")
            print(f"     Sektor: {sektor} | MCap: {mcap_str}")
            print(f"     Data: {r['cnt']} hari ({r['first']} → {r['last']})")
        else:
            print(f"  ❌ {kode}: Tidak ada data!")
    
    print("-" * 50)
    print(f"\n🎉 Test selesai! {success} saham berhasil di-fetch.")
