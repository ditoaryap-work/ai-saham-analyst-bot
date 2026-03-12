"""
analysis/reflection.py — AI Self-Learning (Feedback Loop)

Fungsi:
- Mengambil 5 trade terbaik (win) dan 5 terburuk (loss) dari sinyal_history.
- Meminta AI (DeepSeek) melakukan otopsi: mencari korelasi kenapa gagal/sukses.
- Menghasilkan 'AI Guidelines' baru untuk disuntikkan ke prompt utama.
"""

import sys
from pathlib import Path
from datetime import date, timedelta
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db
from ai.agents import _call_ai

def get_recent_performance_data(days: int = 7):
    """
    Ambil data sinyal yang sudah 'closed' (kena TP atau SL) dalam D hari terakhir.
    """
    start_date = (date.today() - timedelta(days=days)).isoformat()
    
    # Ambil sinyal history yang statusnya bukan ACTIVE atau yang sudah lewat seminggu
    # (Di sistem kita, kita perlu join dengan harga_historis untuk tahu mana yang benar-benar hit)
    # Namun untuk kemudahan, kita asumsikan kita punya data win/loss dari evaluasi performa sebelumnya.
    
    rows = db.execute(
        """SELECT * FROM sinyal_history 
           WHERE tanggal >= ? 
           ORDER BY skor_total DESC""", 
        (start_date,)
    )
    
    wins = []
    losses = []
    
    for r in rows:
        kode = r['kode']
        t0 = r['tanggal']
        tp = r['target']
        sl = r['stoploss']
        
        # Cek aktual pergerakan harga
        hist = db.execute(
            "SELECT MAX(high) as max_h, MIN(low) as min_l FROM harga_historis WHERE kode = ? AND tanggal >= ?",
            (kode, t0)
        )
        
        if not hist or hist[0]['max_h'] is None:
            continue
            
        max_h = hist[0]['max_h']
        min_l = hist[0]['min_l']
        
        is_win = max_h >= tp if tp else False
        is_loss = min_l <= sl if sl else False
        
        data = {
            'kode': kode,
            'tanggal': t0,
            'skor': r['skor_total'],
            'alasan': r['alasan'],
            'outcome': 'WIN (Target Hit)' if is_win else ('LOSS (Stoploss Hit)' if is_loss else 'ACTIVE')
        }
        
        if is_win:
            wins.append(data)
        elif is_loss:
            losses.append(data)
            
    # Ambil top 5 win dan top 5 loss
    return wins[:5], losses[:5]

def run_weekly_reflection():
    """
    Proses utama evaluasi diri AI.
    """
    logger.info("🧠 Memulai AI Self-Reflection (Weekly Feedback Loop)...")
    
    wins, losses = get_recent_performance_data(14) # Ambil data 2 minggu terakhir agar lebih kaya
    
    if not wins and not losses:
        logger.warning("Tidak cukup data trade untuk melakukan reflection.")
        return None
        
    # Susun context untuk AI
    context = "BERIKUT ADALAH HASIL REKOMENDASI AI DALAM 2 MINGGU TERAKHIR:\n\n"
    
    if wins:
        context += "🏆 SUCCESS TRADES (Target Hit):\n"
        for w in wins:
            context += f"- {w['kode']}: {w['alasan']}\n"
            
    if losses:
        context += "\n💀 FAILED TRADES (Stoploss Hit):\n"
        for l in losses:
            context += f"- {l['kode']}: {l['alasan']}\n"
            
    system_prompt = (
        "Anda adalah Kepala Strategi Investasi (Master Fund Manager). "
        "Tugas Anda adalah melakukan OTOPSI terhadap hasil kerja tim analis Anda (AI). "
        "Berdasarkan data profit dan loss yang diberikan, temukan POLA KESALAHAN dan POLA KEBERHASILAN. "
        "Hasilkan 3-5 PEDOMAN BARU (Trading Guidelines) yang sangat spesifik untuk meningkatkan akurasi minggu depan. "
        "Format output: Berikan poin-poin singkat dalam Bahasa Indonesia."
    )
    
    user_content = (
        f"{context}\n\n"
        "Berdasarkan data di atas, apa pelajaran yang bisa diambil? "
        "Sebutkan 3-5 pedoman (Rules) baru untuk trading minggu depan agar win-rate kita naik."
    )
    
    lessons = _call_ai(system_prompt, user_content, max_tokens=1000, temperature=0.5)
    
    if "Error" in lessons:
        logger.error(f"Gagal melakukan reflection: {lessons}")
        return None
        
    # Simpan hasil reflection ke tabel ai_guidelines (kita buat tabelnya jika belum ada)
    db.execute("""
        CREATE TABLE IF NOT EXISTS ai_guidelines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal DATE,
            guidelines TEXT
        )
    """)
    
    db.execute(
        "INSERT INTO ai_guidelines (tanggal, guidelines) VALUES (?, ?)",
        (date.today().isoformat(), lessons)
    )
    
    logger.info("✅ Reflection selesai dan pedoman baru disimpan.")
    return lessons

def get_latest_guidelines():
    """Ambil pedoman terbaru untuk disuntikkan ke prompt."""
    row = db.execute("SELECT guidelines FROM ai_guidelines ORDER BY tanggal DESC LIMIT 1")
    if row:
        return row[0]['guidelines']
    return None

if __name__ == "__main__":
    res = run_weekly_reflection()
    if res:
        print("\n--- AI RECENT LESSONS ---")
        print(res)
