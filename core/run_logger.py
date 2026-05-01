"""
RunLogger — Structured trade session logging for ADA 2.

Captures every decision and trade in detail for analysis and debugging.
Each run (boot session) gets a unique ID and its own log file.

Log structure:
    data/runs/<run_id>.json
        {
            "run_id": "...",
            "brain": "Scalper Brain (Momentum Micro)",
            "brain_profile": {...},
            "start_time": "2026-05-01T05:00:00Z",
            "symbol": "BTC/USDT",
            "starting_capital": 100.0,
            "events": [...],   # every tick's decision
            "trades": [...],   # completed BUY->SELL pairs
            "summary": {...}   # filled on shutdown / reset
        }

Event types in 'events':
    TICK    — every market check (HOLD, BUY, SELL)
    BUY     — buy order executed
    SELL    — sell order executed (by brain or risk manager)
    ERROR   — any error during tick
    SWITCH  — brain switched mid-run
"""

import json
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

RUNS_DIR = "data/runs"
ACTIVE_RUN_FILE = "data/active_run_id.txt"


class RunLogger:
    """Logs every tick and trade for a single ADA run session.
    
    Persists across server restarts (like ThesisTracker).
    A new run is only created on first boot or when reset() is called.
    """

    def __init__(self, brain_name: str, brain_profile: dict, symbol: str, starting_capital: float):
        os.makedirs(RUNS_DIR, exist_ok=True)

        # Try to resume an existing active run
        restored = self._try_restore()

        if restored:
            # Update brain info in case brain was changed in .env between restarts
            self.brain_name = brain_name
            self.brain_profile = brain_profile
            self._save()
            logger.info(f"RunLogger: Resumed active session -> {self.run_id} "
                        f"({len(self.trades)} trades, {len(self.events)} events)")
        else:
            # No active run found — create a fresh one
            self._create_new_run(brain_name, brain_profile, symbol, starting_capital)

    def _create_new_run(self, brain_name: str, brain_profile: dict, symbol: str, starting_capital: float):
        """Creates a brand new run session."""
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        self.brain_name = brain_name
        self.brain_profile = brain_profile
        self.symbol = symbol
        self.starting_capital = starting_capital
        self.start_time = datetime.now(timezone.utc).isoformat()

        self.events: List[dict] = []
        self.trades: List[dict] = []
        self._open_trade: Optional[dict] = None

        # Save the run and mark it as active
        self._save()
        self._save_active_pointer()
        logger.info(f"RunLogger: New session started -> {self.run_id}")

    def _try_restore(self) -> bool:
        """Attempts to restore the active run from disk. Returns True if successful."""
        if not os.path.exists(ACTIVE_RUN_FILE):
            return False

        try:
            with open(ACTIVE_RUN_FILE, 'r') as f:
                run_id = f.read().strip()

            if not run_id:
                return False

            run_path = os.path.join(RUNS_DIR, f"{run_id}.json")
            if not os.path.exists(run_path):
                logger.warning(f"RunLogger: Active pointer references {run_id} but file not found. Starting fresh.")
                return False

            with open(run_path, 'r') as f:
                data = json.load(f)

            self.run_id = data["run_id"]
            self.brain_name = data.get("brain", "Unknown")
            self.brain_profile = data.get("brain_profile", {})
            self.symbol = data.get("symbol", "BTC/USDT")
            self.starting_capital = data.get("starting_capital", 0.0)
            self.start_time = data.get("start_time", _now())
            self.events = data.get("events", [])
            self.trades = data.get("trades", [])

            # Restore open trade state if the last event was a BUY without a matching SELL
            self._open_trade = None
            if self.events:
                # Walk backwards to find if there's an unmatched BUY
                last_buy = None
                last_sell = None
                for event in reversed(self.events):
                    if event["type"] == "SELL" and last_sell is None:
                        last_sell = event
                        break
                    if event["type"] == "BUY" and last_buy is None:
                        last_buy = event
                        break
                
                if last_buy and (last_sell is None or 
                    self.events.index(last_buy) > ([i for i, e in enumerate(self.events) if e["type"] == "SELL"][-1] if last_sell else -1)):
                    # There's an unmatched BUY — reconstruct open trade
                    self._open_trade = {
                        "trade_id": len(self.trades) + 1,
                        "brain": self.brain_name,
                        "symbol": self.symbol,
                        "entry_ts": last_buy.get("ts", _now()),
                        "entry_price": last_buy.get("price", 0),
                        "amount": last_buy.get("amount", 0),
                        "entry_signal": last_buy.get("trigger", "brain"),
                        "entry_metrics": last_buy.get("metrics", {}),
                        "exit_ts": None, "exit_price": None, "exit_signal": None,
                        "exit_metrics": None, "hold_seconds": None,
                        "gross_return": None, "net_profit": None, "outcome": None,
                    }

            return True
        except Exception as e:
            logger.error(f"RunLogger: Failed to restore active run: {e}")
            return False

    def _save_active_pointer(self):
        """Saves the current run_id as the active run."""
        try:
            os.makedirs(os.path.dirname(ACTIVE_RUN_FILE), exist_ok=True)
            with open(ACTIVE_RUN_FILE, 'w') as f:
                f.write(self.run_id)
        except Exception as e:
            logger.error(f"RunLogger: Failed to save active pointer: {e}")

    def reset(self, brain_name: str, brain_profile: dict, symbol: str, starting_capital: float):
        """Resets the run logger — closes the current run and starts a fresh one."""
        logger.info(f"RunLogger: Closing run {self.run_id} ({len(self.trades)} trades)")
        self._save()  # Final save of old run
        self._create_new_run(brain_name, brain_profile, symbol, starting_capital)

    # =========================================================================
    # CORE LOGGING METHODS
    # =========================================================================

    def log_tick(self, action: str, price: float, metrics: dict,
                 position: str, entry_price: float, pl_pct: float,
                 working_capital: float):
        """Logs every market tick. Called every cycle."""
        event = {
            "type": "TICK",
            "ts": _now(),
            "action": action,
            "price": round(price, 2),
            "position": position,
            "entry_price": round(entry_price, 2) if entry_price else None,
            "pl_pct": round(pl_pct, 4) if pl_pct else None,
            "working_capital": round(working_capital, 4),
            "metrics": _clean_metrics(metrics),
        }
        self.events.append(event)
        self._save()

    def log_buy(self, price: float, amount: float, metrics: dict,
                trigger_signal: str = "brain"):
        """Logs a BUY execution. Opens a trade record."""
        event = {
            "type": "BUY",
            "ts": _now(),
            "price": round(price, 2),
            "amount": amount,
            "trigger": trigger_signal,
            "metrics": _clean_metrics(metrics),
        }
        self.events.append(event)

        # Open a trade pair record
        self._open_trade = {
            "trade_id": len(self.trades) + 1,
            "brain": self.brain_name,
            "symbol": self.symbol,
            "entry_ts": _now(),
            "entry_price": round(price, 2),
            "amount": amount,
            "entry_signal": trigger_signal,
            "entry_metrics": _clean_metrics(metrics),
            "exit_ts": None,
            "exit_price": None,
            "exit_signal": None,
            "exit_metrics": None,
            "hold_seconds": None,
            "gross_return": None,
            "net_profit": None,
            "outcome": None,   # "WIN" or "LOSS"
        }

        self._save()
        logger.info(f"RunLogger: Trade #{self._open_trade['trade_id']} opened at ${price:.2f}")

    def log_sell(self, price: float, net_profit: float, metrics: dict,
                 trigger_signal: str = "brain"):
        """Logs a SELL execution. Closes the current trade record."""
        event = {
            "type": "SELL",
            "ts": _now(),
            "price": round(price, 2),
            "net_profit": round(net_profit, 4),
            "trigger": trigger_signal,
            "metrics": _clean_metrics(metrics),
        }
        self.events.append(event)

        if self._open_trade:
            entry_ts_str = self._open_trade["entry_ts"]
            exit_ts_str = _now()

            # Calculate hold duration
            try:
                entry_dt = datetime.fromisoformat(entry_ts_str)
                exit_dt = datetime.fromisoformat(exit_ts_str)
                hold_seconds = int((exit_dt - entry_dt).total_seconds())
            except Exception:
                hold_seconds = None

            gross_return = (price - self._open_trade["entry_price"]) * self._open_trade["amount"]

            self._open_trade.update({
                "exit_ts": exit_ts_str,
                "exit_price": round(price, 2),
                "exit_signal": trigger_signal,
                "exit_metrics": _clean_metrics(metrics),
                "hold_seconds": hold_seconds,
                "gross_return": round(gross_return, 4),
                "net_profit": round(net_profit, 4),
                "outcome": "WIN" if net_profit > 0 else "LOSS",
            })
            self.trades.append(self._open_trade)
            logger.info(
                f"RunLogger: Trade #{self._open_trade['trade_id']} closed. "
                f"Outcome: {self._open_trade['outcome']}, P/L: ${net_profit:.4f}, "
                f"held {hold_seconds}s via '{trigger_signal}'"
            )
            self._open_trade = None

        self._save()

    def log_error(self, message: str):
        """Logs an error event."""
        event = {
            "type": "ERROR",
            "ts": _now(),
            "message": message,
        }
        self.events.append(event)
        self._save()

    def log_brain_switch(self, old_brain: str, new_brain: str, new_profile: dict):
        """Logs when the brain is switched mid-run."""
        event = {
            "type": "SWITCH",
            "ts": _now(),
            "from_brain": old_brain,
            "to_brain": new_brain,
            "new_profile": new_profile,
        }
        self.events.append(event)
        self.brain_name = new_brain
        self.brain_profile = new_profile
        self._save()

    # =========================================================================
    # SUMMARY + PERSISTENCE
    # =========================================================================

    def get_summary(self) -> dict:
        """Returns a summary of this run's performance."""
        total = len(self.trades)
        wins = sum(1 for t in self.trades if t["outcome"] == "WIN")
        losses = total - wins
        total_pnl = sum(t["net_profit"] for t in self.trades if t["net_profit"] is not None)
        avg_hold = (
            sum(t["hold_seconds"] for t in self.trades if t["hold_seconds"])
            / max(total, 1)
        )

        return {
            "run_id": self.run_id,
            "brain": self.brain_name,
            "start_time": self.start_time,
            "end_time": _now(),
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / total * 100) if total > 0 else 0.0,
            "total_net_pnl": round(total_pnl, 4),
            "avg_hold_seconds": round(avg_hold, 1),
            "total_events": len(self.events),
        }

    def get_recent_trades(self, limit: int = 50) -> List[dict]:
        """Returns the most recent completed trades."""
        return self.trades[-limit:]

    def get_recent_events(self, limit: int = 100, event_type: str = None) -> List[dict]:
        """Returns recent events, optionally filtered by type."""
        events = self.events
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        return events[-limit:]

    def _save(self):
        """Persists the full run log to disk."""
        path = os.path.join(RUNS_DIR, f"{self.run_id}.json")
        data = {
            "run_id": self.run_id,
            "brain": self.brain_name,
            "brain_profile": self.brain_profile,
            "start_time": self.start_time,
            "symbol": self.symbol,
            "starting_capital": self.starting_capital,
            "events": self.events,
            "trades": self.trades,
            "summary": self.get_summary(),
        }
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"RunLogger: Failed to save run log: {e}")


# =========================================================================
# HELPER: List all past runs
# =========================================================================

def list_runs() -> List[dict]:
    """Returns metadata for all past run sessions, newest first."""
    if not os.path.exists(RUNS_DIR):
        return []

    runs = []
    for filename in sorted(os.listdir(RUNS_DIR), reverse=True):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(RUNS_DIR, filename)
        try:
            with open(path, "r") as f:
                data = json.load(f)
                runs.append(data.get("summary", {}))
        except Exception:
            pass
    return runs


def load_run(run_id: str) -> Optional[dict]:
    """Loads the full data for a specific run."""
    path = os.path.join(RUNS_DIR, f"{run_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


# =========================================================================
# UTILITIES
# =========================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_metrics(metrics: dict) -> dict:
    """Strips non-serializable values (like predicted_prices lists that are large)."""
    if not metrics:
        return {}
    cleaned = {}
    for k, v in metrics.items():
        if k == "predicted_prices":
            continue  # skip large arrays; kept in state but not needed in log
        try:
            json.dumps(v)  # test serializability
            cleaned[k] = v
        except (TypeError, ValueError):
            cleaned[k] = str(v)
    return cleaned
