import os
import json
import logging
import time
from exchange.base_exchange import BaseExchange
from core.config import Config
from core.thesis import ThesisTracker

logger = logging.getLogger(__name__)

class OrderManager:
    """Handles the actual routing and tracking of orders."""

    def __init__(self, exchange: BaseExchange, thesis_tracker: ThesisTracker):
        self.exchange = exchange
        self.thesis_tracker = thesis_tracker
        self.active_position = False
        self.entry_price = 0.0
        self.position_amount = 0.0
        self.history_file = 'data/trade_history.json'
        self.trade_history = []
        self.run_logger = None  # Injected by ADA2Bot after construction
        self.load_history()

    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self.trade_history = data.get('history', [])
                    # Restore active position state if the last trade was a BUY
                    if self.trade_history and self.trade_history[-1]['side'] == 'BUY':
                        self.active_position = True
                        self.entry_price = self.trade_history[-1]['price']
                        self.position_amount = self.trade_history[-1].get('amount', 0.0)
                        logger.warning(f"Restored an active BUY position from history. Entry: {self.entry_price}, Amount: {self.position_amount}")
                logger.info(f"Loaded {len(self.trade_history)} historical trades.")
            except Exception as e:
                logger.error(f"Failed to load trade history: {e}")

    def save_history(self):
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        try:
            with open(self.history_file, 'w') as f:
                json.dump({'history': self.trade_history}, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save trade history: {e}")

    def reset(self):
        """Hard resets the trade history and local variables."""
        self.active_position = False
        self.entry_price = 0.0
        self.position_amount = 0.0
        self.trade_history = []
        
        if os.path.exists(self.history_file):
            try:
                os.remove(self.history_file)
                logger.info(f"Deleted history file {self.history_file}")
            except Exception as e:
                logger.error(f"Failed to delete history file: {e}")
                
        logger.info("OrderManager memory hard reset!")

    def save_snapshot(self, side: str, price: float, metrics: dict):
        if not metrics:
            return
        os.makedirs('data/snapshots', exist_ok=True)
        timestamp = int(time.time())
        filename = f"data/snapshots/snapshot_{timestamp}_{side}.json"
        data = {
            "time": timestamp,
            "side": side,
            "price": price,
            "metrics": metrics
        }
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")

    def execute_buy(self, symbol: str, price: float, metrics: dict = None, trigger_signal: str = "brain"):
        """Executes a buy and tracks the state."""
        logger.info(f"Attempting to BUY {symbol}...")
        
        allocation = Config.TRADE_ALLOCATION
        amount = allocation / price

        order = self.exchange.create_market_buy_order(symbol, amount)
        if order:
            self.active_position = True
            self.entry_price = order.get('average', price) 
            if self.entry_price is None or self.entry_price == 0:
                 self.entry_price = price
                 
            filled_amount = order.get('filled', amount)
            self.position_amount = filled_amount * 0.999 
            
            # Record Trade (for chart markers)
            self.trade_history.append({
                "time": int(time.time()),
                "price": self.entry_price,
                "side": "BUY",
                "amount": self.position_amount
            })
            
            logger.info(f"BUY executed at {self.entry_price}. Stored Amount: {self.position_amount}")
            self.save_history()
            self.save_snapshot("BUY", self.entry_price, metrics)
            
            # Log to run logger
            if self.run_logger:
                self.run_logger.log_buy(
                    price=self.entry_price,
                    amount=self.position_amount,
                    metrics=metrics or {},
                    trigger_signal=trigger_signal,
                )
            return True
        return False

    def execute_sell(self, symbol: str, price: float, metrics: dict = None, trigger_signal: str = "brain"):
        """Executes a sell and resets the state."""
        logger.info(f"Attempting to SELL {symbol}...")
        
        order = self.exchange.create_market_sell_order(symbol, self.position_amount)
        if order:
            exit_price = order.get('average', price)
            if exit_price is None or exit_price == 0:
                 exit_price = price
            
            # Calculate Gross Return (in USDT)
            gross_return = exit_price * self.position_amount
            # Simulate 0.1% Sell Fee (deducted from quote asset)
            net_return = gross_return * 0.999
            
            # Initial cost
            initial_cost = self.entry_price * (self.position_amount / 0.999)
            
            # Net Profit/Loss
            net_profit = net_return - initial_cost
            
            logger.info(f"SELL executed at {exit_price}. Net Profit: {net_profit:.4f} USDT")
            
            # Report to Thesis Tracker
            self.thesis_tracker.process_trade_result(net_profit)
            
            # Record Trade (for chart markers)
            self.trade_history.append({
                "time": int(time.time()),
                "price": exit_price,
                "side": "SELL"
            })
            
            # Log to run logger
            if self.run_logger:
                self.run_logger.log_sell(
                    price=exit_price,
                    net_profit=net_profit,
                    metrics=metrics or {},
                    trigger_signal=trigger_signal,
                )
            
            self.active_position = False
            self.entry_price = 0.0
            self.position_amount = 0.0
            self.save_history()
            self.save_snapshot("SELL", exit_price, metrics)
            return True
        return False
