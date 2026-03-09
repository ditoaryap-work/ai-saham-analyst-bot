"""
screening.py — Layer 0-3 screening logic (ALIGNED WITH MASTER PROMPT).

Layer 0: Market Context CLASSIFIER (BUKAN filter — analisa TIDAK PERNAH berhenti)
Layer 1: Likuiditas Binary Filter (gugur jika gagal)
Layer 2: Scoring Teknikal (25+ aturan, min skor 15)
Layer 3: OBV + Volume Profile + Candlestick
"""

import sys
from pathlib import Path
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db
from analysis.technical import calculate_indicators


# ═══════════════════════════════════════════════════════
# LAYER 0: Market Context CLASSIFIER (bukan filter!)
# ═══════════════════════════════════════════════════════

def layer0_market_context() -> dict:
    """
    Layer 0: Classifier kondisi market.
    ⚠️ PENTING: Ini BUKAN filter. Sistem TIDAK PERNAH berhenti analisa.
    Label ini dibawa sebagai KONTEKS ke semua layer berikutnya.
    """
    rows = db.execute("SELECT * FROM makro_data ORDER BY tanggal DESC LIMIT 1")

    if not rows:
        return {'label': 'MIXED', 'ihsg_change': 0, 'max_allocation': 0.5}

    data = dict(rows[0])
    ihsg = data.get('ihsg_change', 0) or 0

    # Klasifikasi sesuai master prompt
    if ihsg > 0:
        label = 'BULLISH'
    elif ihsg >= -0.015:
        label = 'MIXED'
    elif ihsg >= -0.03:
        label = 'BEARISH'
    else:
        label = 'EXTREME'

    allocation_map = {
        'BULLISH': 1.0, 'MIXED': 0.7, 'BEARISH': 0.3, 'EXTREME': 0.1
    }

    result = {
        'label': label,
        'ihsg_change': ihsg,
        'max_allocation': allocation_map.get(label, 0.5),
        'nikkei': data.get('nikkei_change', 0),
        'hsi': data.get('hsi_change', 0),
        'sti': data.get('sti_change', 0),
    }

    logger.info(f"Layer 0: {label} (IHSG {ihsg:+.2%}) | Alloc: {result['max_allocation']:.0%}")
    return result


# ═══════════════════════════════════════════════════════
# LAYER 1: Binary Liquidity Filter
# ═══════════════════════════════════════════════════════

def layer1_liquidity(kode: str) -> dict:
    """
    Layer 1: Filter likuiditas — binary, gugur jika gagal.
    Sesuai master prompt:
    - avg_value_5d > 3.000.000.000 (Rp 3M)
    - avg_volume_5d > 1.000.000
    - close > 50
    - data_length >= 200
    - change_1d > -0.15 (ARB flat)
    - change_1d < ARA limit (berjenjang)
    """
    # Volume & value rata-rata 5 hari
    rows = db.execute(
        """SELECT AVG(volume) as avg_vol, AVG(value) as avg_val, COUNT(*) as cnt
           FROM (SELECT volume, value FROM harga_historis
                 WHERE kode = ? ORDER BY tanggal DESC LIMIT 5)""",
        (kode,),
    )

    if not rows:
        return {'pass': False, 'reason': 'Tidak ada data harga'}

    r = dict(rows[0])
    avg_vol = r.get('avg_vol') or 0
    avg_val = r.get('avg_val') or 0

    # Total data
    total = db.execute(
        "SELECT COUNT(*) as cnt FROM harga_historis WHERE kode = ?", (kode,)
    )
    total_days = dict(total[0])['cnt'] if total else 0

    # Harga terakhir & daily change
    last = db.execute(
        """SELECT close FROM harga_historis WHERE kode = ?
           ORDER BY tanggal DESC LIMIT 2""",
        (kode,),
    )
    close = dict(last[0])['close'] if last else 0
    prev_close = dict(last[1])['close'] if last and len(last) > 1 else close
    change_1d = (close - prev_close) / prev_close if prev_close > 0 else 0

    # ARA limit berjenjang
    if close < 200:
        ara_limit = 0.35
    elif close < 5000:
        ara_limit = 0.25
    else:
        ara_limit = 0.20

    # Evaluasi
    reasons = []
    passed = True

    if avg_val and avg_val < 3_000_000_000:
        reasons.append(f"Nilai transaksi rendah (Rp {avg_val/1e9:.1f}M, min 3M)")
        passed = False

    if avg_vol < 1_000_000:
        reasons.append(f"Volume rendah ({avg_vol:,.0f}, min 1M)")
        passed = False

    if close <= 50:
        reasons.append(f"Harga terlalu rendah (Rp {close})")
        passed = False

    if total_days < 200:
        reasons.append(f"Data kurang ({total_days}d, min 200)")
        passed = False

    if change_1d <= -0.15:
        reasons.append(f"Kena ARB ({change_1d:+.1%})")
        passed = False

    if change_1d >= ara_limit:
        reasons.append(f"Kena ARA ({change_1d:+.1%})")
        passed = False

    result = {
        'pass': passed,
        'avg_volume': avg_vol,
        'avg_value': avg_val,
        'close': close,
        'change_1d': change_1d,
        'total_days': total_days,
        'reason': '; '.join(reasons) if reasons else 'OK',
    }

    status = "✅" if passed else "❌"
    logger.info(f"[{kode}] L1 {status} | Vol={avg_vol:,.0f} Val={avg_val/1e9:.1f}M Days={total_days}")
    return result


# ═══════════════════════════════════════════════════════
# LAYER 2: Scoring Teknikal (detail per master prompt)
# ═══════════════════════════════════════════════════════

def layer2_technical_scoring(kode: str, indicators: dict = None) -> dict:
    """
    Layer 2: Scoring teknikal detail sesuai master prompt.
    25+ aturan scoring. Threshold min skor 15.
    """
    if indicators is None:
        indicators = calculate_indicators(kode)

    if not indicators:
        return {'pass': False, 'raw_score': 0, 'reason': 'No data', 'details': []}

    score = 0
    details = []

    # ── EMA Alignment (max +8) ────────────────
    ema5 = indicators.get('ema5')
    ema20 = indicators.get('ema20')
    ema50 = indicators.get('ema50')
    ema200 = indicators.get('ema200')

    if ema5 and ema20 and ema50 and ema200:
        if ema20 > ema50 > ema200:
            score += 8
            details.append("EMA20>50>200 +8")
        elif ema20 > ema50:
            score += 5
            details.append("EMA20>50 +5")
        elif ema20 < ema50:
            score += 2
            details.append("EMA20<50 +2")

    # ── RSI (max +3) ─────────────────────────
    rsi = indicators.get('rsi', 50)
    if 40 <= rsi <= 55:
        score += 3
        details.append(f"RSI sweet spot +3 ({rsi:.0f})")
    elif 55 < rsi <= 65:
        score += 2
        details.append(f"RSI kuat +2 ({rsi:.0f})")
    elif 65 < rsi <= 70:
        score += 1
        details.append(f"RSI hati2 +1 ({rsi:.0f})")
    else:
        details.append(f"RSI extreme +0 ({rsi:.0f})")

    # ── StochRSI / Stochastic (max +4) ───────
    stoch_k = indicators.get('stoch_k', 50)
    stoch_d = indicators.get('stoch_d', 50)
    stoch_bull = indicators.get('stoch_bullish', False)

    if stoch_k < 20 and stoch_bull:
        score += 4
        details.append(f"Stoch cross UP dari <20 +4")
    elif 20 <= stoch_k <= 50 and stoch_bull:
        score += 3
        details.append(f"Stoch 20-50 naik +3")
    elif 50 < stoch_k <= 80:
        score += 1
        details.append(f"Stoch 50-80 +1")
    else:
        details.append(f"Stoch >80 +0 ({stoch_k:.0f})")

    # ── RSI Divergence Bullish (bonus +3) ─────
    # Simplified: RSI naik tapi harga turun = bullish divergence
    daily_chg = indicators.get('daily_change', 0)
    if daily_chg < 0 and rsi > 40 and indicators.get('obv_rising'):
        score += 3
        details.append("RSI Divergence Bullish +3 (bonus)")

    # ── MACD (max +4) ────────────────────────
    macd_bull = indicators.get('macd_bullish', False)
    macd_exp = indicators.get('macd_expanding', False)
    macd_hist = indicators.get('macd_hist', 0)

    if macd_bull and macd_exp and macd_hist > 0:
        score += 4
        details.append("MACD golden cross fresh +4")
    elif macd_hist > 0 and macd_exp:
        score += 3
        details.append("MACD hist positif naik +3")
    elif macd_hist > 0:
        score += 1
        details.append("MACD hist positif mendatar +1")
    else:
        details.append("MACD hist negatif +0")

    # ── Bollinger Bands (max +4 squeeze, +3 BB%B) ──
    bb_squeeze = indicators.get('bb_squeeze', False)
    bb_pos = indicators.get('bb_position', 0.5)

    if bb_squeeze:
        score += 4
        details.append("BB Squeeze aktif +4")

    if 0.4 <= bb_pos <= 0.7:
        score += 3
        details.append(f"BB%B mid +3 ({bb_pos:.2f})")
    elif 0.7 < bb_pos <= 0.85:
        score += 2
        details.append(f"BB%B upper +2 ({bb_pos:.2f})")
    elif bb_pos < 0.4 and rsi < 35:
        score += 3
        details.append(f"BB%B oversold + RSI low +3")
    elif bb_pos > 0.85:
        details.append(f"BB%B extreme +0 ({bb_pos:.2f})")

    # ── ATR (filter: wajib > 2%) ─────────────
    atr_pct = indicators.get('atr_pct', 0)
    if atr_pct < 2:
        score -= 2
        details.append(f"ATR% terlalu rendah -{2} ({atr_pct:.1f}%)")

    # ── Pivot Points (max +4) ────────────────
    close = indicators.get('close', 0)
    r1 = indicators.get('resist1', 0)
    pp = indicators.get('pivot', 0)
    s1 = indicators.get('support1', 0)

    if close > r1 and r1 > 0:
        score += 4
        details.append("Break above R1 +4")
    elif close > pp and s1 > 0:
        score += 3
        details.append("Bounce dari PP/S1 +3")

    # ── Volume (max +4 / min -3) ─────────────
    vol_ratio = indicators.get('vol_ratio', 0)
    candle_bull = indicators.get('candle_bullish', False)

    if vol_ratio > 3 and candle_bull:
        score += 4
        details.append(f"Vol >3x + naik +4 ({vol_ratio:.1f}x)")
    elif 1.5 <= vol_ratio <= 3 and candle_bull:
        score += 2
        details.append(f"Vol 1.5-3x + naik +2 ({vol_ratio:.1f}x)")
    elif vol_ratio > 3 and not candle_bull:
        score -= 3
        details.append(f"Vol >3x + turun -3 ({vol_ratio:.1f}x)")

    # ── Gap Analysis (max +3 / min -3) ───────
    gap = indicators.get('daily_change', 0)
    if gap > 0.02 and vol_ratio > 1.5:
        score += 3
        details.append(f"Gap up + volume +3 ({gap:+.1%})")
    elif gap < -0.02:
        score -= 3
        details.append(f"Gap down -3 ({gap:+.1%})")

    # ── Candlestick Patterns (bonus) ─────────
    if indicators.get('is_hammer'):
        score += 2
        details.append("Hammer pattern +2")

    passed = score >= 15
    result = {
        'pass': passed,
        'raw_score': score,
        'details': details,
        'indicators': indicators,
        'reason': f"L2 skor {score} ({'≥15 ✅' if passed else '<15 ❌'})",
    }

    logger.info(f"[{kode}] {result['reason']} | {len(details)} checks")
    return result


# ═══════════════════════════════════════════════════════
# LAYER 3: OBV + Volume Profile + Candlestick
# ═══════════════════════════════════════════════════════

def layer3_volume_analysis(kode: str, indicators: dict = None) -> dict:
    """
    Layer 3: OBV, Volume Profile, Candlestick detail.
    Raw score diteruskan ke scoring.py.
    """
    if indicators is None:
        indicators = calculate_indicators(kode)

    if not indicators:
        return {'raw_score': 0, 'details': []}

    score = 0
    details = []

    # ── OBV (max +10 / min -5) ───────────────
    obv_rising = indicators.get('obv_rising')
    vol_profile = indicators.get('vol_profile', 'NEUTRAL')
    rsi = indicators.get('rsi', 50)

    # OBV naik saat harga sideways (akumulasi) = strong signal
    daily_chg = abs(indicators.get('daily_change', 0))
    if obv_rising and daily_chg < 0.01:
        score += 10
        details.append("OBV naik + harga sideways (AKUMULASI!) +10")
    elif obv_rising and rsi < 40:
        score += 9
        details.append("OBV bullish divergence +9")
    elif obv_rising:
        score += 7
        details.append("OBV naik konfirmasi +7")
    else:
        score -= 5
        details.append("OBV turun (distribusi) -5")

    # ── Volume Profile (max +7 / min -8) ─────
    vol_ratio = indicators.get('vol_ratio', 0)
    candle_bull = indicators.get('candle_bullish', False)
    is_doji = indicators.get('is_doji', False)

    if vol_ratio > 3 and candle_bull:
        score += 7
        details.append(f"Vol spike >3x + naik +7 ({vol_ratio:.1f}x)")
    elif vol_ratio > 3 and is_doji:
        score -= 8
        details.append(f"Vol spike >3x + doji atas -8 (DISTRIBUSI)")
    elif vol_profile == 'ACCUMULATION':
        score += 5
        details.append("Volume profile accumulation +5")

    # ── Area Nilai (support/resistance) ──────
    close = indicators.get('close', 0)
    s1 = indicators.get('support1', 0)
    r1 = indicators.get('resist1', 0)

    if s1 and close and abs(close - s1) / close < 0.02:
        score += 5
        details.append("Mantul di demand zone +5")
    elif r1 and close > r1 and vol_ratio > 1.5:
        score += 4
        details.append("Tembus supply zone + volume +4")

    # ── Candlestick Patterns (max +6 / min -1) ──
    if indicators.get('is_hammer') and vol_ratio > 1.5:
        score += 5
        details.append("Hammer/Pin Bar + volume +5")
    elif indicators.get('is_hammer'):
        score += 3
        details.append("Hammer/Pin Bar +3")

    bullish_engulf = (
        indicators.get('candle_bullish', False) and
        indicators.get('daily_change', 0) > 0.02 and
        vol_ratio > 1.2
    )
    if bullish_engulf:
        score += 6
        details.append("Bullish Engulfing +6")

    if is_doji and close > r1:
        score -= 1
        details.append("Doji di resistance -1")

    result = {
        'raw_score': score,
        'details': details,
        'reason': f"L3 skor {score}",
    }

    logger.info(f"[{kode}] {result['reason']}")
    return result


# ═══════════════════════════════════════════════════════
# FULL SCREENING PIPELINE
# ═══════════════════════════════════════════════════════

def run_full_screening(stock_list: list) -> list:
    """
    Jalankan screening Layer 0-3.
    ⚠️ Layer 0 adalah CLASSIFIER — sistem TIDAK PERNAH berhenti.
    """
    market = layer0_market_context()

    if market['label'] == 'EXTREME':
        logger.warning("⚠️ MARKET EXTREME — Analisa tetap jalan, tapi alokasi sangat dibatasi.")

    passed = []

    for kode in stock_list:
        logger.info(f"\n{'─'*40}\nScreening {kode}...")

        # Layer 1: Liquidity (binary)
        l1 = layer1_liquidity(kode)
        if not l1['pass']:
            logger.info(f"[{kode}] ❌ L1: {l1['reason']}")
            continue

        # Get indicators once (shared by L2 & L3)
        indicators = calculate_indicators(kode)

        # Layer 2: Technical scoring
        l2 = layer2_technical_scoring(kode, indicators)
        if not l2['pass']:
            logger.info(f"[{kode}] ❌ L2: {l2['reason']}")
            continue

        # Layer 3: Volume/Price action (always runs, raw score passed to scoring)
        l3 = layer3_volume_analysis(kode, indicators)

        logger.info(f"[{kode}] ✅ LOLOS L1-L2 | L2={l2['raw_score']} L3={l3['raw_score']}")
        passed.append({
            'kode': kode,
            'market': market,
            'liquidity': l1,
            'technical': l2,
            'volume': l3,
            'indicators': indicators,
        })

    logger.info(f"\n{'═'*50}")
    logger.info(f"SCREENING: {len(passed)}/{len(stock_list)} lolos")
    logger.info(f"{'═'*50}")

    return passed


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    from config.settings import TEST_STOCKS

    print("\n🔍 Full Screening — Layer 0-3 (Master Prompt Aligned)\n")

    results = run_full_screening(TEST_STOCKS)

    print(f"\n📊 Hasil Screening:")
    print("-" * 50)

    if results:
        for r in results:
            k = r['kode']
            print(f"  ✅ {k} | L2={r['technical']['raw_score']} L3={r['volume']['raw_score']}")
            for d in r['technical']['details'][:3]:
                print(f"     • {d}")
    else:
        print("  Tidak ada saham lolos screening hari ini.")

    print(f"\n🎉 Screening selesai!")
