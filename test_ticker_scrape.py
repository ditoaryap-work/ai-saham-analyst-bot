from curl_cffi import requests
import json

def test_idx_tickers():
    url = "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles?emitenType=s&start=0&length=100"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.idx.co.id/id/perusahaan-tercatat/profil-perusahaan-tercatat/",
    }
    
    try:
        r = requests.get(url, headers=headers, impersonate="chrome110")
        print(f"Status Code: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"Total Companies: {data.get('recordsTotal')}")
            for item in data.get('data', [])[:5]:
                print(f"- {item.get('Symbol')}: {item.get('CompanyName')}")
        else:
            print(r.text[:500])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_idx_tickers()
