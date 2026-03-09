"""
scoring.py — 4 Dimensi Equal Weight Scoring (100 poin).
ALIGNED WITH MASTER PROMPT.

Distribusi: 4 × 25 = 100 poin (equal weight)
  D1: Teknikal (25) — normalized dari Layer 2 raw
  D2: Volume/Price Action (25) — normalized dari Layer 3 raw
  D3: Fundamental (25) — F-Score + Z-Score
  D4: Sentimen (25) — Firm-specific + Industry/Sektor

Label:
  🔵 AMAN       : 75-100
  🟠 MOMENTUM   : 60-74
  🟡 SPEKULATIF  : 45-59
  ❌ SKIP        : < 45
"""

import sys
from pathlib import Path
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db
from analysis.technical import calculate_indicators
from analysis.fundamental import calculate_f_score, calculate_z_score

# List saham bank (skip kriteria 5,6,7 F-Score)
BANK_STOCKS = [
    'BBCA', 'BBRI', 'BMRI', 'BBNI', 'BRIS', 'NISP',
    'BNGA', 'BDMN', 'BTPS', 'BJTM', 'BJBR', 'MEGA',
]

# Raw score ranges untuk normalisasi (dari master prompt)
L2_MIN, L2_MAX = -8, 49    # Layer 2 technical
L3_MIN, L3_MAX = -14, 33   # Layer 3 volume/price action


def _normalize(raw: float, min_raw: float, max_raw: float, max_points: int = 25) -> float:
    """Normalisasi raw score ke 0-max_points sesuai formula master prompt."""
    return max(0, min(max_points, (raw - min_raw) / (max_raw - min_raw) * max_points))


# ═══════════════════════════════════════════════════════
# DIMENSI 1: TEKNIKAL (25 poin) — dari Layer 2 raw
# ═══════════════════════════════════════════════════════

def score_d1_technical(l2_raw: int) -> dict:
    """Normalize Layer 2 raw score ke 0-25."""
    score = round(_normalize(l2_raw, L2_MIN, L2_MAX, 25), 1)
    return {
        'score': score,
        'max': 25,
        'raw': l2_raw,
        'details': [f"L2 raw={l2_raw} → normalized={score:.1f}/25"],
    }


# ═══════════════════════════════════════════════════════
# DIMENSI 2: VOLUME / PRICE ACTION (25 poin) — dari Layer 3 raw
# ═══════════════════════════════════════════════════════

def score_d2_volume(l3_raw: int) -> dict:
    """Normalize Layer 3 raw score ke 0-25."""
    score = round(_normalize(l3_raw, L3_MIN, L3_MAX, 25), 1)
    return {
        'score': score,
        'max': 25,
        'raw': l3_raw,
        'details': [f"L3 raw={l3_raw} → normalized={score:.1f}/25"],
    }


# ═══════════════════════════════════════════════════════
# DIMENSI 3: FUNDAMENTAL (25 poin) — F-Score + Z-Score
# ═══════════════════════════════════════════════════════

def score_d3_fundamental(kode: str) -> dict:
    """
    25 poin: F-Score (15) + Z-Score (10).
    Modifikasi bank: skip kriteria 5,6,7 untuk saham bank.
    """
    details = []
    score = 0

    is_bank = kode in BANK_STOCKS

    # ── F-Score (max 15 poin) ────────────────
    f_score = calculate_f_score(kode)

    if is_bank:
        # Bank: skala 0-6 (skip 3 kriteria)
        if f_score >= 6:
            f_points = 15
        elif f_score >= 4:
            f_points = 10
        elif f_score >= 3:
            f_points = 6
        else:
            f_points = 2
        details.append(f"F-Score {f_score}/6 (bank) → +{f_points}")
    else:
        # Non-bank: skala 0-9
        if f_score >= 8:
            f_points = 15
        elif f_score >= 6:
            f_points = 10
        elif f_score >= 4:
            f_points = 6
        else:
            f_points = 2
        details.append(f"F-Score {f_score}/9 → +{f_points}")

    score += f_points

    # ── Z-Score (max 10 poin) ────────────────
    z_score = calculate_z_score(kode)

    if z_score > 2.99:
        z_points = 10
        details.append(f"Z-Score {z_score:.2f} SAFE → +10")
    elif z_score > 1.81:
        z_points = 5
        details.append(f"Z-Score {z_score:.2f} GREY → +5")
    else:
        z_points = 0
        details.append(f"Z-Score {z_score:.2f} DISTRESS → +0")

    score += z_points

    return {
        'score': min(score, 25),
        'max': 25,
        'f_score': f_score,
        'z_score': z_score,
        'is_bank': is_bank,
        'details': details,
    }


# ═══════════════════════════════════════════════════════
# DIMENSI 4: SENTIMEN (25 poin) — Firm + Industry
# ═══════════════════════════════════════════════════════

def score_d4_sentiment(kode: str) -> dict:
    """
    25 poin: Firm-Specific (15) + Industry/Sektor (10)
    Rolling 7 hari.
    """
    details = []
    score = 0

    # ── Firm-Specific Sentiment (max 15) ─────
    news = db.execute(
        """SELECT sentimen, confidence FROM berita
           WHERE emiten_terkait LIKE ? AND processed = 1
           AND confidence > 0.3
           ORDER BY tanggal DESC LIMIT 10""",
        (f"%{kode}%",),
    )

    if news and len(news) > 0:
        sentiments = [dict(n) for n in news]
        avg_conf = sum(s.get('confidence', 0) for s in sentiments) / len(sentiments)

        pos = sum(1 for s in sentiments if s['sentimen'] == 'positif')
        neg = sum(1 for s in sentiments if s['sentimen'] == 'negatif')
        ratio = pos / max(pos + neg, 1)

        if ratio > 0.7 and avg_conf > 85:
            firm_score = 15
            details.append(f"Sentimen sangat positif +15 (conf={avg_conf:.0f}%)")
        elif ratio > 0.5 and avg_conf > 65:
            firm_score = 10
            details.append(f"Sentimen positif +10 (conf={avg_conf:.0f}%)")
        elif ratio >= 0.3:
            firm_score = 5
            details.append(f"Sentimen netral +5")
        elif ratio < 0.3 and neg > pos:
            firm_score = -5
            details.append(f"Sentimen sangat negatif -5")
        else:
            firm_score = 0
            details.append(f"Sentimen negatif +0")

        score += max(0, firm_score)
    else:
        score += 5  # Default netral
        details.append("Sentimen belum ada data +5 (default netral)")

    # ── Industry/Sektor Sentiment (max 10) ───
    # Ambil sektor dari emiten
    emiten = db.execute(
        "SELECT sektor FROM daftar_emiten WHERE kode = ?", (kode,)
    )
    sektor = dict(emiten[0]).get('sektor', '') if emiten else ''

    # Cek berita sektor (simplified)
    sektor_news = db.execute(
        """SELECT sentimen FROM berita
           WHERE processed = 1 AND confidence > 50
           ORDER BY tanggal DESC LIMIT 20"""
    )

    if sektor_news:
        all_sent = [dict(n)['sentimen'] for n in sektor_news]
        pos_pct = all_sent.count('positif') / len(all_sent) if all_sent else 0

        if pos_pct > 0.5:
            score += 10
            details.append(f"Sektor {sektor}: positif +10")
        elif pos_pct > 0.3:
            score += 5
            details.append(f"Sektor {sektor}: netral +5")
        else:
            score += 0
            details.append(f"Sektor {sektor}: negatif +0")
    else:
        score += 5
        details.append(f"Sektor: default netral +5")

    return {
        'score': min(score, 25),
        'max': 25,
        'details': details,
    }


# ═══════════════════════════════════════════════════════
# COMPOSITE SCORE
# ═══════════════════════════════════════════════════════

def calculate_composite_score(kode: str, l2_raw: int = 0, l3_raw: int = 0,
                               indicators: dict = None) -> dict:
    """
    Hitung skor komposit 4×25 = 100 poin.
    l2_raw/l3_raw dari screening pipeline.
    """
    if indicators is None:
        indicators = calculate_indicators(kode)

    if not indicators and l2_raw == 0:
        return {'kode': kode, 'total': 0, 'label': 'SKIP'}

    # Jika l2/l3 belum di-supply, hitung dari screening
    if l2_raw == 0:
        from analysis.screening import layer2_technical_scoring, layer3_volume_analysis
        l2 = layer2_technical_scoring(kode, indicators)
        l2_raw = l2['raw_score']
        l3 = layer3_volume_analysis(kode, indicators)
        l3_raw = l3['raw_score']

    d1 = score_d1_technical(l2_raw)
    d2 = score_d2_volume(l3_raw)
    d3 = score_d3_fundamental(kode)
    d4 = score_d4_sentiment(kode)

    total = round(d1['score'] + d2['score'] + d3['score'] + d4['score'], 1)

    # Label sesuai master prompt
    if total >= 75:
        label = "AMAN"
        emoji = "🔵"
    elif total >= 60:
        label = "MOMENTUM"
        emoji = "🟠"
    elif total >= 45:
        label = "SPEKULATIF"
        emoji = "🟡"
    else:
        label = "SKIP"
        emoji = "❌"

    result = {
        'kode': kode,
        'total': total,
        'max': 100,
        'label': label,
        'emoji': emoji,
        'd1_technical': d1,
        'd2_volume': d2,
        'd3_fundamental': d3,
        'd4_sentiment': d4,
        'close': indicators.get('close', 0) if indicators else 0,
    }

    logger.info(
        f"[{kode}] {emoji} {total}/100 → {label} | "
        f"D1={d1['score']:.0f} D2={d2['score']:.0f} "
        f"D3={d3['score']:.0f} D4={d4['score']:.0f}"
    )

    return result


def format_score_report(result: dict) -> str:
    """Format untuk Telegram / AI input."""
    k = result['kode']
    t = result['total']
    l = result['label']
    e = result.get('emoji', '❓')
    c = result.get('close', 0)

    d1 = result['d1_technical']
    d2 = result['d2_volume']
    d3 = result['d3_fundamental']
    d4 = result['d4_sentiment']

    return (
        f"{e} {k} — {l} ({t}/100)\n"
        f"Harga: Rp {c:,.0f}\n"
        f"📊 Teknikal:   {d1['score']:.0f}/{d1['max']}\n"
        f"📈 Vol/Action: {d2['score']:.0f}/{d2['max']}\n"
        f"📉 Fundamental:{d3['score']:.0f}/{d3['max']}\n"
        f"📰 Sentimen:   {d4['score']:.0f}/{d4['max']}"
    )


def format_table_for_ai(result: dict) -> str:
    """Format sebagai tabel terstruktur untuk input AI."""
    k = result['kode']
    d1 = result['d1_technical']
    d2 = result['d2_volume']
    d3 = result['d3_fundamental']
    d4 = result['d4_sentiment']

    lines = [
        f"| Dimensi | Skor | Max | Detail |",
        f"|---------|------|-----|--------|",
        f"| Teknikal | {d1['score']:.0f} | 25 | L2 raw={d1.get('raw',0)} |",
        f"| Vol/Price | {d2['score']:.0f} | 25 | L3 raw={d2.get('raw',0)} |",
        f"| Fundamental | {d3['score']:.0f} | 25 | F={d3.get('f_score',0)}/9 Z={d3.get('z_score',0):.1f} |",
        f"| Sentimen | {d4['score']:.0f} | 25 | {d4['details'][0] if d4['details'] else '-'} |",
        f"| **TOTAL** | **{result['total']:.0f}** | **100** | **{result['label']}** |",
    ]
    return "\n".join(lines)


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    from config.settings import TEST_STOCKS

    print("\n🏆 Composite Scoring — 4×25 Equal Weight (Master Prompt)\n")

    results = []
    for kode in TEST_STOCKS:
        result = calculate_composite_score(kode)
        results.append(result)

    results.sort(key=lambda x: x['total'], reverse=True)

    print("\n" + "=" * 60)
    print("  RANKING SAHAM")
    print("=" * 60)

    for i, r in enumerate(results, 1):
        medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f" {i}."))
        print(f"\n  {medal} {r['emoji']} {r['kode']} — {r['label']} ({r['total']}/100)")
        d1, d2, d3, d4 = r['d1_technical'], r['d2_volume'], r['d3_fundamental'], r['d4_sentiment']
        print(f"      D1={d1['score']:.0f}/25 | D2={d2['score']:.0f}/25 | D3={d3['score']:.0f}/25 | D4={d4['score']:.0f}/25")
        # Top details
        for d in (d1['details'][:1] + d3['details'][:1] + d4['details'][:1]):
            print(f"      • {d}")

    print("\n" + "=" * 60)
    print("🎉 Scoring selesai!")
