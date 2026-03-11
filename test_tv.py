from tvDatafeed import TvDatafeed, Interval
import traceback

print("Testing TradingView Datafeed...")
try:
    tv = TvDatafeed()
    df = tv.get_hist(symbol='BBCA', exchange='IDX', interval=Interval.in_daily, n_bars=10)
    print("\nBBCA OHLCV:")
    print(df)
    
    macro = tv.get_hist(symbol='COMPOSITE', exchange='IDX', interval=Interval.in_daily, n_bars=3)
    print("\nIHSG OHLCV:")
    print(macro)
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
