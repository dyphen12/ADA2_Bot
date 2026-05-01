import pandas as pd
import pandas_ta as ta
from strategies.base_strategy import BaseStrategy
from core.config import Config

from typing import Dict, Any

class RSIScalper(BaseStrategy):
    """A simple Mean Reversion brain using RSI."""

    def __init__(self):
        self.period = Config.RSI_PERIOD
        self.overbought = Config.RSI_OVERBOUGHT
        self.oversold = Config.RSI_OVERSOLD

    def analyze(self, df: pd.DataFrame, current_position: bool) -> Dict[str, Any]:
        if df.empty or len(df) < self.period:
            return {"action": "HOLD", "metrics": {"RSI": "--"}}

        # Calculate RSI, MACD, and SMA
        df.ta.rsi(length=self.period, append=True)
        df.ta.macd(append=True)
        df.ta.sma(length=50, append=True)
        
        # Get the latest values
        latest_rsi = df[f'RSI_{self.period}'].iloc[-1]
        
        # MACD columns are usually MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
        latest_macd = df['MACD_12_26_9'].iloc[-1] if 'MACD_12_26_9' in df.columns else 0.0
        latest_sma = df['SMA_50'].iloc[-1] if 'SMA_50' in df.columns else 0.0
        current_price = df['close'].iloc[-1]

        if pd.isna(latest_rsi):
            return {"action": "HOLD", "metrics": {"Status": "Warming up indicators..."}}

        # Formulate ADA's thought process
        trend = "Bullish" if current_price > latest_sma else "Bearish"
        momentum = "Positive" if latest_macd > 0 else "Negative"
        
        thought = f"Market is {trend} and momentum is {momentum}. RSI is currently {latest_rsi:.1f}. "

        # Strategy Logic
        action = "HOLD"
        if not current_position and latest_rsi < self.oversold:
            action = "BUY"
            thought += f"RSI dropped below {self.oversold}. Oversold condition detected. Initiating BUY sequence."
        elif current_position and latest_rsi > self.overbought:
            action = "SELL"
            thought += f"RSI rose above {self.overbought}. Overbought condition detected. Securing profits with SELL order."
        else:
            if current_position:
                thought += "Holding active position. Waiting for take-profit or overbought signal."
            else:
                thought += "Awaiting optimal entry conditions."
            
        metrics = {
            "RSI": f"{latest_rsi:.2f}",
            "MACD": f"{latest_macd:.2f}",
            "SMA(50)": f"{latest_sma:.2f}",
            "Internal Monologue": thought
        }
            
        return {"action": action, "metrics": metrics}

    def get_name(self) -> str:
        return "RSI Scalper (Baseline)"
