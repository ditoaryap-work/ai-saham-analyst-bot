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
import urllib.parse
from pathlib import Path
from datetime import datetime, date

from curl_cffi import requests

import yfinance as yf
import pandas as pd
from loguru import logger

# Setup path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    YFINANCE_DELAY, YFINANCE_BATCH_SIZE, YFINANCE_TICKER_SUFFIX, TEST_STOCKS
)
from data.database import db
from utils.helpers import to_yf_ticker, from_yf_ticker, batch_list, delay, get_yf_session


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
    session = get_yf_session()
    
    try:
        ticker = yf.Ticker(ticker_symbol, session=session)
        hist = ticker.history(period=period)
        
        if hist.empty:
            logger.warning(f"[{kode}] Data OHLCV kosong dari yfinance.")
            return pd.DataFrame()
        
        # Bersihkan dan format data
        df = hist[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df = df.reset_index()
        
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
    session = get_yf_session()
    
    try:
        ticker = yf.Ticker(ticker_symbol, session=session)
        info = ticker.info
        
        return {
            'kode': kode.upper(),
            'nama': info.get('longName') or info.get('shortName', kode),
            'sektor': info.get('sector', ''),
            'subsektor': info.get('industry', ''),
            'papan': '',  # yfinance tidak menyediakan info papan
            'listed_date': None,
            'market_cap': info.get('marketCap', 0),
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


def fetch_and_save_batch(stock_list: list, period: str = "1y", include_info: bool = True):
    """
    Fetch dan simpan OHLCV + info emiten untuk batch saham.
    
    Args:
        stock_list: List kode saham ['BBCA', 'TLKM', ...]
        period: Periode history yfinance
        include_info: Jika False, lewati fetch_emiten_info (sangat mempercepat untuk full scan)
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
                
                # 2. Fetch info emiten (Optional & Slow)
                if include_info:
                    info = fetch_emiten_info(kode)
                    if info:
                        save_emiten_to_db(info)
                
                success += 1
                logger.info(f"  [{success}/{total}] Selesai: {kode}")
                
                # Jeda antar saham (Rate Limit)
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


def fetch_all_idx_tickers() -> list:
    """
    Fetch seluruh daftar emiten dari website IDX via Cloudflare Proxy.
    Returns list kode saham ['AADI', 'ABBA', ...].
    """
    proxy_url = "https://yahoo-proxy.ditoaryap-work.workers.dev/?url="
    idx_api = "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles?emitenType=s&start=0&length=1000"
    target = f"{proxy_url}{urllib.parse.quote(idx_api)}"
    
    logger.info("Fetching all IDX tickers via Cloudflare Proxy...")
    try:
        r = requests.get(target, impersonate="chrome110", timeout=30)
        if r.status_code != 200:
            logger.error(f"Gagal fetch tickers: Status {r.status_code}")
            return []
        
        data = r.json()
        raw_list = data.get('data', [])
        tickers = [item['KodeEmiten'].upper().strip() for item in raw_list if 'KodeEmiten' in item]
        
        logger.info(f"Berhasil mendapatkan {len(tickers)} ticker dari IDX.")
        
        # Simpan info dasar ke DB
        for item in raw_list:
            if 'KodeEmiten' not in item:
                continue
            emiten = {
                'kode': item['KodeEmiten'].upper().strip(),
                'nama': item.get('NamaEmiten', ''),
                'sektor': item.get('Sektor', ''),
                'subsektor': item.get('SubSektor', ''),
                'papan': item.get('PapanPencatatan', ''),
                'listed_date': item.get('TanggalPencatatan', '')[:10],
                'market_cap': 0, # yfinance akan update ini nanti
                'is_suspended': 0,
                'last_update': date.today().isoformat(),
            }
            save_emiten_to_db(emiten)
            
        return tickers
    except Exception as e:
        logger.error(f"Error fetch_all_idx_tickers: {e}")
        return []


# ── Entry point untuk testing ────────────────────────
if __name__ == "__main__":
    import urllib.parse
    print("\n🚀 Stock Fetcher — Test Full Market Tickers\n")
    
    db.create_all_tables()
    
    all_tickers = fetch_all_idx_tickers()
    if all_tickers:
        print(f"Total tickers found: {len(all_tickers)}")
        print(f"Sample 5: {all_tickers[:5]}")
    else:
        print("Failed to fetch tickers.")
