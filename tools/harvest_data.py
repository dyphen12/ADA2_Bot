import os
import sys
import time
import pandas as pd
from datetime import datetime, timedelta

# Ensure parent directory is in sys.path to import ADA modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange.binance_client import BinanceClient

def harvest_data(symbol="BTC/USDT", timeframe="1m", total_candles=100000):
    print(f"Starting Data Harvest for {symbol} ({timeframe})...")
    print(f"Target: {total_candles} candles (approx {total_candles / 1440:.1f} days).")
    
    # Use the existing Binance Client
    client = BinanceClient()
    
    # Calculate starting timestamp (100k minutes ago)
    # 1 minute = 60,000 ms
    current_time_ms = int(time.time() * 1000)
    start_time_ms = current_time_ms - (total_candles * 60 * 1000)
    
    print(f"Fetching from: {datetime.fromtimestamp(start_time_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_candles = []
    current_since = start_time_ms
    
    # Binance limit per request is 1000
    batch_size = 1000
    
    while len(all_candles) < total_candles:
        try:
            # fetch_ohlcv returns [timestamp, open, high, low, close, volume]
            batch = client.exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=batch_size)
            
            if not batch:
                print("No more data found. Reached current time?")
                break
                
            all_candles.extend(batch)
            
            # Update 'since' to the last candle's timestamp + 1 minute (60,000 ms)
            current_since = batch[-1][0] + 60000
            
            progress = min(100.0, (len(all_candles) / total_candles) * 100)
            print(f"Progress: {progress:.1f}% ({len(all_candles)} / {total_candles} candles downloaded)", end="\r")
            
            # Respect rate limits
            time.sleep(0.1)
            
        except Exception as e:
            print(f"\nError fetching data: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)
            
    print("\n\nHarvest complete! Formatting data...")
    
    # Truncate if we fetched slightly more
    all_candles = all_candles[:total_candles]
    
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    file_path = f"data/{symbol.replace('/', '_')}_{timeframe}_dataset.csv"
    df.to_csv(file_path)
    
    print(f"Saved dataset successfully to {file_path}")
    print(f"Head:\n{df.head(3)}")
    print(f"Tail:\n{df.tail(3)}")

if __name__ == "__main__":
    harvest_data()
