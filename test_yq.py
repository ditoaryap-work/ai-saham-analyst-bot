from yahooquery import Ticker
t = Ticker('BBCA.JK')

print("\n--- FINANCIAL DATA ---")
try: print(t.financial_data['BBCA.JK'].keys())
except: pass

print("\n--- SUMMARY DETAIL ---")
try: print(t.summary_detail['BBCA.JK'].keys())
except: pass

