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

class TFBrain(BaseStrategy):
    """A Deep Learning brain using TensorFlow."""

    def __init__(self):
        self.model_path = 'ada_brain.keras'
        self.scaler_path = 'scaler.pkl'
        self.model = None
        self.scaler = None
        self.is_ready = False
        
        if ML_AVAILABLE:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = load_model(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                self.is_ready = True
                print("TFBrain: Neural Network successfully loaded!")
            else:
                print("TFBrain: Model or scaler file not found. Awaiting upload.")
        else:
            print("TFBrain: TensorFlow not installed. Please pip install tensorflow scikit-learn joblib.")

    def analyze(self, df: pd.DataFrame, current_position: bool) -> Dict[str, Any]:
        if not self.is_ready:
            return {
                "action": "HOLD", 
                "metrics": {
                    "Internal Monologue": "I cannot find my brain files! Please put ada_brain.keras and scaler.pkl in my folder.",
                    "Status": "Brain Offline"
                }
            }

        if df.empty or len(df) < 50:
            return {"action": "HOLD", "metrics": {"Status": "Warming up indicators..."}}

        # 1. Feature Engineering (Must perfectly match the Colab notebook!)
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std()
        df['sma_20'] = ta.sma(df['close'], length=20)
        df['sma_50'] = ta.sma(df['close'], length=50)
        
        macd = ta.macd(df['close'])
        df['macd'] = macd['MACD_12_26_9'] if 'MACD_12_26_9' in macd else 0.0
        df['macd_hist'] = macd['MACDh_12_26_9'] if 'MACDh_12_26_9' in macd else 0.0
        
        df['rsi'] = ta.rsi(df['close'], length=14)

        # Get the latest row
        latest_row = df.iloc[-1]
        
        if pd.isna(latest_row['sma_50']) or pd.isna(latest_row['volatility']):
             return {"action": "HOLD", "metrics": {"Status": "Calculating features..."}}

        # 2. Extract Features Array
        features = ['returns', 'volatility', 'sma_20', 'sma_50', 'macd', 'macd_hist', 'rsi']
        X_raw = latest_row[features].values.reshape(1, -1)
        
        # 3. Normalize
        X_scaled = self.scaler.transform(X_raw)
        
        # 4. Predict!
        prediction = self.model.predict(X_scaled, verbose=0)
        confidence = float(prediction[0][0])
        
        # 5. Logic
        action = "HOLD"
        thought = f"AI Confidence Score: {confidence * 100:.1f}%. "
        
        # If confidence is > 70%, it means the AI strongly believes price will go UP
        if not current_position and confidence > 0.70:
            action = "BUY"
            thought += "Signal > 70%. High probability setup detected. Executing BUY."
        # Sell logic (since it's a predictive model, we rely on TP/SL in OrderManager, or we can force sell if confidence drops < 30%)
        elif current_position and confidence < 0.30:
            action = "SELL"
            thought += "Signal < 30%. Momentum failing. Bailing out of position."
        else:
            if current_position:
                thought += "Holding position. Awaiting take-profit or AI panic signal."
            else:
                thought += "Scanning market. Confidence not high enough."

        metrics = {
            "RSI": f"{latest_row['rsi']:.1f}",
            "MACD": f"{latest_row['macd']:.2f}",
            "SMA(50)": f"{latest_row['sma_50']:.2f}",
            "AI_Conf": f"{confidence * 100:.1f}%",
            "Internal Monologue": thought
        }
            
        return {"action": action, "metrics": metrics}

    def get_name(self) -> str:
        return "TensorFlow Deep Learning AI"
