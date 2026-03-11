import os
os.chdir('/Users/ditoaryap/Documents/Project/ai-saham')

from data.database import db
from data.fetcher.fundamental_fetcher import fetch_and_save_fundamentals
from analysis.fundamental import calculate_f_score, calculate_z_score

fetch_and_save_fundamentals(["BBCA"])

print("Rows in fundamental:", db.execute("SELECT COUNT(*) as c FROM fundamental")[0]['c'])
last_row = db.execute("SELECT * FROM fundamental WHERE kode='BBCA' ORDER BY periode DESC LIMIT 1")
if last_row:
    d = dict(last_row[0])
    print("Latest Fundamental Data:")
    for k, v in d.items():
        if v is not None:
            print(f"  {k}: {v}")
else:
    print("NO DATA in fundamental table for BBCA!")

f = calculate_f_score("BBCA")
z = calculate_z_score("BBCA")
print(f"F-Score: {f}, Z-Score: {z}")
if not ind:
    print("Indicators returned empty/None!")
else:
    print(f"Candle data size: close={ind.get('close')}")
    
# 3. Test Scoring
score = calculate_composite_score("BBCA", indicators=ind)
pprint(score)
