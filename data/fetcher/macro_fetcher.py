"""
macro_fetcher.py — Fetch data makroekonomi via yfinance.

Mengambil:
- Indeks Asia: IHSG (^JKSE), Nikkei (^N225), Hang Seng (^HSI), STI (^STI)  
- Komoditas: Gold (GC=F), Crude Oil (CL=F)
- Menentukan label market context (BULLISH/MIXED/BEARISH/EXTREME)
"""

import sys
from pathlib import Path
from datetime import date

from yahooquery import Ticker
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import MACRO_TICKERS
from data.database import db
from utils.helpers import delay


def fetch_index_change(ticker_symbol: str, name: str) -> float:
    """
    Fetch perubahan harian (%) untuk satu indeks/komoditas.
    Returns: persentase perubahan (misal 0.015 = +1.5%)
    """
    try:
        ticker = Ticker(ticker_symbol, asynchronous=False)
        hist = ticker.history(period="5d")
        
        if isinstance(hist, dict) or hist.empty or len(hist) < 2:
            logger.warning(f"[{name}] Data tidak cukup untuk hitung change.")
            return 0.0
            
        hist = hist.reset_index()
        
        prev_close = hist['close'].iloc[-2]
        last_close = hist['close'].iloc[-1]
        
        if prev_close == 0:
            return 0.0
        
        change = (last_close - prev_close) / prev_close
        logger.info(f"[{name}] Close: {last_close:.2f} | Change: {change:+.2%}")
        return round(change, 6)
        
    except Exception as e:
        logger.error(f"[{name}] Gagal fetch: {e}")
        return 0.0


def classify_market(ihsg_change: float) -> str:
    """
    Klasifikasi kondisi market berdasarkan perubahan IHSG.
    Sesuai Layer 0 di master prompt.
    """
    if ihsg_change > 0:
        return "BULLISH"
    elif ihsg_change >= -0.015:
        return "MIXED"
    elif ihsg_change >= -0.03:
        return "BEARISH"
    else:
        return "EXTREME"


def fetch_all_macro() -> dict:
    """
    Fetch semua data makro dan return sebagai dict.
    """
    result = {}
    
    for name, ticker in MACRO_TICKERS.items():
        change = fetch_index_change(ticker, name)
        result[name] = change
        delay(0.3)
    
    # Classify market
    ihsg_change = result.get("IHSG", 0)
    market_label = classify_market(ihsg_change)
    
    logger.info(f"Market label: {market_label} (IHSG: {ihsg_change:+.2%})")
    
    return {
        'tanggal': date.today().isoformat(),
        'ihsg_change': result.get("IHSG", 0),
        'nikkei_change': result.get("Nikkei", 0),
        'hsi_change': result.get("Hang Seng", 0),
        'sti_change': result.get("STI", 0),
        'usd_idr': None,  # Akan diisi nanti jika ada sumber gratis
        'gold_change': result.get("Gold", 0),
        'oil_change': result.get("Crude Oil", 0),
        'market_label': market_label,
        'narasi': None,  # Akan diisi oleh AI nanti
    }


def save_macro_to_db(data: dict) -> bool:
    """Simpan data makro ke tabel makro_data."""
    if not data:
        return False
    
    db.execute(
        """INSERT OR REPLACE INTO makro_data
           (tanggal, ihsg_change, nikkei_change, hsi_change, sti_change,
            usd_idr, gold_change, oil_change, market_label, narasi)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data['tanggal'], data['ihsg_change'], data['nikkei_change'],
            data['hsi_change'], data['sti_change'], data['usd_idr'],
            data['gold_change'], data['oil_change'],
            data['market_label'], data['narasi'],
        ),
    )
    return True


def fetch_and_save_macro():
    """Fetch dan simpan semua data makro."""
    data = fetch_all_macro()
    save_macro_to_db(data)
    return data


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    print("\n🌏 Macro Fetcher — Test Indeks & Komoditas\n")
    
    db.create_all_tables()
    data = fetch_and_save_macro()
    
    # Tampilkan hasil
    print("\n📊 Data Makro Hari Ini:")
    print("-" * 50)
    
    items = [
        ("IHSG",      data['ihsg_change']),
        ("Nikkei",    data['nikkei_change']),
        ("Hang Seng", data['hsi_change']),
        ("STI",       data['sti_change']),
        ("Gold",      data['gold_change']),
        ("Crude Oil", data['oil_change']),
    ]
    
    for name, change in items:
        arrow = "🟢" if change > 0 else ("🔴" if change < 0 else "⚪")
        print(f"  {arrow} {name:12}: {change:+.2%}")
    
    print(f"\n  🏷️  Market Label: {data['market_label']}")
    print("-" * 50)
    
    # Verifikasi DB
    rows = db.execute(
        "SELECT * FROM makro_data WHERE tanggal = ?", (data['tanggal'],)
    )
    if rows:
        print(f"\n✅ Data berhasil disimpan ke database.")
    else:
        print(f"\n❌ Data GAGAL disimpan!")
    
    print(f"\n🎉 Macro fetch selesai!")
