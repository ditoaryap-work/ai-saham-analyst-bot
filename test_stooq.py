import pandas_datareader.data as web
import traceback

def test_stooq(ticker):
    print(f"Testing Stooq for {ticker}...")
    try:
        df = web.DataReader(ticker, 'stooq')
        print("✅ SUCCESS")
        print(df.head())
    except Exception as e:
        print("❌ FAILED")
        print(e)
        traceback.print_exc()

if __name__ == "__main__":
    test_stooq('BBCA.UK')
    test_stooq('BBCA.ID')
    test_stooq('BBCA.JK')
