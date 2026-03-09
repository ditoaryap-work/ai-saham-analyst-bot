import yfinance as yf
import pandas as pd
import json

def test_yfinance_idx():
    print("--- TESTING YFINANCE UNTUK SAHAM IDX ---")
    ticker_symbol = "BIPI.JK"
    print(f"Mengambil data untuk: {ticker_symbol}")
    
    try:
        bbca = yf.Ticker(ticker_symbol)
        
        # 1. Test Historical Data (OHLCV)
        print("\n1. Test Harga Historis (5 hari terakhir):")
        hist = bbca.history(period="5d")
        if not hist.empty:
            print("✅ BERHASIL MENDAPATKAN HARGA!")
            print(hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(2))
        else:
            print("❌ GAGAL: Data harga kosong.")
            
        # 2. Test Fundamental Data (Info)
        print("\n2. Test Data Fundamental Dasar:")
        info = bbca.info
        
        # Cek beberapa key fundamental yang penting
        keys_to_check = [
            'marketCap', 'trailingPE', 'priceToBook', 'returnOnEquity',
            'returnOnAssets', 'totalRevenue', 'netIncomeToCommon',
            'debtToEquity', 'currentRatio'
        ]
        
        found_data = {}
        missing_data = []
        
        for key in keys_to_check:
            if key in info and info[key] is not None:
                found_data[key] = info[key]
            else:
                missing_data.append(key)
                
        print(f"Data Fundamental Ditemukan ({len(found_data)}/{len(keys_to_check)}):")
        for k, v in found_data.items():
            print(f"  - {k}: {v}")
            
        if missing_data:
            print("❌ Data Fundamental yang KOSONG/TIDAK ADA di yfinance:")
            for k in missing_data:
                print(f"  - {k}")
                
        # 3. Test IHSG (^JKSE)
        print("\n3. Test Indeks IHSG (^JKSE):")
        ihsg = yf.Ticker("^JKSE")
        ihsg_hist = ihsg.history(period="1d")
        if not ihsg_hist.empty:
            print("✅ BERHASIL MENDAPATKAN IHSG!")
            print(f"  Close Terakhir: {ihsg_hist['Close'].iloc[-1]:.2f}")
        else:
            print("❌ GAGAL: Data IHSG kosong.")
            
    except Exception as e:
        print(f"❌ ERROR SAAT TESTING: {e}")

if __name__ == "__main__":
    test_yfinance_idx()
