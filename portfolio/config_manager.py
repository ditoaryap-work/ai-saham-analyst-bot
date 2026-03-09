"""
config_manager.py — CLI untuk mengubah portfolio config secara dinamis.

Cara pakai:
  python portfolio/config_manager.py                     # Lihat config
  python portfolio/config_manager.py modal 50000000      # Ubah modal
  python portfolio/config_manager.py max_posisi 10       # Ubah max posisi
  python portfolio/config_manager.py risk aggressive     # Ubah risk profile
  python portfolio/config_manager.py max_pct 0.25        # Ubah max % per saham
"""

import sys
from pathlib import Path

# Setup path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db


def main():
    args = sys.argv[1:]

    # Tanpa argumen → tampilkan config saat ini
    if not args:
        db.show_portfolio_config()
        print("\n📝 Cara mengubah:")
        print("  python portfolio/config_manager.py modal 50000000")
        print("  python portfolio/config_manager.py max_posisi 10")
        print("  python portfolio/config_manager.py risk moderate|aggressive|conservative")
        print("  python portfolio/config_manager.py max_pct 0.25")
        return

    command = args[0].lower()
    if len(args) < 2:
        print("❌ Masukkan nilai! Contoh: python portfolio/config_manager.py modal 50000000")
        return

    value = args[1]

    if command == "modal":
        amount = float(value)
        db.update_portfolio_config(modal_awal=amount)
        print(f"✅ Modal diubah → Rp {amount:,.0f}")

    elif command == "max_posisi":
        db.update_portfolio_config(max_posisi=int(value))
        print(f"✅ Max posisi diubah → {value} saham")

    elif command == "risk":
        if value not in ("conservative", "moderate", "aggressive"):
            print("❌ Pilih: conservative, moderate, atau aggressive")
            return
        db.update_portfolio_config(risk_profile=value)
        print(f"✅ Risk profile diubah → {value}")

    elif command == "max_pct":
        pct = float(value)
        if not (0 < pct <= 1):
            print("❌ Masukkan desimal 0-1 (misal 0.25 untuk 25%)")
            return
        db.update_portfolio_config(max_per_saham_pct=pct)
        print(f"✅ Max per saham diubah → {pct * 100:.0f}%")

    else:
        print(f"❌ Command '{command}' tidak dikenal.")
        print("   Gunakan: modal, max_posisi, risk, max_pct")
        return

    # Tampilkan config terbaru
    db.show_portfolio_config()


if __name__ == "__main__":
    main()
