"""
sentiment.py — Analisis sentimen berita via DeepSeek (OpenRouter).

Fungsi:
- Kirim berita ke AI → terima sentimen + confidence
- Filter berita clickbait/bohong (confidence < 30%)
- Update tabel berita dengan hasil sentimen
"""

import sys
import json
from pathlib import Path

from openai import OpenAI
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, DEEPSEEK_MODEL
from data.database import db
from ai.prompts import SENTIMENT_PROMPT


# ── OpenRouter Client ────────────────────────────────
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)


def analyze_sentiment(judul: str, ringkasan: str = "") -> dict:
    """
    Kirim satu berita ke AI dan terima analisis sentimen.
    
    Returns:
        {
            'sentimen': 'positif'|'negatif'|'netral',
            'confidence': 0-100,
            'emiten': ['BBCA', ...],
            'alasan': '...'
        }
    """
    content = f"Judul: {judul}"
    if ringkasan:
        content += f"\nRingkasan: {ringkasan[:300]}"
    
    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": SENTIMENT_PROMPT},
                {"role": "user", "content": content},
            ],
            max_tokens=200,
            temperature=0.3,  # Rendah untuk konsistensi
        )
        
        reply = response.choices[0].message.content.strip()
        
        # Parse JSON dari response
        # Bersihkan jika ada markdown code block
        if reply.startswith("```"):
            reply = reply.split("```")[1]
            if reply.startswith("json"):
                reply = reply[4:]
        
        result = json.loads(reply)
        
        # Validasi
        result['sentimen'] = result.get('sentimen', 'netral').lower()
        result['confidence'] = min(max(int(result.get('confidence', 50)), 0), 100)
        result['emiten'] = result.get('emiten', [])
        result['alasan'] = result.get('alasan', '')
        
        # Log usage
        usage = response.usage
        logger.info(
            f"Sentimen: {result['sentimen']} ({result['confidence']}%) | "
            f"Tokens: {usage.prompt_tokens}+{usage.completion_tokens}={usage.total_tokens}"
        )
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e} | Raw: {reply[:100]}")
        return {'sentimen': 'netral', 'confidence': 0, 'emiten': [], 'alasan': 'Parse error'}
    except Exception as e:
        logger.error(f"AI sentiment error: {e}")
        return {'sentimen': 'netral', 'confidence': 0, 'emiten': [], 'alasan': str(e)}


def process_unprocessed_news(limit: int = 10) -> int:
    """
    Proses berita yang belum dianalisis (processed=0).
    Update tabel berita dengan hasil sentimen.
    Returns jumlah berita yang diproses.
    """
    rows = db.execute(
        "SELECT id, judul, isi_ringkas FROM berita WHERE processed = 0 ORDER BY tanggal DESC LIMIT ?",
        (limit,),
    )
    
    if not rows:
        logger.info("Tidak ada berita baru untuk diproses.")
        return 0
    
    processed = 0
    
    for row in rows:
        r = dict(row)
        result = analyze_sentiment(r['judul'], r.get('isi_ringkas', ''))
        
        # Update DB
        emiten_str = ','.join(result['emiten']) if result['emiten'] else None
        
        db.execute(
            """UPDATE berita SET 
               sentimen = ?, confidence = ?, emiten_terkait = ?, processed = 1
               WHERE id = ?""",
            (result['sentimen'], result['confidence'], emiten_str, r['id']),
        )
        
        processed += 1
        logger.info(f"  [{r['id']}] {result['sentimen']} ({result['confidence']}%) — {r['judul'][:50]}...")
    
    logger.info(f"Selesai proses {processed} berita.")
    return processed


def get_sentiment_summary() -> dict:
    """
    Hitung ringkasan sentimen dari berita yang sudah diproses.
    Returns: {'positif': n, 'negatif': n, 'netral': n, 'avg_confidence': float}
    """
    rows = db.execute(
        """SELECT sentimen, COUNT(*) as cnt, AVG(confidence) as avg_conf
           FROM berita WHERE processed = 1 AND confidence > 30
           GROUP BY sentimen"""
    )
    
    summary = {'positif': 0, 'negatif': 0, 'netral': 0, 'avg_confidence': 0}
    total_conf = 0
    total_count = 0
    
    for row in rows:
        r = dict(row)
        sentimen = r['sentimen']
        if sentimen in summary:
            summary[sentimen] = r['cnt']
            total_conf += r['avg_conf'] * r['cnt']
            total_count += r['cnt']
    
    if total_count > 0:
        summary['avg_confidence'] = total_conf / total_count
    
    return summary


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    print("\n🧠 AI Sentiment Analysis — Test\n")
    print("Memproses 5 berita terbaru...\n")
    
    count = process_unprocessed_news(limit=5)
    
    # Tampilkan hasil
    print(f"\n📊 Hasil Analisis Sentimen:")
    print("-" * 60)
    
    results = db.execute(
        """SELECT judul, sumber, sentimen, confidence, emiten_terkait
           FROM berita WHERE processed = 1
           ORDER BY tanggal DESC LIMIT 5"""
    )
    
    for r in results:
        r = dict(r)
        emoji = "🟢" if r['sentimen'] == 'positif' else ("🔴" if r['sentimen'] == 'negatif' else "⚪")
        conf = r['confidence'] or 0
        emiten = r.get('emiten_terkait', '-') or '-'
        
        print(f"\n  {emoji} [{r['sentimen'].upper()} {conf}%] {r['judul'][:55]}...")
        print(f"     Sumber: {r['sumber']} | Emiten: {emiten}")
    
    # Summary
    summary = get_sentiment_summary()
    print(f"\n📈 Ringkasan:")
    print(f"  Positif: {summary['positif']} | Negatif: {summary['negatif']} | Netral: {summary['netral']}")
    print(f"  Avg Confidence: {summary['avg_confidence']:.0f}%")
    
    print(f"\n🎉 Sentimen analysis selesai! ({count} berita diproses)")
