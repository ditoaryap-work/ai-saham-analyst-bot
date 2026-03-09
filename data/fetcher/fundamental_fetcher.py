"""
fundamental_fetcher.py — Ambil data laporan keuangan via yfinance.

Mengambil:
- Income Statement (laba/rugi)
- Balance Sheet (neraca)
- Cash Flow Statement (arus kas)
- Info fundamental (PER, PBV, ROE, dll)

Data ini digunakan untuk perhitungan Piotroski F-Score dan Altman Z-Score.
"""

import sys
from pathlib import Path
from datetime import date

import yfinance as yf
import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import YFINANCE_DELAY, TEST_STOCKS
from data.database import db
from utils.helpers import to_yf_ticker, delay, get_yf_session


def fetch_fundamental(kode: str) -> dict:
    """
    Fetch semua data fundamental dari yfinance untuk satu saham.
    Menggabungkan data dari income_stmt, balance_sheet, cashflow, dan info.
    
    Returns dict siap insert ke tabel fundamental.
    """
    ticker_symbol = to_yf_ticker(kode)
    session = get_yf_session()
    
    try:
        ticker = yf.Ticker(ticker_symbol, session=session)
        info = ticker.info
        
        # Ambil laporan keuangan terbaru (kolom pertama = terbaru)
        income = ticker.income_stmt
        balance = ticker.balance_sheet
        cashflow = ticker.cashflow
        
        # Helper: ambil value dari DataFrame dengan aman
        def safe_get(df, key, col_idx=0):
            """Ambil value dari financial statement DataFrame."""
            if df is None or df.empty:
                return None
            if key in df.index and col_idx < len(df.columns):
                val = df.loc[key].iloc[col_idx]
                return float(val) if pd.notna(val) else None
            return None
        
        # ── Dari Income Statement ────────────────────
        revenue = safe_get(income, 'Total Revenue')
        net_income = safe_get(income, 'Net Income')
        gross_profit = safe_get(income, 'Gross Profit')
        ebit = safe_get(income, 'EBIT')
        
        # ── Dari Balance Sheet ───────────────────────
        total_assets = safe_get(balance, 'Total Assets')
        total_equity = safe_get(balance, 'Stockholders Equity') or safe_get(balance, 'Common Stock Equity')
        total_debt = safe_get(balance, 'Total Debt')
        current_assets = safe_get(balance, 'Current Assets')
        current_liabilities = safe_get(balance, 'Current Liabilities')
        retained_earnings = safe_get(balance, 'Retained Earnings')
        
        # ── Dari Cash Flow ───────────────────────────
        operating_cashflow = safe_get(cashflow, 'Operating Cash Flow')
        
        # ── Kalkulasi turunan ────────────────────────
        working_capital = None
        if current_assets is not None and current_liabilities is not None:
            working_capital = current_assets - current_liabilities
        
        roa = info.get('returnOnAssets')
        roe = info.get('returnOnEquity')
        
        der = None
        if total_debt is not None and total_equity is not None and total_equity != 0:
            der = total_debt / total_equity
        
        per = info.get('trailingPE')
        pbv = info.get('priceToBook')
        eps = info.get('trailingEps')
        
        # Periode: ambil dari kolom terbaru income statement
        periode = "latest"
        if income is not None and not income.empty:
            latest_date = income.columns[0]
            periode = str(latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else latest_date)
        
        result = {
            'kode': kode.upper(),
            'periode': periode,
            'revenue': revenue,
            'net_income': net_income,
            'total_assets': total_assets,
            'total_equity': total_equity,
            'total_debt': total_debt,
            'current_assets': current_assets,
            'current_liabilities': current_liabilities,
            'operating_cashflow': operating_cashflow,
            'gross_profit': gross_profit,
            'ebit': ebit,
            'roa': roa,
            'roe': roe,
            'der': der,
            'per': per,
            'pbv': pbv,
            'eps': eps,
            'retained_earnings': retained_earnings,
            'working_capital': working_capital,
            'f_score': None,  # Dihitung di analysis/fundamental.py
            'z_score': None,  # Dihitung di analysis/fundamental.py
            'last_update': date.today().isoformat(),
        }
        
        # Hitung metrics yang tersedia
        available = sum(1 for v in result.values() if v is not None and v != kode.upper())
        logger.info(f"[{kode}] Fundamental fetched: {available}/23 fields terisi.")
        
        return result
        
    except Exception as e:
        logger.error(f"[{kode}] Gagal fetch fundamental: {e}")
        return {}


def save_fundamental_to_db(data: dict) -> bool:
    """Simpan data fundamental ke tabel."""
    if not data:
        return False
    
    db.execute(
        """INSERT OR REPLACE INTO fundamental 
           (kode, periode, revenue, net_income, total_assets, total_equity,
            total_debt, current_assets, current_liabilities, operating_cashflow,
            gross_profit, ebit, roa, roe, der, per, pbv, eps,
            retained_earnings, working_capital, f_score, z_score, last_update)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        tuple(data.values()),
    )
    return True


def fetch_and_save_fundamentals(stock_list: list):
    """Fetch dan simpan fundamental untuk batch saham."""
    success = 0
    failed = []
    
    for kode in stock_list:
        try:
            data = fetch_fundamental(kode)
            if data:
                save_fundamental_to_db(data)
                success += 1
            else:
                failed.append(kode)
            delay(YFINANCE_DELAY)
        except Exception as e:
            logger.error(f"[{kode}] Error: {e}")
            failed.append(kode)
    
    logger.info(f"Fundamental fetch selesai: {success}/{len(stock_list)} berhasil.")
    return success, failed


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    print("\n🚀 Fundamental Fetcher — Test 5 saham LQ45\n")
    
    db.create_all_tables()
    success, failed = fetch_and_save_fundamentals(TEST_STOCKS)
    
    # Verifikasi
    print("\n📊 Data Fundamental di Database:")
    print("-" * 60)
    
    for kode in TEST_STOCKS:
        rows = db.execute(
            "SELECT * FROM fundamental WHERE kode = ? ORDER BY periode DESC LIMIT 1",
            (kode,),
        )
        if rows:
            r = dict(rows[0])
            print(f"\n  ✅ {kode} (periode: {r['periode']})")
            print(f"     Revenue     : Rp {r['revenue']/1e12:.1f}T" if r['revenue'] else f"     Revenue     : -")
            print(f"     Net Income  : Rp {r['net_income']/1e12:.1f}T" if r['net_income'] else f"     Net Income  : -")
            print(f"     Total Assets: Rp {r['total_assets']/1e12:.1f}T" if r['total_assets'] else f"     Total Assets: -")
            print(f"     ROA: {r['roa']:.2%}" if r['roa'] else "     ROA: -", end="")
            print(f" | ROE: {r['roe']:.2%}" if r['roe'] else " | ROE: -", end="")
            print(f" | PER: {r['per']:.1f}" if r['per'] else " | PER: -", end="")
            print(f" | PBV: {r['pbv']:.1f}" if r['pbv'] else " | PBV: -")
        else:
            print(f"\n  ❌ {kode}: Tidak ada data fundamental!")
    
    print("\n" + "-" * 60)
    print(f"🎉 {success}/{len(TEST_STOCKS)} saham berhasil.")
