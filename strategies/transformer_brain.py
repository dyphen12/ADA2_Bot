import os
import pandas as pd
import pandas_ta as ta
import numpy as np
from strategies.base_strategy import BaseStrategy
from typing import Dict, Any

try:
    import tensorflow as tf
    from tensorflow.keras.models import load_model
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

class TransformerBrain(BaseStrategy):
    """A Deep Learning Sequence Forecaster using a Transformer Encoder."""

    def __init__(self):
        self.model_path = 'transformer_brain.keras'
        self.scaler_path = 'scaler_adatransformer.pkl'
        self.model = None
        self.scaler = None
        self.is_ready = False
        self.lookback = 60
        self.forecast = 10
        
        if ML_AVAILABLE:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                # The model uses custom Add layers internally, but Keras should handle it.
                self.model = load_model(self.model_path, compile=False)
                self.scaler = joblib.load(self.scaler_path)
                self.is_ready = True
                print("TransformerBrain: Sequence Forecaster successfully loaded!")
            else:
                print("TransformerBrain: Model or scaler file not found. Awaiting Colab output.")
        else:
            print("TransformerBrain: TensorFlow not installed.")

    def analyze(self, df: pd.DataFrame, current_position: bool) -> Dict[str, Any]:
        if not self.is_ready:
            return {
                "action": "HOLD", 
                "metrics": {
                    "Internal Monologue": "Awaiting transformer_brain.keras upload...",
                    "Status": "Brain Offline"
                }
            }

        if df.empty or len(df) <= self.lookback:
            return {"action": "HOLD", "metrics": {"Status": f"Building {self.lookback}-candle memory..."}}

        # 1. Feature Engineering (Must perfectly match the Colab notebook!)
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std()
        df['sma_20'] = ta.sma(df['close'], length=20)
        df['sma_50'] = ta.sma(df['close'], length=50)
        
        macd = ta.macd(df['close'])
        df['macd'] = macd['MACD_12_26_9'] if 'MACD_12_26_9' in macd else 0.0
        df['macd_hist'] = macd['MACDh_12_26_9'] if 'MACDh_12_26_9' in macd else 0.0
        
        df['rsi'] = ta.rsi(df['close'], length=14)

        # Drop NaNs just to be safe, though rolling handles it mostly if we have enough data
        df_clean = df.dropna()
        if len(df_clean) < self.lookback:
             return {"action": "HOLD", "metrics": {"Status": "Not enough clean data yet..."}}

        # 2. Extract Sequence Array (Last 60 rows)
        features = ['returns', 'volatility', 'sma_20', 'sma_50', 'macd', 'macd_hist', 'rsi']
        sequence_raw = df_clean[features].iloc[-self.lookback:].values
        
        # 3. Normalize the sequence
        sequence_scaled = self.scaler.transform(sequence_raw)
        
        # Reshape to (Batch=1, TimeSteps=60, Features=7)
        X = sequence_scaled.reshape(1, self.lookback, len(features))
        
        # 4. Forecast!
        prediction = self.model.predict(X, verbose=0) # Shape: (1, 10)
        predicted_returns = prediction[0]
        
        # Calculate the cumulative projected return over the next 10 candles
        projected_total_return = np.sum(predicted_returns)
        
        # Calculate absolute predicted prices for the chart forecast line
        current_price = float(df_clean['close'].iloc[-1])
        predicted_prices = []
        sim_price = current_price
        for r in predicted_returns:
            sim_price = sim_price * (1 + float(r))
            predicted_prices.append(sim_price)
        
        # 5. Logic
        action = "HOLD"
        thought = f"10m Forecast: {projected_total_return * 100:.2f}%. "
        
        # If the model predicts a cumulative return > 0.15% over the next 10 mins
        if not current_position and projected_total_return > 0.0015:
            action = "BUY"
            thought += "Strong upward trajectory forecasted. Executing BUY."
        # If the model predicts a drop < -0.10%
        elif current_position and projected_total_return < -0.0010:
            action = "SELL"
            thought += "Downward trajectory forecasted. Bailing out of position."
        else:
            if current_position:
                thought += "Trajectory stable. Holding position."
            else:
                thought += "Trajectory sideways/bearish. Scanning..."

        metrics = {
            "RSI": f"{df_clean['rsi'].iloc[-1]:.1f}",
            "MACD": f"{df_clean['macd'].iloc[-1]:.2f}",
            "Forecast": f"{projected_total_return * 100:.2f}%",
            "Internal Monologue": thought,
            "predicted_prices": predicted_prices
        }
            
        return {"action": action, "metrics": metrics}

    def get_name(self) -> str:
        return "Transformer Sequence Forecaster"
