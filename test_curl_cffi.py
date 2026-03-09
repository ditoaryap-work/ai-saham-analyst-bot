from curl_cffi import requests
import json

def test_idx_curl_cffi():
    print("--- TESTING IDX API MENGGUNAKAN CURL_CFFI ---")
    
    # 1. Test GetStockList
    print("\n1. Test GetStockList:")
    url_list = "https://idx.co.id/umbraco/Surface/ListedCompany/GetStockList"
    
    try:
        # Menggunakan impersonate="chrome120" untuk memalsukan fingerprint browser
        response = requests.get(url_list, impersonate="chrome120", timeout=10)
        
        print(f"HTTP Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                print("✅ BERHASIL BYPASS CLOUDFLARE!")
                print(f"Total Saham Ditemukan: {len(data['data'])}")
                print(f"Sample data: {data['data'][0]['Code']} - {data['data'][0]['Name']}")
            else:
                print("⚠️ Request berhasil (200 OK) tapi format data tidak dikenali atau kosong.")
                print("Snippet respons:", response.text[:200])
        else:
            print("❌ GAGAL BYPASS CLOUDFLARE.")
            print("Snippet respons:", response.text[:200])
            
    except Exception as e:
        print(f"❌ ERROR SAAT TESTING: {e}")
        
    # 2. Test Trading Info
    print("\n2. Test TradingInfoSS (BBCA):")
    url_info = "https://idx.co.id/umbraco/Surface/ListedCompany/GetTradingInfoSS?code=BBCA&length=5"
    
    try:
        response = requests.get(url_info, impersonate="chrome120", timeout=10)
        print(f"HTTP Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if 'replies' in data and len(data['replies']) > 0:
                print("✅ BERHASIL BYPASS CLOUDFLARE TradingInfo!")
                print(f"Data ditemukan! Hari terakhir: {data['replies'][0]['Date']}")
            else:
                print("⚠️ Request 200 OK tapi format tidak sesuai.")
        else:
            print("❌ GAGAL BYPASS CLOUDFLARE TradingInfo.")
            
    except Exception as e:
        print(f"❌ ERROR SAAT TESTING: {e}")

if __name__ == "__main__":
    test_idx_curl_cffi()
