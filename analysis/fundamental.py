"""
fundamental.py — Piotroski F-Score dan Altman Z-Score calculator.

F-Score (0-9): Mengukur kualitas fundamental perusahaan.
Z-Score: Mengukur risiko kebangkrutan.
"""

import sys
from pathlib import Path
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db


def calculate_f_score(kode: str) -> int:
    """
    Hitung Piotroski F-Score (0-9) berdasarkan data fundamental.
    
    9 kriteria:
    PROFITABILITY (4 poin):
      1. ROA > 0
      2. Operating Cash Flow > 0
      3. ROA meningkat (vs periode sebelumnya, approx. net_income/total_assets)
      4. Cash Flow > Net Income (accrual quality)
    LEVERAGE & LIQUIDITY (3 poin):
      5. DER menurun (atau Total Debt/Total Assets turun)
      6. Current Ratio meningkat
      7. Tidak ada dilusi saham (skip - tidak tersedia di yfinance)
    OPERATING EFFICIENCY (2 poin):
      8. Gross Margin meningkat
      9. Asset Turnover meningkat (Revenue / Total Assets)
    """
    rows = db.execute(
        "SELECT * FROM fundamental WHERE kode = ? ORDER BY periode DESC LIMIT 2",
        (kode,),
    )
    
    if not rows:
        logger.warning(f"[{kode}] Tidak ada data fundamental untuk F-Score.")
        return 0
    
    current = dict(rows[0])
    prev = dict(rows[1]) if len(rows) > 1 else None
    
    score = 0
    details = []
    
    # ── PROFITABILITY ─────────────────────────────────
    
    # 1. ROA > 0
    roa = current.get('roa')
    if roa and roa > 0:
        score += 1
        details.append("ROA+ ✅")
    else:
        details.append("ROA- ❌")
    
    # 2. Operating Cash Flow > 0
    ocf = current.get('operating_cashflow')
    if ocf and ocf > 0:
        score += 1
        details.append("OCF+ ✅")
    else:
        details.append("OCF- ❌")
    
    # 3. ROA meningkat
    if prev and current.get('roa') is not None and prev.get('roa') is not None:
        if current['roa'] > prev['roa']:
            score += 1
            details.append("ROA↑ ✅")
        else:
            details.append("ROA↓ ❌")
    else:
        # Jika tidak ada data pembanding, cek apakah ROA cukup tinggi
        if roa and roa > 0.05:
            score += 1
            details.append("ROA>5% ✅")
        else:
            details.append("ROA cmp N/A")
    
    # 4. Cash Flow > Net Income (kualitas akrual)
    ni = current.get('net_income')
    if ocf and ni and ocf > ni:
        score += 1
        details.append("OCF>NI ✅")
    else:
        details.append("OCF≤NI ❌")
    
    # ── LEVERAGE & LIQUIDITY ──────────────────────────
    
    # 5. DER menurun
    der = current.get('der')
    if prev and der is not None and prev.get('der') is not None:
        if der < prev['der']:
            score += 1
            details.append("DER↓ ✅")
        else:
            details.append("DER↑ ❌")
    else:
        # Pakai threshold: DER < 1.5 dianggap baik
        if der is not None and der < 1.5:
            score += 1
            details.append("DER<1.5 ✅")
        else:
            details.append("DER N/A")
    
    # 6. Current Ratio meningkat
    ca = current.get('current_assets')
    cl = current.get('current_liabilities')
    if ca and cl and cl > 0:
        cr = ca / cl
        if prev and prev.get('current_assets') and prev.get('current_liabilities'):
            prev_cr = prev['current_assets'] / prev['current_liabilities']
            if cr > prev_cr:
                score += 1
                details.append("CR↑ ✅")
            else:
                details.append("CR↓ ❌")
        else:
            # CR > 1 dianggap sehat
            if cr > 1:
                score += 1
                details.append("CR>1 ✅")
            else:
                details.append("CR<1 ❌")
    else:
        details.append("CR N/A")
    
    # 7. No dilution (skip - beri 1 poin default)
    score += 1
    details.append("NoDilute ✅ (default)")
    
    # ── OPERATING EFFICIENCY ──────────────────────────
    
    # 8. Gross Margin meningkat
    gp = current.get('gross_profit')
    rev = current.get('revenue')
    if gp and rev and rev > 0:
        gm = gp / rev
        if prev and prev.get('gross_profit') and prev.get('revenue') and prev['revenue'] > 0:
            prev_gm = prev['gross_profit'] / prev['revenue']
            if gm > prev_gm:
                score += 1
                details.append("GM↑ ✅")
            else:
                details.append("GM↓ ❌")
        else:
            if gm > 0.2:
                score += 1
                details.append("GM>20% ✅")
            else:
                details.append("GM N/A")
    else:
        details.append("GM N/A")
    
    # 9. Asset Turnover meningkat
    ta_val = current.get('total_assets')
    if rev and ta_val and ta_val > 0:
        at = rev / ta_val
        if prev and prev.get('revenue') and prev.get('total_assets') and prev['total_assets'] > 0:
            prev_at = prev['revenue'] / prev['total_assets']
            if at > prev_at:
                score += 1
                details.append("AT↑ ✅")
            else:
                details.append("AT↓ ❌")
        else:
            details.append("AT N/A")
    else:
        details.append("AT N/A")
    
    logger.info(f"[{kode}] F-Score: {score}/9 | {', '.join(details)}")
    return score


def calculate_z_score(kode: str) -> float:
    """
    Hitung Altman Z-Score untuk menilai risiko kebangkrutan.
    
    Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
    
    A = Working Capital / Total Assets
    B = Retained Earnings / Total Assets
    C = EBIT / Total Assets
    D = Market Cap / Total Debt  (modifikasi: equity/debt jika market cap tak ada)
    E = Revenue / Total Assets
    
    Interpretasi:
    - Z > 2.99: Zone Aman (Safe)
    - 1.81 < Z < 2.99: Grey Zone
    - Z < 1.81: Distress Zone (risiko kebangkrutan)
    """
    rows = db.execute(
        "SELECT * FROM fundamental WHERE kode = ? ORDER BY periode DESC LIMIT 1",
        (kode,),
    )
    
    if not rows:
        logger.warning(f"[{kode}] Tidak ada data fundamental untuk Z-Score.")
        return 0.0
    
    f = dict(rows[0])
    
    total_assets = f.get('total_assets')
    if not total_assets or total_assets <= 0:
        logger.warning(f"[{kode}] Total assets tidak valid.")
        return 0.0
    
    # A = Working Capital / Total Assets
    wc = f.get('working_capital') or 0
    A = wc / total_assets
    
    # B = Retained Earnings / Total Assets
    re = f.get('retained_earnings') or 0
    B = re / total_assets
    
    # C = EBIT / Total Assets
    ebit = f.get('ebit') or 0
    C = ebit / total_assets
    
    # D = Market Cap / Total Debt (atau Equity / Debt)
    # Ambil market cap dari daftar_emiten
    emiten = db.execute(
        "SELECT market_cap FROM daftar_emiten WHERE kode = ?", (kode,)
    )
    market_cap = dict(emiten[0]).get('market_cap') if emiten else None
    
    total_debt = f.get('total_debt') or 1  # Hindari division by zero
    if market_cap and market_cap > 0:
        D = market_cap / total_debt
    elif f.get('total_equity') and f['total_equity'] > 0:
        D = f['total_equity'] / total_debt
    else:
        D = 0
    
    # E = Revenue / Total Assets
    revenue = f.get('revenue') or 0
    E = revenue / total_assets
    
    # Hitung Z-Score
    z_score = (1.2 * A) + (1.4 * B) + (3.3 * C) + (0.6 * D) + (1.0 * E)
    
    # Klasifikasi
    if z_score > 2.99:
        zone = "SAFE"
    elif z_score > 1.81:
        zone = "GREY"
    else:
        zone = "DISTRESS"
    
    logger.info(f"[{kode}] Z-Score: {z_score:.2f} ({zone}) | A={A:.3f} B={B:.3f} C={C:.3f} D={D:.3f} E={E:.3f}")
    return round(z_score, 2)


def update_scores_in_db(kode: str) -> dict:
    """
    Hitung F-Score dan Z-Score, lalu update ke tabel fundamental.
    """
    f_score = calculate_f_score(kode)
    z_score = calculate_z_score(kode)
    
    # Update di DB
    db.execute(
        "UPDATE fundamental SET f_score = ?, z_score = ? WHERE kode = ?",
        (f_score, z_score, kode),
    )
    
    return {'kode': kode, 'f_score': f_score, 'z_score': z_score}


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    from config.settings import TEST_STOCKS
    
    print("\n📊 Fundamental Analysis — F-Score & Z-Score\n")
    
    for kode in TEST_STOCKS:
        result = update_scores_in_db(kode)
        if result:
            fs = result['f_score']
            zs = result['z_score']
            
            # Label
            f_label = "STRONG" if fs >= 7 else ("MODERATE" if fs >= 4 else "WEAK")
            z_label = "SAFE" if zs > 2.99 else ("GREY" if zs > 1.81 else "DISTRESS")
            
            f_bar = "█" * fs + "░" * (9 - fs)
            print(f"  {kode}: F-Score {fs}/9 [{f_bar}] {f_label} | Z-Score {zs:.2f} {z_label}")
    
    print(f"\n🎉 Fundamental scoring selesai!")
