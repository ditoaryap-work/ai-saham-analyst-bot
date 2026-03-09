"""
main.py — Entry point IDX AI Trading Assistant.

Fase 1: Inisialisasi database dan verifikasi struktur.
Fase selanjutnya akan menambahkan scheduler, bot, dsb.
"""

import sys
from pathlib import Path

# Pastikan root project ada di Python path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    DATABASE_PATH, MODAL_AWAL, RISK_PROFILE,
    MAX_POSISI, MAX_PER_SAHAM_PCT, TEST_STOCKS
)
from data.database import db
from utils.logger import logger


def init_database():
    """Inisialisasi database: buat tabel dan set default portfolio config."""
    logger.info("Memulai inisialisasi database...")
    db.create_all_tables()

    # Insert default portfolio config jika belum ada
    existing = db.execute(
        "SELECT * FROM portfolio_config WHERE user_id = 'default'"
    )
    if not existing:
        db.execute(
            """INSERT INTO portfolio_config
               (user_id, modal_awal, risk_profile, max_posisi, max_per_saham_pct)
               VALUES (?, ?, ?, ?, ?)""",
            ("default", MODAL_AWAL, RISK_PROFILE, MAX_POSISI, MAX_PER_SAHAM_PCT),
        )
        logger.info(f"Portfolio config default dibuat: modal={MODAL_AWAL:,.0f}")

    # Insert dana_snapshot awal jika belum ada
    from datetime import date
    existing_snap = db.execute(
        "SELECT * FROM dana_snapshot ORDER BY tanggal DESC LIMIT 1"
    )
    if not existing_snap:
        db.execute(
            """INSERT INTO dana_snapshot
               (tanggal, total_portfolio, cash, invested, return_pct)
               VALUES (?, ?, ?, ?, ?)""",
            (date.today().isoformat(), MODAL_AWAL, MODAL_AWAL, 0, 0),
        )
        logger.info(f"Dana snapshot awal dibuat: Rp {MODAL_AWAL:,.0f}")


def verify_setup():
    """Verifikasi bahwa semua komponen Fase 1 siap."""
    logger.info("=" * 50)
    logger.info("VERIFIKASI FASE 1 — FONDASI")
    logger.info("=" * 50)

    # 1. Cek tabel
    tables = db.get_table_list()
    expected_tables = [
        "berita", "dana_snapshot", "daftar_emiten", "fundamental",
        "historis_trade", "kalender_ekonomi", "makro_data",
        "portfolio_config", "posisi_aktif", "sinyal_history",
        "harga_historis"
    ]

    logger.info(f"\n📊 Database: {DATABASE_PATH}")
    logger.info(f"   Tabel ditemukan: {len(tables)}")

    all_found = True
    for t in sorted(expected_tables):
        if t in tables:
            cols = db.get_table_info(t)
            rows = db.count_rows(t)
            logger.info(f"   ✅ {t} ({len(cols)} kolom, {rows} baris)")
        else:
            logger.error(f"   ❌ {t} — TIDAK DITEMUKAN!")
            all_found = False

    # 2. Cek portfolio config
    config = db.execute("SELECT * FROM portfolio_config WHERE user_id='default'")
    if config:
        c = dict(config[0])
        logger.info(f"\n💼 Portfolio Config:")
        logger.info(f"   Modal: Rp {c['modal_awal']:,.0f}")
        logger.info(f"   Profil: {c['risk_profile']}")
        logger.info(f"   Max posisi: {c['max_posisi']}")
        logger.info(f"   Max per saham: {c['max_per_saham_pct'] * 100:.0f}%")

    # 3. Cek test stocks
    logger.info(f"\n🧪 Test Stocks: {', '.join(TEST_STOCKS)}")

    # 4. Summary
    logger.info("\n" + "=" * 50)
    if all_found and len(tables) >= 11:
        logger.info("🎉 FASE 1 SELESAI — Semua fondasi siap!")
        logger.info("   Lanjut ke Fase 2: Data Layer (yfinance)")
    else:
        logger.error("❌ FASE 1 GAGAL — Ada komponen yang hilang.")
    logger.info("=" * 50)


if __name__ == "__main__":
    print("\n🚀 IDX AI Trading Assistant — Inisialisasi\n")
    init_database()
    verify_setup()
