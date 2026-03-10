from data.database import db
from scheduler.jobs import fetch_full_market_scan
from loguru import logger
import sys

def verify_phase7():
    print("\n🧪 VERIFIKASI FASE 7 — FULL MARKET SCREENING\n")
    
    # 1. Pastikan tabel ada
    db.create_all_tables()
    
    # 2. Ambil emiten (kita sudah test ini, tapi pastikan ada di DB)
    rows = db.execute("SELECT COUNT(*) as count FROM daftar_emiten")
    print(f"Emiten di database: {rows[0]['count']}")
    
    if rows[0]['count'] == 0:
        print("Mendaftarkan emiten first time...")
        from data.fetcher.stock_fetcher import fetch_all_idx_tickers
        fetch_all_idx_tickers()
    
    # 3. Jalankan Scan (Kita batasi test ini ke 20 saham saja untuk kecepatan verifikasi)
    # Tapi karena fetch_full_market_scan mengambil SEMUA, kita panggil manual sebagian kodenya saja
    
    from data.fetcher.stock_fetcher import fetch_and_save_batch
    from analysis.screening import run_full_screening
    from datetime import date
    
    test_tickers = ['BBCA', 'TLKM', 'BMRI', 'ASII', 'GOTO', 'ADRO', 'ITMG', 'PTBA', 'UNVR', 'ICBP']
    print(f"Running partial scan for {len(test_tickers)} stocks...")
    
    # Fetch data
    fetch_and_save_batch(test_tickers, include_info=False)
    
    # Screening
    results = run_full_screening(test_tickers)
    print(f"Screening results: {len(results)} stocks passed L1/L2.")
    
    # Save to watchlist
    today = date.today().isoformat()
    db.execute("DELETE FROM watchlist_harian WHERE tanggal = ?", (today,))
    
    data_to_db = []
    for i, r in enumerate(results[:5], 1):
        score_total = r['technical']['raw_score'] + r['volume']['raw_score']
        data_to_db.append((
            today, r['kode'], i, r['technical']['raw_score'], r['volume']['raw_score'], score_total, today
        ))
        print(f"  #{i} {r['kode']} - Score: {score_total}")
        
    db.execute_many("INSERT INTO watchlist_harian VALUES (?,?,?,?,?,?,?)", data_to_db)
    print("\n✅ Watchlist harian berhasil di-update.")
    
    # 4. Verifikasi pengambilan di /sinyal
    rows = db.execute("SELECT * FROM watchlist_harian ORDER BY rank")
    print(f"\n📊 Isi Watchlist Harian ({today}):")
    for r in rows:
        print(f"  {r['rank']}. {r['kode']} (Skor: {r['total_composite']})")

if __name__ == "__main__":
    verify_phase7()
