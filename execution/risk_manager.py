import logging
from core.config import Config

logger = logging.getLogger(__name__)

class RiskManager:
    """
    Independent safeguard to protect ADA 2's balance.
    
    Operates in two layers:
        1. Tactical — stop-loss/take-profit from the active brain's profile
           (or .env defaults if the brain doesn't override).
        2. Circuit Breaker — hard max loss that overrides EVERYTHING.
    """

    def __init__(self):
        # Tactical layer: starts with .env defaults
        self.stop_loss_pct = Config.STOP_LOSS_PCT
        self.take_profit_pct = Config.TAKE_PROFIT_PCT
        self.max_hold_candles = None  # No limit by default
        
        # Circuit breaker: never changes, always enforced
        self.circuit_breaker_pct = Config.CIRCUIT_BREAKER_PCT

    def apply_profile(self, profile: dict):
        """
        Updates tactical risk params from a brain's profile.
        Only overrides keys that the brain explicitly provides.
        """
        if "stop_loss_pct" in profile:
            self.stop_loss_pct = profile["stop_loss_pct"]
            logger.info(f"Risk Profile: Stop-Loss set to {self.stop_loss_pct*100:.2f}%")
        else:
            self.stop_loss_pct = Config.STOP_LOSS_PCT

        if "take_profit_pct" in profile:
            self.take_profit_pct = profile["take_profit_pct"]
            logger.info(f"Risk Profile: Take-Profit set to {self.take_profit_pct*100:.2f}%")
        else:
            self.take_profit_pct = Config.TAKE_PROFIT_PCT

        if "max_hold_candles" in profile:
            self.max_hold_candles = profile["max_hold_candles"]
            logger.info(f"Risk Profile: Max Hold set to {self.max_hold_candles} candles")
        else:
            self.max_hold_candles = None

    def should_exit_position(self, entry_price: float, current_price: float, is_long: bool = True) -> str:
        """
        Checks if we need to force-exit.
        Returns "SELL" if we need to exit, else "HOLD".
        """
        if entry_price <= 0:
            return "HOLD"

        profit_pct = (current_price - entry_price) / entry_price
        if not is_long:
            profit_pct = -profit_pct

        # === Layer 1: Circuit Breaker (absolute, non-negotiable) ===
        if profit_pct <= -self.circuit_breaker_pct:
            logger.critical(f"CIRCUIT BREAKER! Loss: {profit_pct*100:.2f}% exceeds {self.circuit_breaker_pct*100:.1f}% limit!")
            return "SELL"

        # === Layer 2: Tactical Stop-Loss ===
        if profit_pct <= -self.stop_loss_pct:
            logger.warning(f"STOP LOSS HIT! P/L: {profit_pct*100:.3f}% (limit: -{self.stop_loss_pct*100:.2f}%)")
            return "SELL"
        
        # === Layer 2: Tactical Take-Profit ===
        if profit_pct >= self.take_profit_pct:
            logger.info(f"TAKE PROFIT HIT! P/L: {profit_pct*100:.3f}% (target: +{self.take_profit_pct*100:.2f}%)")
            return "SELL"

        return "HOLD"
