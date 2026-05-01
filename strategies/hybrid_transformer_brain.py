import os
import pandas as pd
import pandas_ta as ta
import numpy as np
import logging
from strategies.base_strategy import BaseStrategy
from typing import Dict, Any, Optional

try:
    import tensorflow as tf
    from tensorflow.keras.models import load_model
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

logger = logging.getLogger(__name__)

class HybridTransformerBrain(BaseStrategy):
    """
    A System 1 + System 2 Hybrid Brain.
    
    System 1 (Intuition/Fast): Scalper EMAs, RSI, and Momentum.
    System 2 (Reasoning/Slow): Transformer Sequence Forecaster.
    
    It only enters when both systems agree, and exits when either signals danger.
    """

    def __init__(self):
        # === Scalper Parameters (System 1) ===
        self.ema_fast = 3
        self.ema_slow = 8
        self.rsi_period = 7
        self.rsi_oversold = 25
        self.momentum_lookback = 3
        self.momentum_threshold = 0.0008
        
        # === Transformer Parameters (System 2) ===
        self.model_path = 'transformer_brain.keras'
        self.scaler_path = 'scaler_adatransformer.pkl'
        self.lookback = 60
        self.forecast = 10
        self.model = None
        self.scaler = None
        self.ml_ready = False
        
        # Internal state
        self.candles_in_position = 0
        
        if ML_AVAILABLE:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                try:
                    self.model = load_model(self.model_path, compile=False)
                    self.scaler = joblib.load(self.scaler_path)
                    self.ml_ready = True
                    logger.info("HybridBrain: Transformer model successfully integrated.")
                except Exception as e:
                    logger.error(f"HybridBrain: Error loading ML model: {e}")
            else:
                logger.warning("HybridBrain: Model files not found. Operating in Scalper-Only mode.")
        else:
            logger.warning("HybridBrain: TensorFlow not installed. Operating in Scalper-Only mode.")

    def get_profile(self) -> Dict[str, Any]:
        """Hybrid profile — fast ticks for scalping, but uses Transformer depth."""
        return {
            "tick_interval": 5,            # High frequency
            "stop_loss_pct": 0.0015,       # 0.15% tight SL
            "take_profit_pct": 0.0025,     # 0.25% target
            "max_hold_candles": 10,        # Max 10 minutes
        }

    def get_name(self) -> str:
        return "Hybrid Transformer Scalper (System 1+2)"

    # =========================================================================
    # SYSTEM 1: SCALPER SENSORS
    # =========================================================================

    def _check_scalper_entry(self, df: pd.DataFrame) -> tuple:
        """Standard scalper entry logic."""
        # 1. EMA Cross
        ema_f = df[f'EMA_{self.ema_fast}']
        ema_s = df[f'EMA_{self.ema_slow}']
        ema_cross = (ema_f.iloc[-1] > ema_s.iloc[-1]) and (ema_f.iloc[-2] <= ema_s.iloc[-2])
        
        # 2. Momentum Burst
        recent_close = df['close'].iloc[-1]
        past_close = df['close'].iloc[-(self.momentum_lookback + 1)]
        move_pct = (recent_close - past_close) / past_close
        burst = move_pct > self.momentum_threshold
        
        # 3. RSI Bounce
        rsi_col = f'RSI_{self.rsi_period}'
        rsi_curr = df[rsi_col].iloc[-1]
        rsi_prev = df[rsi_col].iloc[-2]
        rsi_prev2 = df[rsi_col].iloc[-3]
        rsi_bounce = (rsi_prev2 < self.rsi_oversold) and (rsi_prev < self.rsi_oversold) and (rsi_curr > rsi_prev)
        
        if ema_cross: return True, "EMA Cross"
        if burst: return True, f"Momentum Burst (+{move_pct*100:.3f}%)"
        if rsi_bounce: return True, "RSI Oversold Bounce"
        
        return False, ""

    # =========================================================================
    # SYSTEM 2: TRANSFORMER FORECASTER
    # =========================================================================

    def _get_transformer_forecast(self, df: pd.DataFrame) -> tuple:
        """Runs the Transformer model to get a price prediction."""
        if not self.ml_ready:
            return 0.0, [], "ML Offline"

        # Prepare features (Must match training!)
        df_feat = df.copy()
        df_feat['returns'] = df_feat['close'].pct_change()
        df_feat['volatility'] = df_feat['returns'].rolling(window=20).std()
        df_feat['sma_20'] = ta.sma(df_feat['close'], length=20)
        df_feat['sma_50'] = ta.sma(df_feat['close'], length=50)
        
        macd = ta.macd(df_feat['close'])
        df_feat['macd'] = macd['MACD_12_26_9'] if 'MACD_12_26_9' in macd else 0.0
        df_feat['macd_hist'] = macd['MACDh_12_26_9'] if 'MACDh_12_26_9' in macd else 0.0
        df_feat['rsi_14'] = ta.rsi(df_feat['close'], length=14)
        
        df_clean = df_feat.dropna()
        if len(df_clean) < self.lookback:
            return 0.0, [], "Insufficient data"

        # Extract sequence
        features = ['returns', 'volatility', 'sma_20', 'sma_50', 'macd', 'macd_hist', 'rsi_14']
        sequence_raw = df_clean[features].iloc[-self.lookback:].values
        
        # Scale and Predict
        sequence_scaled = self.scaler.transform(sequence_raw)
        X = sequence_scaled.reshape(1, self.lookback, len(features))
        
        prediction = self.model.predict(X, verbose=0)
        predicted_returns = prediction[0]
        projected_total_return = np.sum(predicted_returns)
        
        # Calculate predicted prices for UI
        current_price = float(df_clean['close'].iloc[-1])
        predicted_prices = []
        sim_price = current_price
        for r in predicted_returns:
            sim_price = sim_price * (1 + float(r))
            predicted_prices.append(sim_price)
            
        return projected_total_return, predicted_prices, "OK"

    # =========================================================================
    # HYBRID ANALYZE
    # =========================================================================

    def analyze(self, df: pd.DataFrame, current_position: bool) -> Dict[str, Any]:
        # Building buffer check
        min_len = max(self.lookback, self.ema_slow, 50) + 5
        if df.empty or len(df) < min_len:
            return {"action": "HOLD", "metrics": {"Status": "Warming up Hybrid sensors..."}}

        # Add base indicators for System 1
        df = df.copy()
        df.ta.ema(length=self.ema_fast, append=True)
        df.ta.ema(length=self.ema_slow, append=True)
        df.ta.rsi(length=self.rsi_period, append=True)
        df_clean = df.dropna()

        # 1. Run Transformer Forecast (System 2)
        forecast_pnl, pred_prices, ml_status = self._get_transformer_forecast(df_clean)
        forecast_pct = forecast_pnl * 100
        
        # 2. Decision Logic
        action = "HOLD"
        thoughts = []
        
        if current_position:
            self.candles_in_position += 1
            
            # EXIT LOGIC: Either Scalper Reversal OR Transformer predicting a crash
            ema_f = df_clean[f'EMA_{self.ema_fast}'].iloc[-1]
            ema_s = df_clean[f'EMA_{self.ema_slow}'].iloc[-1]
            
            if ema_f < ema_s:
                action = "SELL"
                thoughts.append("EXIT: EMA Reversal (System 1)")
            elif self.ml_ready and forecast_pnl < -0.0005: # -0.05% predicted drop
                action = "SELL"
                thoughts.append(f"EXIT: Negative Forecast {forecast_pct:.2f}% (System 2)")
            elif self.candles_in_position >= self.get_profile()["max_hold_candles"]:
                action = "SELL"
                thoughts.append("EXIT: Max Hold Reached")
            else:
                thoughts.append(f"Holding. Forecast: {forecast_pct:+.2f}%")
        else:
            self.candles_in_position = 0
            
            # ENTRY LOGIC: Scalper Trigger AND Transformer Forecast > +0.05%
            scalper_trigger, reason = self._check_scalper_entry(df_clean)
            
            if scalper_trigger:
                if not self.ml_ready:
                    # Fallback to pure scalper if ML is offline
                    action = "BUY"
                    thoughts.append(f"ENTRY: {reason} (ML Offline, fallback to S1)")
                elif forecast_pnl > 0.0005: # +0.05% predicted gain
                    action = "BUY"
                    thoughts.append(f"ENTRY: {reason} + Forecast {forecast_pct:+.2f}% (CONFLUENCE)")
                else:
                    thoughts.append(f"REJECTED: {reason} detected, but Forecast is too weak ({forecast_pct:+.2f}%)")
            else:
                thoughts.append(f"Scanning. Current Forecast: {forecast_pct:+.2f}%")

        # UI Metrics
        metrics = {
            "Forecast": f"{forecast_pct:+.2f}%",
            "ML Status": ml_status,
            "Internal Monologue": " | ".join(thoughts),
            "predicted_prices": pred_prices
        }
        
        return {"action": action, "metrics": metrics}
