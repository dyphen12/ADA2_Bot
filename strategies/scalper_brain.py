"""
ScalperBrain — Momentum Micro-Scalper for ADA 2

This brain makes ADA a true scalper: fast entries, tiny targets, high frequency.
It detects micro-opportunities using short EMAs, momentum bursts, and fast RSI,
then exits quickly with tight stop-loss and take-profit.

Designed for future improvement — the entry/exit logic is cleanly separated
into named methods that can be individually upgraded, replaced, or extended.
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
from strategies.base_strategy import BaseStrategy
from typing import Dict, Any


class ScalperBrain(BaseStrategy):
    """A momentum micro-scalper that trades frequently with tiny targets."""

    def __init__(self):
        # === Tunable Parameters ===
        # These are the knobs to tweak when improving the scalper.
        
        # EMAs for trend micro-detection
        self.ema_fast = 3
        self.ema_slow = 8
        
        # RSI settings (shorter = faster signals)
        self.rsi_period = 7
        self.rsi_oversold = 25
        
        # Momentum burst detection
        self.momentum_lookback = 3    # candles to check for burst
        self.momentum_threshold = 0.0008  # 0.08% move = momentum burst
        
        # Internal state for tracking candles held
        self.candles_in_position = 0

    def get_profile(self) -> Dict[str, Any]:
        """Scalper profile — fast ticks, tight stops."""
        return {
            "tick_interval": 5,            # Check every 5 seconds
            "stop_loss_pct": 0.0015,       # 0.15% stop-loss
            "take_profit_pct": 0.0025,     # 0.25% take-profit
            "max_hold_candles": 10,        # Force exit after 10 candles (~10 min)
        }

    def get_name(self) -> str:
        return "Scalper Brain (Momentum Micro)"

    # =========================================================================
    # ENTRY SIGNALS — Each returns (triggered: bool, reason: str)
    # Upgrade these individually to improve entry quality.
    # =========================================================================

    def _check_ema_crossover(self, df: pd.DataFrame) -> tuple:
        """Detects when fast EMA crosses above slow EMA (bullish micro-trend)."""
        ema_f = df[f'EMA_{self.ema_fast}']
        ema_s = df[f'EMA_{self.ema_slow}']
        
        # Current: fast above slow. Previous: fast was below slow.
        if len(df) < 2:
            return False, ""
        
        curr_above = ema_f.iloc[-1] > ema_s.iloc[-1]
        prev_below = ema_f.iloc[-2] <= ema_s.iloc[-2]
        
        if curr_above and prev_below:
            return True, "EMA micro-cross detected (bullish)"
        return False, ""

    def _check_momentum_burst(self, df: pd.DataFrame) -> tuple:
        """Detects a sudden price burst over the last N candles."""
        if len(df) < self.momentum_lookback + 1:
            return False, ""
        
        recent_close = df['close'].iloc[-1]
        past_close = df['close'].iloc[-(self.momentum_lookback + 1)]
        move_pct = (recent_close - past_close) / past_close
        
        if move_pct > self.momentum_threshold:
            return True, f"Momentum burst: +{move_pct*100:.3f}% in {self.momentum_lookback} candles"
        return False, ""

    def _check_rsi_bounce(self, df: pd.DataFrame) -> tuple:
        """Detects RSI bouncing up from oversold territory."""
        rsi_col = f'RSI_{self.rsi_period}'
        if rsi_col not in df.columns or len(df) < 3:
            return False, ""
        
        rsi_curr = df[rsi_col].iloc[-1]
        rsi_prev = df[rsi_col].iloc[-2]
        rsi_prev2 = df[rsi_col].iloc[-3]
        
        # Was oversold and is now ticking up
        if rsi_prev2 < self.rsi_oversold and rsi_prev < self.rsi_oversold and rsi_curr > rsi_prev:
            return True, f"RSI bounce from oversold ({rsi_curr:.1f} ↑)"
        return False, ""

    # =========================================================================
    # EXIT SIGNALS — Each returns (triggered: bool, reason: str)
    # =========================================================================

    def _check_ema_reversal(self, df: pd.DataFrame) -> tuple:
        """Detects when fast EMA crosses below slow EMA while holding."""
        ema_f = df[f'EMA_{self.ema_fast}']
        ema_s = df[f'EMA_{self.ema_slow}']
        
        if ema_f.iloc[-1] < ema_s.iloc[-1]:
            return True, "EMA reversal (bearish cross) — exiting"
        return False, ""

    def _check_max_hold(self) -> tuple:
        """Force exit if held too long."""
        max_hold = self.get_profile()["max_hold_candles"]
        if self.candles_in_position >= max_hold:
            return True, f"Max hold time reached ({max_hold} candles) — force exit"
        return False, ""

    # =========================================================================
    # MAIN ANALYSIS
    # =========================================================================

    def analyze(self, df: pd.DataFrame, current_position: bool) -> Dict[str, Any]:
        if df.empty or len(df) < max(self.ema_slow, self.rsi_period) + 5:
            return {"action": "HOLD", "metrics": {"Status": "Building candle buffer..."}}

        # --- Compute Indicators ---
        df = df.copy()
        df.ta.ema(length=self.ema_fast, append=True)
        df.ta.ema(length=self.ema_slow, append=True)
        df.ta.rsi(length=self.rsi_period, append=True)

        df_clean = df.dropna()
        if len(df_clean) < self.ema_slow + 2:
            return {"action": "HOLD", "metrics": {"Status": "Warming up indicators..."}}

        # --- Gather Market Snapshot ---
        current_price = float(df_clean['close'].iloc[-1])
        ema_fast_val = float(df_clean[f'EMA_{self.ema_fast}'].iloc[-1])
        ema_slow_val = float(df_clean[f'EMA_{self.ema_slow}'].iloc[-1])
        rsi_val = float(df_clean[f'RSI_{self.rsi_period}'].iloc[-1])
        
        spread_pct = ((ema_fast_val - ema_slow_val) / ema_slow_val) * 100

        # --- Decision Logic ---
        action = "HOLD"
        thought_parts = []

        if current_position:
            # Track how long we've been in this position
            self.candles_in_position += 1
            
            # Check exit signals (priority order)
            exit_checks = [
                self._check_max_hold(),
                self._check_ema_reversal(df_clean),
            ]
            for triggered, reason in exit_checks:
                if triggered:
                    action = "SELL"
                    thought_parts.append(reason)
                    break
            
            if action == "HOLD":
                thought_parts.append(
                    f"Holding ({self.candles_in_position}/{self.get_profile()['max_hold_candles']} candles). "
                    f"Waiting for TP/SL or exit signal."
                )
        else:
            # Reset hold counter when not in position
            self.candles_in_position = 0
            
            # Check entry signals — first one to fire wins
            entry_checks = [
                self._check_ema_crossover(df_clean),
                self._check_momentum_burst(df_clean),
                self._check_rsi_bounce(df_clean),
            ]
            
            for triggered, reason in entry_checks:
                if triggered:
                    action = "BUY"
                    thought_parts.append(f"ENTRY: {reason}")
                    break
            
            if action == "HOLD":
                thought_parts.append("Scanning for micro-opportunities...")

        # --- Build Metrics ---
        trend_arrow = "↑" if ema_fast_val > ema_slow_val else "↓"
        
        metrics = {
            "EMA(3)": f"{ema_fast_val:.2f}",
            "EMA(8)": f"{ema_slow_val:.2f}",
            "EMA Spread": f"{spread_pct:+.4f}% {trend_arrow}",
            "RSI(7)": f"{rsi_val:.1f}",
            "Candles Held": str(self.candles_in_position) if current_position else "—",
            "Internal Monologue": " | ".join(thought_parts),
        }

        return {"action": action, "metrics": metrics}
