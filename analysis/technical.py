"""
technical.py — Indikator teknikal via pure pandas/numpy.

Menghitung semua indikator yang dibutuhkan oleh sistem scoring:
- Trend: EMA 5/20/50/200, MACD, ADX
- Momentum: RSI, Stochastic, CCI
- Volume: OBV, Volume SMA, Volume Profile (relative)
- Volatility: Bollinger Bands, ATR
- Support/Resistance: Pivot Points, Recent High/Low

NOTE: Menggunakan pure pandas/numpy (bukan pandas-ta) untuk kompatibilitas
dengan Python 3.14+ yang tidak support numba.
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db


# ═══════════════════════════════════════════════════════
# HELPER: Indikator Teknikal Pure Pandas
# ═══════════════════════════════════════════════════════

def _ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def _sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    """MACD: returns (macd_line, signal_line, histogram)."""
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _stochastic(high, low, close, k_period=14, d_period=3):
    """Stochastic Oscillator: returns (%K, %D)."""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    denom = highest_high - lowest_low
    k = 100 * (close - lowest_low) / denom.replace(0, np.nan)
    d = k.rolling(window=d_period).mean()
    return k, d


def _adx(high, low, close, period=14):
    """Average Directional Index: returns (ADX, +DI, -DI)."""
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, min_periods=period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr.replace(0, np.nan))

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1/period, min_periods=period).mean()

    return adx, plus_di, minus_di


def _cci(high, low, close, period=20):
    """Commodity Channel Index."""
    tp = (high + low + close) / 3
    sma_tp = _sma(tp, period)
    mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))


def _bbands(series: pd.Series, period=20, std=2):
    """Bollinger Bands: returns (upper, mid, lower, width)."""
    mid = _sma(series, period)
    std_val = series.rolling(window=period).std()
    upper = mid + std * std_val
    lower = mid - std * std_val
    width = (upper - lower) / mid.replace(0, np.nan)
    return upper, mid, lower, width


def _atr(high, low, close, period=14):
    """Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()


def _obv(close, volume):
    """On-Balance Volume."""
    direction = np.where(close > close.shift(), 1, np.where(close < close.shift(), -1, 0))
    return (volume * direction).cumsum()


# ═══════════════════════════════════════════════════════
# MAIN: Hitung semua indikator
# ═══════════════════════════════════════════════════════

def calculate_indicators(kode: str) -> dict:
    """
    Hitung semua indikator teknikal untuk satu saham.
    Data diambil dari tabel harga_historis.
    """
    rows = db.execute(
        """SELECT tanggal, open, high, low, close, volume, value
           FROM harga_historis WHERE kode = ?
           ORDER BY tanggal ASC""",
        (kode,),
    )

    if not rows or len(rows) < 50:
        logger.warning(f"[{kode}] Data tidak cukup ({len(rows) if rows else 0} hari, min 50).")
        return {}

    df = pd.DataFrame([dict(r) for r in rows])
    df['tanggal'] = pd.to_datetime(df['tanggal'])
    df.set_index('tanggal', inplace=True)

    last = df.iloc[-1]
    close = last['close']
    volume = last['volume']

    result = {'kode': kode, 'close': close, 'volume': volume}

    # ── TREND ────────────────────────────────────
    df['ema5'] = _ema(df['close'], 5)
    df['ema20'] = _ema(df['close'], 20)
    df['ema50'] = _ema(df['close'], 50)
    df['ema200'] = _ema(df['close'], 200)

    result['ema5'] = df['ema5'].iloc[-1]
    result['ema20'] = df['ema20'].iloc[-1]
    result['ema50'] = df['ema50'].iloc[-1]
    result['ema200'] = df['ema200'].iloc[-1]

    if all(pd.notna(v) for v in [result['ema5'], result['ema20'], result['ema50']]):
        result['ema_aligned'] = result['ema5'] > result['ema20'] > result['ema50']
        result['above_ema200'] = close > result['ema200'] if pd.notna(result['ema200']) else None
    else:
        result['ema_aligned'] = None
        result['above_ema200'] = None

    macd_line, signal_line, histogram = _macd(df['close'])
    result['macd_line'] = macd_line.iloc[-1]
    result['macd_signal'] = signal_line.iloc[-1]
    result['macd_hist'] = histogram.iloc[-1]
    result['macd_bullish'] = result['macd_line'] > result['macd_signal']
    if len(histogram) >= 2:
        result['macd_expanding'] = abs(histogram.iloc[-1]) > abs(histogram.iloc[-2])
    else:
        result['macd_expanding'] = None

    adx, plus_di, minus_di = _adx(df['high'], df['low'], df['close'])
    result['adx'] = adx.iloc[-1]
    result['adx_plus'] = plus_di.iloc[-1]
    result['adx_minus'] = minus_di.iloc[-1]
    result['trend_strong'] = result['adx'] > 25 if pd.notna(result['adx']) else False
    result['trend_bullish'] = result['adx_plus'] > result['adx_minus'] if pd.notna(result['adx_plus']) else False

    # ── MOMENTUM ─────────────────────────────────
    rsi = _rsi(df['close'])
    result['rsi'] = rsi.iloc[-1]
    result['rsi_oversold'] = result['rsi'] < 30 if pd.notna(result['rsi']) else False
    result['rsi_overbought'] = result['rsi'] > 70 if pd.notna(result['rsi']) else False
    result['rsi_bullish_zone'] = 40 < result['rsi'] < 60 if pd.notna(result['rsi']) else False

    stoch_k, stoch_d = _stochastic(df['high'], df['low'], df['close'])
    result['stoch_k'] = stoch_k.iloc[-1]
    result['stoch_d'] = stoch_d.iloc[-1]
    result['stoch_bullish'] = result['stoch_k'] > result['stoch_d'] if pd.notna(result['stoch_k']) else False
    result['stoch_oversold'] = result['stoch_k'] < 20 if pd.notna(result['stoch_k']) else False

    cci = _cci(df['high'], df['low'], df['close'])
    result['cci'] = cci.iloc[-1]

    # ── VOLUME ───────────────────────────────────
    obv = _obv(df['close'], df['volume'])
    result['obv'] = obv.iloc[-1]
    if len(obv) >= 5:
        result['obv_rising'] = obv.iloc[-1] > obv.iloc[-5]
    else:
        result['obv_rising'] = None

    vol_sma20 = _sma(df['volume'], 20)
    avg_vol = vol_sma20.iloc[-1]
    result['vol_sma20'] = avg_vol
    result['vol_ratio'] = volume / avg_vol if avg_vol and avg_vol > 0 else 0
    result['vol_spike'] = result['vol_ratio'] > 1.5
    result['vol_dry'] = result['vol_ratio'] < 0.5

    if len(df) >= 5:
        last5 = df.iloc[-5:]
        price_change = last5['close'].iloc[-1] - last5['close'].iloc[0]
        vol_change = last5['volume'].iloc[-1] - last5['volume'].iloc[0]
        if price_change > 0 and vol_change > 0:
            result['vol_profile'] = 'ACCUMULATION'
        elif price_change < 0 and vol_change > 0:
            result['vol_profile'] = 'DISTRIBUTION'
        elif price_change > 0 and vol_change <= 0:
            result['vol_profile'] = 'WEAK_RALLY'
        else:
            result['vol_profile'] = 'NEUTRAL'

    # ── VOLATILITY ───────────────────────────────
    bb_upper, bb_mid, bb_lower, bb_width = _bbands(df['close'])
    result['bb_upper'] = bb_upper.iloc[-1]
    result['bb_mid'] = bb_mid.iloc[-1]
    result['bb_lower'] = bb_lower.iloc[-1]
    result['bb_width'] = bb_width.iloc[-1]

    bb_range = result['bb_upper'] - result['bb_lower']
    if bb_range and bb_range > 0:
        result['bb_position'] = (close - result['bb_lower']) / bb_range
    else:
        result['bb_position'] = 0.5
    result['bb_squeeze'] = (bb_range / result['bb_mid'] < 0.05) if result['bb_mid'] else False

    atr = _atr(df['high'], df['low'], df['close'])
    result['atr'] = atr.iloc[-1]
    result['atr_pct'] = (result['atr'] / close) * 100 if close > 0 else 0

    # ── SUPPORT / RESISTANCE ─────────────────────
    high_prev = df['high'].iloc[-2]
    low_prev = df['low'].iloc[-2]
    close_prev = df['close'].iloc[-2]

    pivot = (high_prev + low_prev + close_prev) / 3
    result['pivot'] = pivot
    result['support1'] = (2 * pivot) - high_prev
    result['resist1'] = (2 * pivot) - low_prev
    result['support2'] = pivot - (high_prev - low_prev)
    result['resist2'] = pivot + (high_prev - low_prev)

    if len(df) >= 200:
        result['high_52w'] = df['high'].iloc[-200:].max()
        result['low_52w'] = df['low'].iloc[-200:].min()
        result['pct_from_high'] = (close - result['high_52w']) / result['high_52w']
        result['pct_from_low'] = (close - result['low_52w']) / result['low_52w']

    # ── CANDLESTICK ──────────────────────────────
    body = abs(last['close'] - last['open'])
    total_range = last['high'] - last['low']
    if total_range > 0:
        lower_shadow = min(last['open'], last['close']) - last['low']
        upper_shadow = last['high'] - max(last['open'], last['close'])
        result['is_doji'] = (body / total_range) < 0.1
        result['is_hammer'] = (lower_shadow > 2 * body) and (upper_shadow < body)
        result['is_shooting_star'] = (upper_shadow > 2 * body) and (lower_shadow < body)
        result['candle_bullish'] = last['close'] > last['open']

    if len(df) >= 2:
        prev_close = df['close'].iloc[-2]
        result['daily_change'] = (close - prev_close) / prev_close

    logger.info(f"[{kode}] {len(result)} indikator dihitung.")
    return result


def get_technical_summary(indicators: dict) -> str:
    """Buat ringkasan teknikal dalam format teks."""
    if not indicators:
        return "Data teknikal tidak tersedia."
    kode = indicators.get('kode', '?')
    close = indicators.get('close', 0)
    ema_status = "✅ ALIGNED" if indicators.get('ema_aligned') else "❌ NOT ALIGNED"
    macd_status = "✅ BULLISH" if indicators.get('macd_bullish') else "❌ BEARISH"
    rsi = indicators.get('rsi', 0)
    rsi_label = "OVERSOLD" if rsi < 30 else ("OVERBOUGHT" if rsi > 70 else "NORMAL")
    vol_ratio = indicators.get('vol_ratio', 0)
    vol_profile = indicators.get('vol_profile', '-')
    s1 = indicators.get('support1', 0)
    r1 = indicators.get('resist1', 0)
    return (
        f"## {kode} @ Rp {close:,.0f}\n"
        f"Trend: EMA {ema_status} | MACD {macd_status}\n"
        f"RSI: {rsi:.1f} ({rsi_label})\n"
        f"Volume: {vol_ratio:.1f}x avg | Profile: {vol_profile}\n"
        f"S1: {s1:,.0f} | R1: {r1:,.0f}"
    )


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    from config.settings import TEST_STOCKS

    print("\n📈 Technical Indicators — Test 5 saham LQ45\n")

    for kode in TEST_STOCKS:
        ind = calculate_indicators(kode)
        if ind:
            print(f"\n{'='*50}")
            print(f"  {kode} @ Rp {ind['close']:,.0f}")
            print(f"  EMA Aligned: {ind.get('ema_aligned')}")
            print(f"  MACD Bullish: {ind.get('macd_bullish')} | Expanding: {ind.get('macd_expanding')}")
            print(f"  RSI: {ind.get('rsi', 0):.1f} | Stoch K: {ind.get('stoch_k', 0):.1f}")
            print(f"  ADX: {ind.get('adx', 0):.1f} | Trend Strong: {ind.get('trend_strong')}")
            print(f"  Vol Ratio: {ind.get('vol_ratio', 0):.2f}x | Profile: {ind.get('vol_profile')}")
            print(f"  OBV Rising: {ind.get('obv_rising')}")
            print(f"  BB Position: {ind.get('bb_position', 0):.2f} | Squeeze: {ind.get('bb_squeeze')}")
            print(f"  ATR%: {ind.get('atr_pct', 0):.2f}%")
            print(f"  S1: {ind.get('support1', 0):,.0f} | R1: {ind.get('resist1', 0):,.0f}")
            print(f"  Daily: {ind.get('daily_change', 0):+.2%}")
        else:
            print(f"\n  ❌ {kode}: Data tidak cukup.")

    print(f"\n{'='*50}")
    print("🎉 Technical analysis selesai!")
