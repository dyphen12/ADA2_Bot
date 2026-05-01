from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseExchange(ABC):
    """Abstract interface for all exchange integrations."""

    @abstractmethod
    def fetch_balance(self, currency: str = "USDT") -> float:
        """Fetch free balance for a specific currency."""
        pass

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current price ticker for a symbol."""
        pass

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> List[List[Any]]:
        """Fetch historical candlestick data."""
        pass

    @abstractmethod
    def create_market_buy_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        """Execute a market buy order."""
        pass

    @abstractmethod
    def create_market_sell_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        """Execute a market sell order."""
        pass
