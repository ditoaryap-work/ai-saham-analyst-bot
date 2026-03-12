"""
agents.py — 5 Agent AI System via DeepSeek (OpenRouter).
ALIGNED WITH MASTER PROMPT.

Agent 1: Macro Context (temp 0.3)
Agent 2: Technical Analyst (temp 0.2)
Agent 3: Fundamental + Sentiment (temp 0.2)
Agent 4: Bull vs Bear Debate (temp 0.7 vs 0.3)
Agent 5: Risk Management + Fund Manager (temp 0.1)
"""

import sys
import json
from pathlib import Path
from datetime import date


from loguru import logger
from .llm import _call_ai

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL, DEEPSEEK_MODEL, TEST_STOCKS
)
from data.database import db
from ai.prompts import BRIEFING_PROMPT, SIGNAL_PROMPT, RISK_PROMPT
from ai.sentiment import process_unprocessed_news, get_sentiment_summary
from analysis.technical import calculate_indicators, get_technical_summary
from analysis.scoring import calculate_composite_score, format_score_report, format_table_for_ai
from analysis.reflection import get_latest_guidelines










def _parse_json(reply: str) -> dict:
    """Parse JSON dari AI reply, handle markdown code blocks."""
    try:
        if reply.startswith("```"):
            reply = reply.split("```")[1]
            if reply.startswith("json"):
                reply = reply[4:]
        return json.loads(reply)
    except (json.JSONDecodeError, IndexError):
        return {}


def _build_tech_table(indicators: dict) -> str:
    """Format indikator sebagai tabel terstruktur (master prompt requirement)."""
    if not indicators:
        return "Data tidak tersedia"

    rsi = indicators.get('rsi', 0)
    rsi_sig = "Sweet Spot" if 40 <= rsi <= 55 else ("Kuat" if rsi <= 65 else ("Overbought" if rsi > 70 else "Oversold"))

    macd_sig = "Golden X" if indicators.get('macd_bullish') and indicators.get('macd_expanding') else (
        "Bullish" if indicators.get('macd_bullish') else "Bearish")

    ema_sig = "Golden" if indicators.get('ema_aligned') else ("Above 200" if indicators.get('above_ema200') else "Bearish")

    vol_r = indicators.get('vol_ratio', 0)
    vol_sig = f"Spike+Up" if vol_r > 1.5 and indicators.get('candle_bullish') else (
        f"Normal" if vol_r > 0.8 else "Kering")

    adx = indicators.get('adx', 0)
    lines = [
        "| Indikator | Nilai | Signal | Strength |",
        "|-----------|-------|--------|----------|",
        f"| EMA Align | {ema_sig} | {'Bullish' if indicators.get('ema_aligned') else 'Bearish'} | {'Strong' if indicators.get('ema_aligned') else 'Weak'} |",
        f"| RSI(14) | {rsi:.1f} | {rsi_sig} | {'Strong' if 40 <= rsi <= 55 else 'Medium'} |",
        f"| Stoch | {indicators.get('stoch_k', 0):.0f}/{indicators.get('stoch_d', 0):.0f} | {'Cross↑' if indicators.get('stoch_bullish') else 'Down'} | {'Strong' if indicators.get('stoch_oversold') and indicators.get('stoch_bullish') else 'Medium'} |",
        f"| MACD | {indicators.get('macd_hist', 0):+.3f} | {macd_sig} | {'Strong' if indicators.get('macd_expanding') else 'Weak'} |",
        f"| BB%B | {indicators.get('bb_position', 0):.2f} | {'Squeeze!' if indicators.get('bb_squeeze') else 'Normal'} | {'Strong' if indicators.get('bb_squeeze') else 'OK'} |",
        f"| ATR% | {indicators.get('atr_pct', 0):.1f}% | {'Good' if indicators.get('atr_pct', 0) > 2 else 'Low'} | OK |",
        f"| ADX | {adx:.0f} | {'Trend' if adx > 25 else 'Sideways'} | {'Strong' if adx > 25 else 'Weak'} |",
        f"| Volume | {vol_r:.1f}x | {vol_sig} | {'Strong' if vol_r > 1.5 else 'Weak'} |",
        f"| OBV | {'Rising' if indicators.get('obv_rising') else 'Falling'} | {'Accumulation' if indicators.get('obv_rising') else 'Distribution'} | {'Strong' if indicators.get('obv_rising') else 'Weak'} |",
        f"| Pivot | S1={indicators.get('support1', 0):,.0f} R1={indicators.get('resist1', 0):,.0f} | {'Above R1' if indicators.get('close', 0) > indicators.get('resist1', 0) else 'Normal'} | OK |",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# AGENT 1: Macro Context (temp 0.3)
# ═══════════════════════════════════════════════════════

def agent1_macro_context() -> dict:
    """Agent 1: Macro context analysis. Returns JSON."""
    macro = db.execute("SELECT * FROM makro_data ORDER BY tanggal DESC LIMIT 1")
    if not macro:
        return {'market_label': 'MIXED', 'market_narrative': 'Data belum tersedia'}

    m = dict(macro[0])
    sentiment = get_sentiment_summary()

    data = f"""
| Indeks | Change |
|--------|--------|
| IHSG | {m.get('ihsg_change', 0):+.2%} |
| Nikkei | {m.get('nikkei_change', 0):+.2%} |
| Hang Seng | {m.get('hsi_change', 0):+.2%} |
| STI | {m.get('sti_change', 0):+.2%} |
| Gold | {m.get('gold_change', 0):+.2%} |
| Oil | {m.get('oil_change', 0):+.2%} |

Market Label saat ini: {m.get('market_label', 'MIXED')}
Sentimen Berita: {sentiment['positif']} positif, {sentiment['negatif']} negatif
"""

    reply = _call_ai(BRIEFING_PROMPT, data, max_tokens=400, temperature=0.3)
    return {'market_label': m.get('market_label'), 'narrative': reply}


# ═══════════════════════════════════════════════════════
# AGENT 2: Technical Analyst (temp 0.2)
# ═══════════════════════════════════════════════════════

TECH_SYSTEM = """Kamu adalah technical analyst profesional IDX.
Analisa tabel indikator berikut dan berikan verdict.
Output JSON ONLY:
{
  "kode": "XXXX",
  "technical_verdict": "BULLISH/BEARISH/NEUTRAL",
  "key_signals": ["signal 1", "signal 2", "signal 3"],
  "support": angka,
  "resistance": angka,
  "entry_zone": [low, high]
}"""

def agent2_technical(kode: str, indicators: dict) -> dict:
    """Agent 2: Technical analysis, temp 0.2."""
    table = _build_tech_table(indicators)
    data = f"Kode: {kode}\nHarga: Rp {indicators.get('close', 0):,.0f}\n\n{table}"

    reply = _call_ai(TECH_SYSTEM, data, max_tokens=250, temperature=0.2)
    result = _parse_json(reply)
    if not result:
        result = {'technical_verdict': 'NEUTRAL', 'key_signals': [reply[:100]]}
    result['kode'] = kode
    return result


# ═══════════════════════════════════════════════════════
# AGENT 3: Fundamental + Sentiment (temp 0.2)
# ═══════════════════════════════════════════════════════

FUNDSENT_SYSTEM = """Kamu adalah fundamental analyst + sentiment analyst IDX.
Analisa F-Score, Z-Score, dan sentimen berikut.
Output JSON ONLY:
{
  "kode": "XXXX",
  "fundamental_verdict": "STRONG/AVERAGE/WEAK",
  "f_score": n,
  "z_score": n,
  "fundamental_highlights": ["highlight 1"],
  "sentiment_verdict": "POSITIVE/NEUTRAL/NEGATIVE",
  "red_flags": []
}"""

def agent3_fundamental_sentiment(kode: str, score_result: dict) -> dict:
    """Agent 3: Fundamental + Sentiment combined, temp 0.2."""
    d3 = score_result.get('d3_fundamental', {})
    d4 = score_result.get('d4_sentiment', {})

    data = f"""Kode: {kode}
F-Score: {d3.get('f_score', 0)}/9 {'(BANK modifier applied)' if d3.get('is_bank') else ''}
Z-Score: {d3.get('z_score', 0):.2f}
Detail F: {', '.join(d3.get('details', []))}
Detail Sentimen: {', '.join(d4.get('details', []))}"""

    reply = _call_ai(FUNDSENT_SYSTEM, data, max_tokens=250, temperature=0.2)
    result = _parse_json(reply)
    if not result:
        result = {'fundamental_verdict': 'AVERAGE', 'sentiment_verdict': 'NEUTRAL'}
    result['kode'] = kode
    return result


# ═══════════════════════════════════════════════════════
# AGENT 4: Bull vs Bear Debate (temp 0.7 vs 0.3)
# ═══════════════════════════════════════════════════════

BULL_SYSTEM = """Berikan 3 argumen TERKUAT mengapa saham ini LAYAK DIBELI.
Fokus pada potensi upside. Bahasa Indonesia, ringkas.
Output JSON: {"arguments": ["arg1", "arg2", "arg3"]}"""

BEAR_SYSTEM = """Berikan 3 argumen TERKUAT mengapa saham ini BERBAHAYA DIBELI.
Fokus pada risiko downside. Bahasa Indonesia, ringkas.
Output JSON: {"arguments": ["arg1", "arg2", "arg3"]}"""

def agent4_bull_vs_bear(kode: str, indicators: dict, score_result: dict) -> dict:
    """
    Agent 4: Bull vs Bear Debate.
    Bull: temp 0.7 (lebih kreatif/optimis)
    Bear: temp 0.3 (lebih konservatif/pesimis)
    """
    tech_table = _build_tech_table(indicators)
    score_table = format_table_for_ai(score_result)

    data = f"Kode: {kode}\nHarga: Rp {indicators.get('close', 0):,.0f}\n\n{tech_table}\n\n{score_table}"

    # Bull call (temp 0.7)
    bull_reply = _call_ai(BULL_SYSTEM, data, max_tokens=200, temperature=0.7)
    bull = _parse_json(bull_reply)
    bull_args = bull.get('arguments', [bull_reply[:100]]) if bull else [bull_reply[:100]]

    # Bear call (temp 0.3)
    bear_reply = _call_ai(BEAR_SYSTEM, data, max_tokens=200, temperature=0.3)
    bear = _parse_json(bear_reply)
    bear_args = bear.get('arguments', [bear_reply[:100]]) if bear else [bear_reply[:100]]

    # Verdict berdasarkan scoring
    total = score_result.get('total', 0)
    if total >= 60:
        verdict = "BULL_WIN"
        confidence = min(90, total)
    elif total >= 45:
        verdict = "DRAW"
        confidence = 50
    else:
        verdict = "BEAR_WIN"
        confidence = max(20, 100 - total)

    # Confidence < 60 → auto SKIP
    if confidence < 60:
        label_override = "SKIP"
    else:
        label_override = None

    result = {
        'kode': kode,
        'bull_arguments': bull_args,
        'bear_arguments': bear_args,
        'debate_verdict': verdict,
        'confidence': confidence,
        'label_override': label_override,
    }

    logger.info(f"[{kode}] Debate: {verdict} (conf={confidence}%)")
    return result


# ═══════════════════════════════════════════════════════
# AGENT 5: Risk Management + Fund Manager (temp 0.1)
# ═══════════════════════════════════════════════════════

def agent5_risk_manager(kode: str, all_results: dict) -> dict:
    """
    Agent 5: Final decision. temp 0.1 (paling konservatif).
    Returns sinyal final dengan entry/target/SL.
    """
    tech = all_results.get('agent2', {})
    fund = all_results.get('agent3', {})
    debate = all_results.get('agent4', {})
    score = all_results.get('score', {})
    market = all_results.get('market', {})

    # Injeksi pedoman belajar AI (Self-Learning)
    guidelines = get_latest_guidelines()
    guideline_text = f"\n[PENTING - PEDOMAN HASIL BELAJAR SEBELUMNYA]:\n{guidelines}\n" if guidelines else ""

    data = f"""Kode: {kode}
Market: {market.get('market_label', 'UNKNOWN')}
{guideline_text}
Scoring: {format_table_for_ai(score)}

Technical Verdict: {tech.get('technical_verdict', 'N/A')}
Key Signals: {', '.join(tech.get('key_signals', []))}
Support: {tech.get('support', 0)} | Resistance: {tech.get('resistance', 0)}

Fundamental: {fund.get('fundamental_verdict', 'N/A')}
Sentiment: {fund.get('sentiment_verdict', 'N/A')}
Red Flags: {', '.join(fund.get('red_flags', []))}

Debate: {debate.get('debate_verdict', 'N/A')} (conf={debate.get('confidence', 0)}%)
Bull: {', '.join(debate.get('bull_arguments', [])[:2])}
Bear: {', '.join(debate.get('bear_arguments', [])[:2])}

Skor Total: {score.get('total', 0)}/100 → {score.get('label', 'SKIP')}"""

    reply = _call_ai(SIGNAL_PROMPT, data, max_tokens=300, temperature=0.1)
    result = _parse_json(reply)

    if not result:
        result = {
            'rekomendasi': score.get('label', 'SKIP'),
            'confidence': debate.get('confidence', 0),
            'alasan': reply[:200],
        }

    # Override label jika confidence < 60
    if debate.get('label_override') == 'SKIP':
        result['rekomendasi'] = 'SKIP'

    result['kode'] = kode
    logger.info(f"[{kode}] Agent5: {result.get('rekomendasi', 'N/A')} conf={result.get('confidence', 0)}%")
    return result


# ═══════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════

def run_full_analysis(stock_list: list = None) -> dict:
    """Jalankan semua 5 agent → laporan final."""
    if stock_list is None:
        stock_list = TEST_STOCKS

    logger.info("=" * 60)
    logger.info("🤖 ORCHESTRATOR — 5 Agent Analysis")
    logger.info("=" * 60)

    output = {
        'tanggal': date.today().isoformat(),
        'sentimen_processed': 0,
        'market': {},
        'signals': {},
    }

    # Step 1: Sentimen
    logger.info("\n📰 Step 1: Sentimen Berita...")
    output['sentimen_processed'] = process_unprocessed_news(limit=5)

    # Step 2: Agent 1 — Macro
    logger.info("\n🌍 Step 2: Agent 1 — Macro Context...")
    output['market'] = agent1_macro_context()

    # Steps 3-6: Per saham
    for kode in stock_list:
        logger.info(f"\n{'─'*40}\n📊 Analyzing {kode}...")

        indicators = calculate_indicators(kode)
        if not indicators:
            continue

        score = calculate_composite_score(kode, indicators=indicators)

        a2 = agent2_technical(kode, indicators)
        a3 = agent3_fundamental_sentiment(kode, score)
        a4 = agent4_bull_vs_bear(kode, indicators, score)

        all_results = {
            'agent2': a2, 'agent3': a3, 'agent4': a4,
            'score': score, 'market': output['market'],
        }

        a5 = agent5_risk_manager(kode, all_results)

        output['signals'][kode] = {
            'score': score,
            'technical': a2,
            'fundamental': a3,
            'debate': a4,
            'final': a5,
        }

    logger.info(f"\n{'═'*60}")
    logger.info("🎉 ORCHESTRATOR SELESAI!")
    return output


def format_full_report(result: dict) -> str:
    """Format laporan final untuk display."""
    lines = [
        f"📋 LAPORAN AI TRADING — {result['tanggal']}",
        "=" * 50,
        f"\n🌍 MARKET: {result['market'].get('market_label', '-')}",
        result['market'].get('narrative', '')[:300],
        f"\n📰 SENTIMEN: {result['sentimen_processed']} berita diproses",
        f"\n📊 SINYAL SAHAM:",
        "-" * 40,
    ]

    for kode, data in result.get('signals', {}).items():
        f = data['final']
        s = data['score']
        d = data['debate']

        rek = f.get('rekomendasi', 'SKIP')
        emoji = s.get('emoji', '❌')

        lines.append(f"\n{emoji} {kode} — {rek} (skor: {s['total']}/100)")
        lines.append(f"   Debate: {d.get('debate_verdict', '-')} (conf: {d.get('confidence', 0)}%)")

        if f.get('entry_low'):
            lines.append(f"   Entry: Rp {f['entry_low']:,.0f}-{f['entry_high']:,.0f}")
            lines.append(f"   Target: Rp {f.get('target', 0):,.0f} | SL: Rp {f.get('stoploss', 0):,.0f}")

        lines.append(f"   📈 Bull: {d.get('bull_arguments', ['?'])[0]}")
        lines.append(f"   📉 Bear: {d.get('bear_arguments', ['?'])[0]}")

        if f.get('alasan'):
            lines.append(f"   💡 {f['alasan'][:150]}")
        if f.get('risk_warning'):
            lines.append(f"   ⚠️ {f['risk_warning']}")

    return "\n".join(lines)


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    print("\n🤖 IDX AI Trading Assistant — 5 Agent System\n")
    result = run_full_analysis(["BBCA", "BMRI", "ASII"])
    report = format_full_report(result)
    print("\n" + report)
