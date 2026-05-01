import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Central configuration manager for ADA 2."""
    
    # API Keys
    BINANCE_TESTNET_API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
    BINANCE_TESTNET_SECRET_KEY = os.getenv("BINANCE_TESTNET_SECRET_KEY")
    
    # Bot Settings
    TRADING_PAIR = os.getenv("TRADING_PAIR", "BTC/USDT")
    INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "10.0"))
    DAILY_TARGET = float(os.getenv("DAILY_TARGET", "1.0"))
    TRADE_ALLOCATION = float(os.getenv("TRADE_ALLOCATION", "10.0"))
    
    # Strategy Settings
    RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
    RSI_OVERBOUGHT = int(os.getenv("RSI_OVERBOUGHT", "70"))
    RSI_OVERSOLD = int(os.getenv("RSI_OVERSOLD", "30"))
    
    # Risk Limits (defaults — brains can override via profiles)
    STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.01"))
    TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.015"))
    CIRCUIT_BREAKER_PCT = float(os.getenv("CIRCUIT_BREAKER_PCT", "0.05"))  # Hard 5% max loss, overrides everything
    
    # Bot Timing
    TICK_INTERVAL = int(os.getenv("TICK_INTERVAL", "30"))  # Default tick speed in seconds
    DEFAULT_BRAIN = os.getenv("DEFAULT_BRAIN", "scalper")  # Which brain to load on startup
    
    @classmethod
    def validate(cls):
        """Ensure critical config variables are set."""
        if not cls.BINANCE_TESTNET_API_KEY or not cls.BINANCE_TESTNET_SECRET_KEY:
            raise ValueError("Binance Testnet API keys are missing in the .env file!")
