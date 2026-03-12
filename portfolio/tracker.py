"""
portfolio/tracker.py — Portfolio tracking system.

Fungsi:
- buy_position(): Catat pembelian
- sell_position(): Catat penjualan + hitung P&L
- get_portfolio_summary(): Ringkasan portfolio + unrealized P&L
- check_alerts(): Cek stoploss/target/konsentrasi
- get_track_record(): Hit rate & statistik 30 hari
"""

import sys
from pathlib import Path
from datetime import date, datetime

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import db
from config.settings import MAX_POSISI, MAX_PER_SAHAM_PCT
from config.settings import MODAL_AWAL as ENV_MODAL_AWAL


def get_modal_awal() -> float:
    """Ambil modal_awal dari database, fallback ke .env"""
    row = db.execute("SELECT modal_awal FROM portfolio_config WHERE user_id = 'default'")
    if row and row[0]['modal_awal']:
        return float(row[0]['modal_awal'])
    return ENV_MODAL_AWAL


def set_modal_awal(amount: float) -> bool:
    """Update modal_awal dan asimulasikan cash berdasarkan selisih deposit/withdraw."""
    old_modal = get_modal_awal()
    diff = amount - old_modal
    
    # Update config
    db.execute(
        "INSERT INTO portfolio_config (user_id, modal_awal, max_posisi, max_per_saham_pct) "
        "VALUES ('default', ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET modal_awal = excluded.modal_awal",
        (amount, MAX_POSISI, MAX_PER_SAHAM_PCT)
    )
    
    # Adjust last cash snapshot
    row = db.execute("SELECT cash FROM dana_snapshot ORDER BY tanggal DESC LIMIT 1")
    if row:
        current_cash = float(row[0]['cash'])
        new_cash = max(0, current_cash + diff)
        db.execute(
            "UPDATE dana_snapshot SET cash = ? WHERE tanggal = (SELECT tanggal FROM dana_snapshot ORDER BY tanggal DESC LIMIT 1)",
            (new_cash,)
        )
    
    _update_snapshot()
    return True


def _get_cash() -> float:
    """Ambil saldo cash terbaru."""
    row = db.execute("SELECT cash FROM dana_snapshot ORDER BY tanggal DESC LIMIT 1")
    if row:
        return dict(row[0])['cash']
    return get_modal_awal()


def _update_snapshot():
    """Update dana_snapshot dengan posisi terkini."""
    cash = _get_cash()

    # Total invested
    positions = db.execute("SELECT SUM(lot * harga_beli * 100) as invested FROM posisi_aktif")
    invested = dict(positions[0])['invested'] if positions and dict(positions[0])['invested'] else 0

    total = cash + invested
    modal = get_modal_awal()
    return_pct = (total - modal) / modal if modal > 0 else 0

    db.execute(
        """INSERT OR REPLACE INTO dana_snapshot (tanggal, total_portfolio, cash, invested, return_pct)
           VALUES (?, ?, ?, ?, ?)""",
        (date.today().isoformat(), total, cash, invested, return_pct),
    )
    return {'total': total, 'cash': cash, 'invested': invested, 'return_pct': return_pct}


def buy_position(kode: str, lot: int, harga: float, stoploss: float = None,
                 target: float = None, label: str = None) -> dict:
    """
    Catat posisi beli baru.
    Validasi: cek dana cukup, max posisi, max per saham.
    """
    cost = lot * harga * 100  # 1 lot = 100 lembar
    cash = _get_cash()

    # Validasi dana
    if cost > cash:
        return {'success': False, 'error': f'Dana tidak cukup. Butuh Rp {cost:,.0f}, sisa Rp {cash:,.0f}'}

    # Validasi max posisi
    count = db.execute("SELECT COUNT(*) as n FROM posisi_aktif")
    n_posisi = dict(count[0])['n'] if count else 0
    if n_posisi >= MAX_POSISI:
        return {'success': False, 'error': f'Max posisi ({MAX_POSISI}) sudah tercapai'}

    # Validasi max per saham
    modal = get_modal_awal()
    max_alloc = modal * MAX_PER_SAHAM_PCT
    if cost > max_alloc:
        return {'success': False, 'error': f'Melebihi max alokasi per saham (Rp {max_alloc:,.0f})'}

    # Simpan posisi
    db.execute(
        """INSERT INTO posisi_aktif (kode, lot, harga_beli, harga_terkini,
           unrealized_pnl, tanggal_beli, stoploss_set, target_set, label_sinyal)
           VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)""",
        (kode, lot, harga, harga, date.today().isoformat(), stoploss, target, label),
    )

    # Update cash
    new_cash = cash - cost
    db.execute(
        "INSERT OR REPLACE INTO dana_snapshot (tanggal, total_portfolio, cash, invested, return_pct) "
        "VALUES (?, ?, ?, ?, ?)",
        (date.today().isoformat(), modal, new_cash, cost, 0),
    )

    _update_snapshot()

    logger.info(f"BUY {kode} {lot} lot @ Rp {harga:,.0f} | Cost: Rp {cost:,.0f} | Sisa: Rp {new_cash:,.0f}")

    return {
        'success': True,
        'kode': kode,
        'lot': lot,
        'harga': harga,
        'cost': cost,
        'sisa_cash': new_cash,
        'stoploss': stoploss,
        'target': target,
    }


def sell_position(kode: str, lot: int, harga_jual: float) -> dict:
    """
    Jual posisi, hitung P&L, pindah ke historis_trade.
    """
    positions = db.execute(
        "SELECT * FROM posisi_aktif WHERE kode = ? ORDER BY tanggal_beli ASC",
        (kode,),
    )

    if not positions:
        return {'success': False, 'error': f'Tidak ada posisi {kode} yang aktif'}

    pos = dict(positions[0])

    if lot > pos['lot']:
        return {'success': False, 'error': f'Lot yang dijual ({lot}) > lot yang dimiliki ({pos["lot"]})'}

    # Hitung P&L
    harga_beli = pos['harga_beli']
    pnl = (harga_jual - harga_beli) * lot * 100
    pnl_pct = (harga_jual - harga_beli) / harga_beli if harga_beli > 0 else 0

    # Tentukan hit (profit / loss)
    hit = 1 if pnl > 0 else 0

    # Simpan ke historis
    db.execute(
        """INSERT INTO historis_trade (kode, lot, harga_beli, harga_jual,
           tanggal_beli, tanggal_jual, pnl, pnl_pct, label_sinyal, hit)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (kode, lot, harga_beli, harga_jual, pos['tanggal_beli'],
         date.today().isoformat(), pnl, pnl_pct, pos.get('label_sinyal'), hit),
    )

    # Update atau hapus posisi
    remaining = pos['lot'] - lot
    if remaining <= 0:
        db.execute("DELETE FROM posisi_aktif WHERE id = ?", (pos['id'],))
    else:
        db.execute("UPDATE posisi_aktif SET lot = ? WHERE id = ?", (remaining, pos['id']))

    # Update cash
    cash = _get_cash()
    proceeds = lot * harga_jual * 100
    new_cash = cash + proceeds
    _update_snapshot()

    emoji = "🟢" if pnl > 0 else "🔴"
    logger.info(f"SELL {kode} {lot} lot @ Rp {harga_jual:,.0f} | {emoji} P&L: Rp {pnl:,.0f} ({pnl_pct:+.1%})")

    return {
        'success': True,
        'kode': kode,
        'lot': lot,
        'harga_beli': harga_beli,
        'harga_jual': harga_jual,
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'hit': hit,
        'sisa_cash': new_cash,
    }


def get_portfolio_summary() -> dict:
    """
    Ringkasan portfolio: semua posisi aktif + unrealized P&L.
    """
    positions = db.execute("SELECT * FROM posisi_aktif")
    snapshot = _update_snapshot()

    items = []
    total_unrealized = 0

    for row in (positions or []):
        p = dict(row)

        # Fetch harga terkini dari DB
        latest = db.execute(
            "SELECT close FROM harga_historis WHERE kode = ? ORDER BY tanggal DESC LIMIT 1",
            (p['kode'],),
        )
        harga_now = dict(latest[0])['close'] if latest else p['harga_beli']

        # Update harga terkini
        unrealized = (harga_now - p['harga_beli']) * p['lot'] * 100
        unrealized_pct = (harga_now - p['harga_beli']) / p['harga_beli'] if p['harga_beli'] > 0 else 0

        db.execute(
            "UPDATE posisi_aktif SET harga_terkini = ?, unrealized_pnl = ? WHERE id = ?",
            (harga_now, unrealized, p['id']),
        )

        total_unrealized += unrealized

        items.append({
            'kode': p['kode'],
            'lot': p['lot'],
            'harga_beli': p['harga_beli'],
            'harga_now': harga_now,
            'unrealized': unrealized,
            'unrealized_pct': unrealized_pct,
            'stoploss': p.get('stoploss_set'),
            'target': p.get('target_set'),
            'tanggal_beli': p['tanggal_beli'],
        })

    return {
        **snapshot,
        'positions': items,
        'total_unrealized': total_unrealized,
        'n_positions': len(items),
    }


def check_alerts() -> list:
    """
    Cek alerts: stoploss, target, konsentrasi sektor, cash idle.
    """
    alerts = []
    summary = get_portfolio_summary()

    for pos in summary['positions']:
        # Cek stoploss
        if pos['stoploss'] and pos['harga_now'] <= pos['stoploss']:
            alerts.append({
                'type': 'STOPLOSS',
                'kode': pos['kode'],
                'message': f"⚠️ {pos['kode']} kena STOPLOSS! Harga Rp {pos['harga_now']:,.0f} ≤ SL Rp {pos['stoploss']:,.0f}. SEGERA JUAL!",
            })

        # Cek target
        if pos['target'] and pos['harga_now'] >= pos['target']:
            alerts.append({
                'type': 'TARGET',
                'kode': pos['kode'],
                'message': f"🎯 {pos['kode']} HIT TARGET! Harga Rp {pos['harga_now']:,.0f} ≥ Target Rp {pos['target']:,.0f}. Pertimbangkan jual.",
            })

        # Unrealized loss > 5%
        if pos['unrealized_pct'] < -0.05:
            alerts.append({
                'type': 'LOSS_WARNING',
                'kode': pos['kode'],
                'message': f"🔴 {pos['kode']} floating loss {pos['unrealized_pct']:+.1%}. Review posisi.",
            })

    # Cash idle check
    modal = get_modal_awal()
    if summary['cash'] > modal * 0.4 and summary['n_positions'] > 0:
        alerts.append({
            'type': 'CASH_IDLE',
            'message': f"💰 Cash idle tinggi: Rp {summary['cash']:,.0f} ({summary['cash']/modal:.0%} dari modal). Pertimbangkan deploy.",
            'kode': '-'
        })
    return alerts


def get_track_record(days: int = 30) -> dict:
    """
    Track record N hari: hit rate, avg win, avg loss, best, worst.
    """
    rows = db.execute(
        """SELECT * FROM historis_trade
           WHERE tanggal_jual >= date('now', ?)
           ORDER BY tanggal_jual DESC""",
        (f"-{days} days",),
    )

    if not rows:
        return {
            'total_trades': 0, 'hit_rate': 0, 'avg_return': 0,
            'avg_win': 0, 'avg_loss': 0, 'best': None, 'worst': None,
            'total_pnl': 0,
        }

    trades = [dict(r) for r in rows]
    wins = [t for t in trades if t['hit'] == 1]
    losses = [t for t in trades if t['hit'] == 0]

    total_pnl = sum(t['pnl'] for t in trades)
    avg_return = sum(t['pnl_pct'] for t in trades) / len(trades) if trades else 0

    best = max(trades, key=lambda t: t['pnl_pct']) if trades else None
    worst = min(trades, key=lambda t: t['pnl_pct']) if trades else None

    return {
        'total_trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'hit_rate': len(wins) / len(trades) if trades else 0,
        'avg_return': avg_return,
        'avg_win': sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0,
        'avg_loss': sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0,
        'best': best,
        'worst': worst,
        'total_pnl': total_pnl,
    }


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    print("\n💼 Portfolio Tracker — Test\n")

    # Test buy
    r = buy_position("BBCA", 10, 9200, stoploss=8950, target=9500, label="AMAN")
    print(f"BUY: {r}")

    r = buy_position("BMRI", 20, 5800, stoploss=5600, target=6100, label="MOMENTUM")
    print(f"BUY: {r}")

    # Summary
    s = get_portfolio_summary()
    print(f"\n📊 Portfolio: {s['n_positions']} posisi")
    print(f"   Cash: Rp {s['cash']:,.0f}")
    print(f"   Invested: Rp {s['invested']:,.0f}")
    for p in s['positions']:
        emoji = "🟢" if p['unrealized'] >= 0 else "🔴"
        print(f"   {emoji} {p['kode']}: {p['lot']} lot @ {p['harga_beli']:,.0f} → {p['harga_now']:,.0f} ({p['unrealized_pct']:+.1%})")

    # Alerts
    alerts = check_alerts()
    if alerts:
        print(f"\n🔔 Alerts:")
        for a in alerts:
            print(f"   {a['message']}")

    # Test sell
    r = sell_position("BBCA", 10, 9400)
    print(f"\nSELL: {r}")

    # Track record
    tr = get_track_record()
    print(f"\n📈 Track Record: {tr['total_trades']} trades, hit rate {tr['hit_rate']:.0%}")

    print("\n🎉 Portfolio tracker test selesai!")
