import sys
import traceback

print("=== MENGUJI KONEKSI BUKAN YAHOO FINANCE ===")

def test_tradingview():
    print("\n[1] Testing TradingView (tvDatafeed)...")
    try:
        from tvDatafeed import TvDatafeed, Interval
        tv = TvDatafeed()
        df = tv.get_hist(symbol='BBCA', exchange='IDX', interval=Interval.in_daily, n_bars=2)
        print("✅ TradingView Berhasil:")
        print(df.head())
        return True
    except Exception as e:
        print("❌ TradingView Gagal:")
        print(e)
        return False

def test_idx_api():
    print("\n[2] Testing API Resmi Bursa Efek (IDX)...")
    try:
        from curl_cffi import requests
        url = "https://idx.co.id/umbraco/Surface/ListedCompany/GetTradingInfoSS?code=BBCA&length=1"
        r = requests.get(url, impersonate="chrome120", timeout=10)
        if r.status_code == 200:
            print("✅ API IDX Berhasil (Raw Data):")
            print(str(r.json())[:100] + "...")
            return True
        else:
            print(f"❌ API IDX Gagal: Status {r.status_code}")
            return False
    except Exception as e:
        print("❌ API IDX Gagal:")
        print(e)
        return False

if __name__ == "__main__":
    tv_ok = test_tradingview()
    idx_ok = test_idx_api()
    print("\n==================================")
    if tv_ok or idx_ok:
         print("KESIMPULAN: Kita bisa ganti data provider!")
    else:
         print("KESIMPULAN: Semua diblokir oleh VPS!")
