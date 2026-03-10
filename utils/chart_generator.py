"""
chart_generator.py — Generate stock chart images using mplfinance.
"""
import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import mplfinance as mpf
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db
from analysis.technical import _ema, _macd, _bbands, _rsi, _stochastic

CHART_DIR = ROOT / "temp_charts"
os.makedirs(CHART_DIR, exist_ok=True)

def _stoch_rsi(series: pd.Series, period=14, smoothK=3, smoothD=3):
    """Calculate Stochastic RSI."""
    rsi = _rsi(series, period)
    # Stoch of RSI
    rsi_low = rsi.rolling(window=period).min()
    rsi_high = rsi.rolling(window=period).max()
    stoch_rsi = (rsi - rsi_low) / (rsi_high - rsi_low) * 100
    
    stoch_rsi_k = stoch_rsi.rolling(window=smoothK).mean()
    stoch_rsi_d = stoch_rsi_k.rolling(window=smoothD).mean()
    return stoch_rsi_k, stoch_rsi_d

def generate_advanced_chart(kode: str, days: int = 150) -> str:
    """
    Generate Advanced Chart for Telegram using mplfinance.
    Saves to a temporary file and returns the file path.
    """
    rows = db.execute(
        """SELECT tanggal, open, high, low, close, volume 
           FROM harga_historis WHERE kode = ? 
           ORDER BY tanggal ASC""",
        (kode,)
    )

    if not rows or len(rows) < 50:
        logger.warning(f"[{kode}] Data tidak cukup untuk chart.")
        return None

    df = pd.DataFrame([dict(r) for r in rows])
    df['tanggal'] = pd.to_datetime(df['tanggal'])
    df.set_index('tanggal', inplace=True)
    
    # Calculate indicators over the entire dataset first
    df['EMA20'] = _ema(df['close'], 20)
    df['EMA50'] = _ema(df['close'], 50)
    upper, mid, lower, _ = _bbands(df['close'])
    df['BB_Upper'] = upper
    df['BB_Lower'] = lower
    
    macd, signal, hist = _macd(df['close'])
    df['MACD'] = macd
    df['MACD_Signal'] = signal
    df['MACD_Hist'] = hist
    
    stoch_k, stoch_d = _stoch_rsi(df['close'])
    df['StochRSI_K'] = stoch_k
    df['StochRSI_D'] = stoch_d

    # Slice for the chart
    df_plot = df.iloc[-days:].copy()

    # Define custom style (Premium Dark)
    mc = mpf.make_marketcolors(
        up='#00ff00', down='#ff0000', 
        edge='inherit',
        wick='inherit',
        volume='in',
        ohlc='inherit'
    )
    s = mpf.make_mpf_style(
        marketcolors=mc, 
        gridstyle=':', 
        y_on_right=True,
        facecolor='#121212',
        edgecolor='#2c2c2c',
        figcolor='#121212',
        gridcolor='#2c2c2c',
        rc={'text.color': '#ffffff', 'axes.labelcolor': '#ffffff', 
            'xtick.color': '#888888', 'ytick.color': '#888888'}
    )

    # Prepare addplots
    # Panel 0: Main Chart (Price, EMA, BB)
    # Panel 1: Volume
    # Panel 2: MACD
    # Panel 3: StochRSI
    
    # MACD Colors
    hist_colors = ['#00ff00' if val > 0 else '#ff0000' for val in df_plot['MACD_Hist']]

    apds = [
        mpf.make_addplot(df_plot['EMA20'], color='#00bfff', width=1.5, panel=0),
        mpf.make_addplot(df_plot['EMA50'], color='#ffb800', width=1.5, panel=0),
        mpf.make_addplot(df_plot['BB_Upper'], color='#555555', linestyle='--', width=1, panel=0),
        mpf.make_addplot(df_plot['BB_Lower'], color='#555555', linestyle='--', width=1, panel=0),
        
        # MACD
        mpf.make_addplot(df_plot['MACD_Hist'], type='bar', color=hist_colors, panel=2, ylabel='MACD'),
        mpf.make_addplot(df_plot['MACD'], color='#00bfff', panel=2, width=1),
        mpf.make_addplot(df_plot['MACD_Signal'], color='#ffb800', panel=2, width=1),
        
        # StochRSI
        mpf.make_addplot(df_plot['StochRSI_K'], color='#00bfff', panel=3, ylabel='StochRSI', width=1),
        mpf.make_addplot(df_plot['StochRSI_D'], color='#ffb800', panel=3, width=1),
        mpf.make_addplot([80]*len(df_plot), color='#ff0000', linestyle=':', panel=3),
        mpf.make_addplot([20]*len(df_plot), color='#00ff00', linestyle=':', panel=3)
    ]

    filepath = CHART_DIR / f"{kode}_chart.png"
    
    mpf.plot(
        df_plot, 
        type='candle', 
        style=s, 
        title=f"\n{kode} - AI Breakout Scanner",
        volume=True,
        volume_panel=1,
        addplot=apds,
        panel_ratios=(4, 1, 1, 1),
        figratio=(10, 8),
        figscale=1.2,
        tight_layout=True,
        savefig=dict(fname=filepath, dpi=150, bbox_inches='tight')
    )
    
    return str(filepath)

if __name__ == "__main__":
    path = generate_advanced_chart("BBCA")
    if path:
        print(f"Chart generated: {path}")
