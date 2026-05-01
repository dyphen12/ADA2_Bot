import time
import asyncio
import logging
from core.config import Config
from exchange.base_exchange import BaseExchange
from data.fetcher import DataFetcher
from strategies.base_strategy import BaseStrategy
from execution.risk_manager import RiskManager
from execution.order_manager import OrderManager
from core.thesis import ThesisTracker
from core.run_logger import RunLogger

logger = logging.getLogger(__name__)

class ADA2Bot:
    """The main orchestrator for the ADA 2 Trading Bot."""

    def __init__(self, exchange: BaseExchange, strategy: BaseStrategy, brain_registry: dict = None):
        self.symbol = Config.TRADING_PAIR
        self.exchange = exchange
        self.strategy = strategy
        
        # Brain registry — all available brains keyed by ID
        self.brain_registry = brain_registry or {}
        
        # Inject dependencies
        self.thesis = ThesisTracker()
        self.data_fetcher = DataFetcher(exchange)
        self.order_manager = OrderManager(exchange, self.thesis)
        self.risk_manager = RiskManager()
        
        self.is_running = False
        
        # Dynamic tick interval — starts from Config, brain can override
        self.tick_interval = Config.TICK_INTERVAL
        
        # Apply the initial brain's profile (sets tick_interval, SL/TP on risk manager)
        self._apply_brain_profile()
        
        # Initialize RunLogger for this session
        self.run_logger = RunLogger(
            brain_name=self.strategy.get_name(),
            brain_profile=self._get_active_profile(),
            symbol=self.symbol,
            starting_capital=self.thesis.working_capital,
        )
        
        # Pass the run_logger to order_manager so it can log trade events
        self.order_manager.run_logger = self.run_logger
        
        # State dictionary for the UI Dashboard
        self.state = {
            "symbol": self.symbol,
            "status": "Stopped",
            "balance": 0.0,
            "current_price": 0.0,
            "position": "None",
            "entry_price": 0.0,
            "profit_loss_pct": 0.0,
            "profit_loss_usd": 0.0,
            "position_size": 0.0,
            "latest_action": "HOLD",
            "brain": self.strategy.get_name(),
            "brain_profile": self._get_active_profile(),
            "trade_stats": self._get_trade_stats(),
            "thesis": self.thesis.get_state(),
            "available_brains": list(self.brain_registry.keys()),
        }

    def _apply_brain_profile(self):
        """Apply the current brain's profile to the risk manager and tick interval."""
        profile = self.strategy.get_profile()
        
        # Apply risk params to RiskManager
        self.risk_manager.apply_profile(profile)
        
        # Apply tick interval (brain override or .env default)
        self.tick_interval = profile.get("tick_interval", Config.TICK_INTERVAL)
        
        logger.info(f"Applied profile for '{self.strategy.get_name()}': "
                     f"tick={self.tick_interval}s, "
                     f"SL={self.risk_manager.stop_loss_pct*100:.2f}%, "
                     f"TP={self.risk_manager.take_profit_pct*100:.2f}%")

    def _get_active_profile(self) -> dict:
        """Returns the currently active risk/timing profile for UI display."""
        return {
            "tick_interval": self.tick_interval,
            "stop_loss_pct": self.risk_manager.stop_loss_pct,
            "take_profit_pct": self.risk_manager.take_profit_pct,
            "max_hold_candles": self.risk_manager.max_hold_candles,
            "circuit_breaker_pct": self.risk_manager.circuit_breaker_pct,
        }

    def switch_brain(self, brain_id: str) -> bool:
        """
        Hot-swaps ADA's brain to a different strategy.
        Preserves position state — if ADA is in a trade, the new brain takes over.
        """
        if brain_id not in self.brain_registry:
            logger.error(f"Brain '{brain_id}' not found in registry.")
            return False
        
        old_name = self.strategy.get_name()
        self.strategy = self.brain_registry[brain_id]
        self._apply_brain_profile()
        
        # Log the brain switch in the run log
        self.run_logger.log_brain_switch(
            old_brain=old_name,
            new_brain=self.strategy.get_name(),
            new_profile=self._get_active_profile(),
        )
        # Update run_logger reference on order_manager
        self.order_manager.run_logger = self.run_logger
        
        self.state["brain"] = self.strategy.get_name()
        self.state["brain_profile"] = self._get_active_profile()
        self.state["trade_stats"] = self._get_trade_stats()
        
        logger.info(f"Brain switched: '{old_name}' -> '{self.strategy.get_name()}'")
        return True

    def _get_trade_stats(self) -> dict:
        """Derives trade stats from RunLogger — single source of truth."""
        summary = self.run_logger.get_summary()
        return {
            "total_trades": summary["total_trades"],
            "wins": summary["wins"],
            "losses": summary["losses"],
            "win_rate": summary["win_rate"],
            "avg_hold_seconds": summary["avg_hold_seconds"],
        }

    def check_system(self) -> bool:
        """Verifies connection and balances before starting."""
        logger.info(f"Checking system status for {self.symbol}...")
        
        balance = self.exchange.fetch_balance("USDT")
        self.state["balance"] = balance
        logger.info(f"Current USDT Balance: {balance}")
        
        if balance < Config.TRADE_ALLOCATION:
            logger.error(f"Insufficient testnet balance. Need {Config.TRADE_ALLOCATION}, got {balance}")
            return False
            
        if self.thesis.working_capital < Config.TRADE_ALLOCATION:
            logger.error(f"Insufficient Working Capital. Need {Config.TRADE_ALLOCATION}, got {self.thesis.working_capital}")
            return False
            
        ticker = self.exchange.fetch_ticker(self.symbol)
        if not ticker:
            logger.error("Could not fetch ticker. Check connection.")
            return False
            
        logger.info(f"System Check OK. Current Price: {ticker.get('last')}")
        return True

    def tick(self):
        """A single execution cycle."""
        try:
            # 1. Fetch current state
            ticker = self.exchange.fetch_ticker(self.symbol)
            if not ticker:
                return
                
            current_price = ticker.get('last')
            self.state["current_price"] = current_price
            
            try:
                self.state["balance"] = self.exchange.fetch_balance("USDT")
            except Exception as e:
                logger.error(f"Failed to fetch real balance: {e}")
            
            # Update state for UI
            if self.order_manager.active_position:
                self.state["position"] = "LONG"
                self.state["entry_price"] = self.order_manager.entry_price
                pl_pct = (current_price - self.order_manager.entry_price) / self.order_manager.entry_price
                self.state["profit_loss_pct"] = pl_pct * 100
                self.state["profit_loss_usd"] = Config.TRADE_ALLOCATION * pl_pct
                self.state["position_size"] = Config.TRADE_ALLOCATION
            else:
                self.state["position"] = "None"
                self.state["entry_price"] = 0.0
                self.state["profit_loss_pct"] = 0.0
                self.state["profit_loss_usd"] = 0.0
                self.state["position_size"] = 0.0

            # 2. Risk Management (Highest Priority — independent of brain)
            if self.order_manager.active_position:
                risk_action = self.risk_manager.should_exit_position(
                    self.order_manager.entry_price, 
                    current_price
                )
                if risk_action == "SELL":
                    pl_pct = (current_price - self.order_manager.entry_price) / self.order_manager.entry_price
                    
                    # Reset brain's internal candle counter
                    if hasattr(self.strategy, 'candles_in_position'):
                        self.strategy.candles_in_position = 0
                    
                    self.state["latest_action"] = "RISK_SELL"
                    # Determine if this is a stop-loss, take-profit, or circuit breaker
                    if pl_pct <= -self.risk_manager.circuit_breaker_pct:
                        trigger = "circuit_breaker"
                    elif pl_pct <= -self.risk_manager.stop_loss_pct:
                        trigger = "stop_loss"
                    else:
                        trigger = "take_profit"
                    self.order_manager.execute_sell(self.symbol, current_price, trigger_signal=trigger)
                    self.state["trade_stats"] = self._get_trade_stats()
                    return

            # 3. Strategy Brain
            df = self.data_fetcher.get_dataframe(self.symbol, timeframe='1m', limit=150)
            analysis = self.strategy.analyze(df, self.order_manager.active_position)
            action = analysis["action"]
            self.state["latest_action"] = action
            self.state["metrics"] = analysis["metrics"]
            
            # Log every tick to the run log
            self.run_logger.log_tick(
                action=action,
                price=current_price,
                metrics=analysis["metrics"],
                position=self.state["position"],
                entry_price=self.state["entry_price"],
                pl_pct=self.state["profit_loss_pct"],
                working_capital=self.thesis.working_capital,
            )
            
            # 4. Execution
            if action == "BUY" and not self.order_manager.active_position:
                if self.thesis.working_capital >= Config.TRADE_ALLOCATION:
                    self.order_manager.execute_buy(
                        self.symbol, current_price, analysis["metrics"],
                        trigger_signal="brain"
                    )
                else:
                    logger.critical(f"THESIS FAILED: Working Capital (${self.thesis.working_capital:.2f}) dropped below trade minimum!")
                    self.state["status"] = "Experiment Failed"
                    self.is_running = False
            elif action == "SELL" and self.order_manager.active_position:
                # Reset brain's internal candle counter
                if hasattr(self.strategy, 'candles_in_position'):
                    self.strategy.candles_in_position = 0
                
                self.order_manager.execute_sell(
                    self.symbol, current_price, analysis["metrics"],
                    trigger_signal="brain"
                )
                
            # Update Thesis State and Trade Stats (derived from RunLogger)
            thesis_state = self.thesis.get_state()
            if self.order_manager.active_position:
                thesis_state["working_capital"] -= Config.TRADE_ALLOCATION
            self.state["thesis"] = thesis_state
            self.state["trade_stats"] = self._get_trade_stats()
            self.state["current_run_id"] = self.run_logger.run_id
                
        except Exception as e:
            logger.error(f"Error during tick: {e}")
            self.run_logger.log_error(str(e))

    async def run(self, interval_seconds: int = None):
        """Starts the infinite trading loop asynchronously."""
        Config.validate()
        
        # Use brain profile tick interval, or passed argument, or config default
        if interval_seconds is None:
            interval_seconds = self.tick_interval
        
        logger.info(f"Starting ADA 2 Bot with Brain: {self.strategy.get_name()}")
        if not self.check_system():
            logger.critical("System check failed. Shutting down.")
            self.state["status"] = "Error: System Check Failed"
            return

        self.is_running = True
        self.state["status"] = "Running"
        logger.info(f"Bot loop started. Ticking every {interval_seconds} seconds.")
        
        while self.is_running:
            self.tick()
            # Re-read tick interval in case brain was switched mid-loop
            await asyncio.sleep(self.tick_interval)
