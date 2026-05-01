import ccxt
import logging
from typing import Dict, Any, List
from exchange.base_exchange import BaseExchange
from core.config import Config

logger = logging.getLogger(__name__)

class BinanceClient(BaseExchange):
    """Concrete implementation for Binance Testnet."""

    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': Config.BINANCE_TESTNET_API_KEY,
            'secret': Config.BINANCE_TESTNET_SECRET_KEY,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 10000, # Increase window to 10 seconds
            }
        })
        self.exchange.set_sandbox_mode(True) # VERY IMPORTANT: Forces testnet
        logger.info("Initialized Binance Testnet Client")

    def fetch_balance(self, currency: str = "USDT") -> float:
        try:
            balance = self.exchange.fetch_balance()
            return balance[currency]['free'] if currency in balance else 0.0
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return {}

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> List[List[Any]]:
        try:
            return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            return []

    def create_market_buy_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        try:
            order = self.exchange.create_market_buy_order(symbol, amount)
            logger.info(f"Successfully placed BUY order: {order}")
            return order
        except Exception as e:
            logger.error(f"Failed to place BUY order: {e}")
            return {}

    def create_market_sell_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        try:
            order = self.exchange.create_market_sell_order(symbol, amount)
            logger.info(f"Successfully placed SELL order: {order}")
            return order
        except Exception as e:
            logger.error(f"Failed to place SELL order: {e}")
            return {}
