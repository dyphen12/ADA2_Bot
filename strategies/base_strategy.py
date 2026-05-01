from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, Optional

class BaseStrategy(ABC):
    """Abstract interface for all ADA 2 trading brains."""

    @abstractmethod
    def analyze(self, df: pd.DataFrame, current_position: bool) -> Dict[str, Any]:
        """
        Analyzes the dataframe and returns a dictionary.
        Returns: {"action": "BUY"|"SELL"|"HOLD", "metrics": {...}}
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Returns the name of the strategy."""
        pass

    def get_profile(self) -> Dict[str, Any]:
        """
        Returns the brain's operational profile.
        Brains override this to declare their preferred settings.
        Any key NOT overridden falls back to .env / Config defaults.
        
        Keys:
            tick_interval:    seconds between market checks
            stop_loss_pct:    fractional (0.01 = 1%)
            take_profit_pct:  fractional (0.015 = 1.5%)
            max_hold_candles: force-exit after N candles (None = no limit)
        """
        # Default profile — matches the .env defaults.
        # Subclasses override ONLY the keys they want to change.
        return {}
