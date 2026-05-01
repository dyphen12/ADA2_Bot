import pandas as pd
from typing import List, Any
from exchange.base_exchange import BaseExchange

class DataFetcher:
    """Handles data retrieval and formatting."""

    def __init__(self, exchange: BaseExchange):
        self.exchange = exchange

    def get_dataframe(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> pd.DataFrame:
        """Fetches OHLCV data and converts it to a Pandas DataFrame."""
        raw_data = self.exchange.fetch_ohlcv(symbol, timeframe, limit)
        if not raw_data:
            return pd.DataFrame()

        df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
