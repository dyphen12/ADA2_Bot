import os
import json
import logging
from core.config import Config

logger = logging.getLogger(__name__)

class ThesisTracker:
    """
    The Thesis Engine tracks the experiment parameters (N dollars for N earnings).
    It maintains the 'Working Capital' (N) and siphons profits into a 'Claimable Vault'.
    """
    def __init__(self):
        self.state_file = 'data/thesis_state.json'
        
        # Starting Capital (N dollars)
        self.initial_balance = Config.INITIAL_BALANCE
        self.working_capital = self.initial_balance
        
        # The Vault (for theoretically claimable earnings)
        self.claimable_vault = 0.0
        
        # Experiment Targets
        self.daily_target = Config.DAILY_TARGET
        
        # Statistics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        self.load_state()

    def load_state(self):
        """Loads state from JSON if it exists."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.working_capital = data.get('working_capital', self.initial_balance)
                    self.claimable_vault = data.get('claimable_vault', 0.0)
                    self.total_trades = data.get('total_trades', 0)
                    self.winning_trades = data.get('winning_trades', 0)
                    self.losing_trades = data.get('losing_trades', 0)
                logger.info(f"THESIS: State restored from {self.state_file}")
            except Exception as e:
                logger.error(f"THESIS: Failed to load state: {e}")

    def save_state(self):
        """Saves current state to JSON."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        try:
            state_data = {
                'working_capital': self.working_capital,
                'claimable_vault': self.claimable_vault,
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades
            }
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=4)
        except Exception as e:
            logger.error(f"THESIS: Failed to save state: {e}")

    def reset(self):
        """Hard resets the experiment memory."""
        self.working_capital = self.initial_balance
        self.claimable_vault = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        if os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
                logger.info(f"THESIS: Deleted state file {self.state_file}")
            except Exception as e:
                logger.error(f"THESIS: Failed to delete state file: {e}")
        
        logger.info("THESIS: Experiment memory hard reset!")

    def process_trade_result(self, profit_loss: float):
        """Processes the outcome of a closed trade."""
        self.total_trades += 1
        
        if profit_loss > 0:
            self.winning_trades += 1
            # Profit goes straight to the claimable vault! Working capital is untouched.
            self.claimable_vault += profit_loss
            logger.info(f"THESIS: Trade Won! +${profit_loss:.4f} deposited to Claimable Vault.")
        else:
            self.losing_trades += 1
            # Loss eats into our working capital
            self.working_capital += profit_loss # profit_loss is negative
            logger.warning(f"THESIS: Trade Lost! ${profit_loss:.4f} deducted from Working Capital.")
            
        self.save_state()

    def get_win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    def get_target_progress_pct(self) -> float:
        if self.daily_target == 0:
            return 0.0
        return (self.claimable_vault / self.daily_target) * 100

    def get_state(self) -> dict:
        """Returns the current state for the UI."""
        return {
            "initial_capital": self.initial_balance,
            "working_capital": self.working_capital,
            "claimable_vault": self.claimable_vault,
            "daily_target": self.daily_target,
            "target_progress_pct": self.get_target_progress_pct(),
            "total_trades": self.total_trades,
            "win_rate": self.get_win_rate()
        }
