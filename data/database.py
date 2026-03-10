"""
database.py — SQLite database manager untuk IDX AI Trading Assistant.
Membuat dan mengelola 11 tabel utama sesuai master prompt.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from loguru import logger

# Impor konfigurasi
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DATABASE_PATH


class Database:
    """SQLite database manager dengan context manager support."""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._ensure_dir()

    def _ensure_dir(self):
        """Pastikan direktori database ada."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self):
        """Context manager untuk koneksi database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def execute(self, query: str, params: tuple = ()):
        """Execute sebuah query dan return rows."""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()

    def execute_many(self, query: str, data: list):
        """Execute batch insert/update."""
        with self.get_connection() as conn:
            conn.executemany(query, data)

    def create_all_tables(self):
        """Buat semua 11 tabel yang dibutuhkan sistem."""
        with self.get_connection() as conn:
            # ─── Tabel 1: harga_historis ─────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS harga_historis (
                    kode TEXT NOT NULL,
                    tanggal DATE NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    value REAL,
                    PRIMARY KEY (kode, tanggal)
                )
            """)

            # ─── Tabel 2: daftar_emiten ──────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daftar_emiten (
                    kode TEXT PRIMARY KEY,
                    nama TEXT,
                    sektor TEXT,
                    subsektor TEXT,
                    papan TEXT,
                    listed_date DATE,
                    market_cap REAL,
                    is_suspended INTEGER DEFAULT 0,
                    last_update DATE
                )
            """)

            # ─── Tabel 3: fundamental ────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fundamental (
                    kode TEXT NOT NULL,
                    periode TEXT NOT NULL,
                    revenue REAL,
                    net_income REAL,
                    total_assets REAL,
                    total_equity REAL,
                    total_debt REAL,
                    current_assets REAL,
                    current_liabilities REAL,
                    operating_cashflow REAL,
                    gross_profit REAL,
                    ebit REAL,
                    roa REAL,
                    roe REAL,
                    der REAL,
                    per REAL,
                    pbv REAL,
                    eps REAL,
                    retained_earnings REAL,
                    working_capital REAL,
                    f_score INTEGER,
                    z_score REAL,
                    last_update DATE,
                    PRIMARY KEY (kode, periode)
                )
            """)

            # ─── Tabel 4: berita ─────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS berita (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    judul TEXT,
                    url TEXT,
                    sumber TEXT,
                    tanggal DATETIME,
                    isi_ringkas TEXT,
                    emiten_terkait TEXT,
                    sentimen TEXT,
                    confidence REAL,
                    processed INTEGER DEFAULT 0
                )
            """)

            # ─── Tabel 5: makro_data ─────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS makro_data (
                    tanggal DATE PRIMARY KEY,
                    ihsg_change REAL,
                    nikkei_change REAL,
                    hsi_change REAL,
                    sti_change REAL,
                    usd_idr REAL,
                    gold_change REAL,
                    oil_change REAL,
                    market_label TEXT,
                    narasi TEXT
                )
            """)

            # ─── Tabel 6: sinyal_history ─────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sinyal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kode TEXT,
                    tanggal DATE,
                    waktu TEXT,
                    skor_total REAL,
                    label TEXT,
                    entry_low REAL,
                    entry_high REAL,
                    target REAL,
                    stoploss REAL,
                    rr_ratio REAL,
                    confidence REAL,
                    alasan TEXT,
                    risk_warning TEXT,
                    status TEXT DEFAULT 'ACTIVE'
                )
            """)

            # ─── Tabel 7: portfolio_config ───────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_config (
                    user_id TEXT DEFAULT 'default' PRIMARY KEY,
                    modal_awal REAL,
                    risk_profile TEXT,
                    max_posisi INTEGER DEFAULT 5,
                    max_per_saham_pct REAL DEFAULT 0.30
                )
            """)

            # ─── Tabel 8: posisi_aktif ───────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS posisi_aktif (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kode TEXT,
                    lot INTEGER,
                    harga_beli REAL,
                    harga_terkini REAL,
                    unrealized_pnl REAL,
                    tanggal_beli DATE,
                    stoploss_set REAL,
                    target_set REAL,
                    label_sinyal TEXT
                )
            """)

            # ─── Tabel 9: historis_trade ─────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS historis_trade (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kode TEXT,
                    lot INTEGER,
                    harga_beli REAL,
                    harga_jual REAL,
                    tanggal_beli DATE,
                    tanggal_jual DATE,
                    pnl REAL,
                    pnl_pct REAL,
                    label_sinyal TEXT,
                    hit INTEGER
                )
            """)

            # ─── Tabel 10: dana_snapshot ─────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dana_snapshot (
                    tanggal DATE PRIMARY KEY,
                    total_portfolio REAL,
                    cash REAL,
                    invested REAL,
                    return_pct REAL
                )
            """)

            # ─── Tabel 11: kalender_ekonomi ──────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kalender_ekonomi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tanggal DATE,
                    event_type TEXT,
                    kode TEXT,
                    deskripsi TEXT,
                    impact TEXT
                )
            """)

            # ─── Tabel 12: watchlist_harian ──────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist_harian (
                    tanggal DATE NOT NULL,
                    kode TEXT NOT NULL,
                    rank INTEGER,
                    skor_l2 REAL,
                    skor_l3 REAL,
                    total_composite REAL,
                    last_update DATETIME,
                    PRIMARY KEY (tanggal, kode)
                )
            """)

            # ─── Indeks tambahan untuk performa ──────────
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_berita_tanggal
                ON berita(tanggal)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sinyal_kode_tanggal
                ON sinyal_history(kode, tanggal)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fundamental_kode
                ON fundamental(kode)
            """)

            logger.info("✅ Semua 11 tabel berhasil dibuat/diverifikasi.")

    # ── Portfolio Config CRUD ─────────────────────────
    def get_portfolio_config(self, user_id: str = "default") -> dict:
        """Ambil portfolio config aktif."""
        rows = self.execute(
            "SELECT * FROM portfolio_config WHERE user_id = ?", (user_id,)
        )
        if rows:
            return dict(rows[0])
        return {}

    def update_portfolio_config(self, user_id: str = "default", **kwargs):
        """
        Update portfolio config secara dinamis.
        Contoh: db.update_portfolio_config(modal_awal=50_000_000, max_posisi=10)
        """
        valid_fields = {"modal_awal", "risk_profile", "max_posisi", "max_per_saham_pct"}
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}

        if not updates:
            logger.warning("Tidak ada field valid untuk di-update.")
            return

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [user_id]

        self.execute(
            f"UPDATE portfolio_config SET {set_clause} WHERE user_id = ?",
            tuple(values),
        )
        logger.info(f"Portfolio config updated: {updates}")

    def show_portfolio_config(self, user_id: str = "default"):
        """Tampilkan portfolio config ke console."""
        config = self.get_portfolio_config(user_id)
        if not config:
            print("⚠️ Belum ada portfolio config.")
            return

        print("\n💼 Portfolio Config Saat Ini:")
        print("-" * 40)
        print(f"  Modal Awal    : Rp {config['modal_awal']:>15,.0f}")
        print(f"  Risk Profile  : {config['risk_profile']}")
        print(f"  Max Posisi    : {config['max_posisi']} saham")
        print(f"  Max Per Saham : {config['max_per_saham_pct'] * 100:.0f}%")
        print("-" * 40)

    def get_table_list(self) -> list:
        """Return daftar semua tabel di database."""
        rows = self.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row["name"] for row in rows]

    def get_table_info(self, table_name: str) -> list:
        """Return info kolom untuk sebuah tabel."""
        rows = self.execute(f"PRAGMA table_info({table_name})")
        return [dict(row) for row in rows]

    def count_rows(self, table_name: str) -> int:
        """Hitung jumlah baris di sebuah tabel."""
        rows = self.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
        return rows[0]["cnt"]


# ── Singleton instance ───────────────────────────────────
db = Database()


if __name__ == "__main__":
    """Quick test: buat database dan tampilkan semua tabel."""
    print("=" * 50)
    print("IDX AI Trading Assistant — Database Setup")
    print("=" * 50)

    db.create_all_tables()

    tables = db.get_table_list()
    print(f"\n📊 Total tabel: {len(tables)}")
    print("-" * 50)

    for t in tables:
        cols = db.get_table_info(t)
        col_names = [c["name"] for c in cols]
        print(f"  ✅ {t} ({len(cols)} kolom): {', '.join(col_names)}")

    print("-" * 50)
    expected = 11
    if len(tables) >= expected:
        print(f"\n🎉 SUKSES! Semua {expected} tabel berhasil dibuat.")
    else:
        print(f"\n❌ GAGAL! Hanya {len(tables)}/{expected} tabel ditemukan.")
