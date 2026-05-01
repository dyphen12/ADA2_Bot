import logging
import sys
import os
import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from core.bot import ADA2Bot
from core.config import Config
from core.run_logger import list_runs, load_run
from exchange.binance_client import BinanceClient

# Import all available brains
from strategies.scalper_brain import ScalperBrain
from strategies.rsi_scalper import RSIScalper
from strategies.transformer_brain import TransformerBrain
from strategies.tf_brain import TFBrain

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ada2_bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# ===== Brain Registry =====
# All available brains, keyed by ID.
# To add a new brain: instantiate it here and give it a key.
BRAIN_REGISTRY = {
    "scalper": ScalperBrain(),
    "rsi": RSIScalper(),
    "transformer": TransformerBrain(),
    "tf": TFBrain(),
}

# Determine which brain to start with
default_brain_id = Config.DEFAULT_BRAIN
if default_brain_id not in BRAIN_REGISTRY:
    logging.warning(f"DEFAULT_BRAIN '{default_brain_id}' not found. Falling back to 'scalper'.")
    default_brain_id = "scalper"

# Initialize FastAPI App
app = FastAPI(title="ADA 2 Dashboard")

# Enable CORS for the UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate Bot Components
exchange_client = BinanceClient()
bot = ADA2Bot(
    exchange=exchange_client,
    strategy=BRAIN_REGISTRY[default_brain_id],
    brain_registry=BRAIN_REGISTRY,
)

# Startup Event to launch the bot
@app.on_event("startup")
async def startup_event():
    logging.info("Starting ADA 2 background task...")
    asyncio.create_task(bot.run())

# ===== API Endpoints =====

@app.get("/api/state")
async def get_state():
    """Returns the live state of ADA 2 for the UI."""
    return bot.state

@app.get("/api/chart_data")
async def get_chart_data():
    """Returns the last 100 OHLCV candles formatted for TradingView Lightweight Charts."""
    df = bot.data_fetcher.get_dataframe(bot.symbol, limit=100)
    if df.empty:
        return []
    
    df_reset = df.reset_index()
    chart_data = []
    for _, row in df_reset.iterrows():
        chart_data.append({
            "time": int(row['timestamp'].timestamp()),
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close'])
        })
    return chart_data

@app.get("/api/trade_history")
async def get_trade_history():
    """Returns the history of executed trades to draw markers."""
    return bot.order_manager.trade_history

@app.get("/api/run_log")
async def get_run_log():
    """Returns the current run's trades and recent tick events for the UI."""
    return {
        "run_id": bot.run_logger.run_id,
        "brain": bot.run_logger.brain_name,
        "start_time": bot.run_logger.start_time,
        "trades": bot.run_logger.get_recent_trades(limit=50),
        "recent_events": bot.run_logger.get_recent_events(limit=30),
        "summary": bot.run_logger.get_summary(),
    }

@app.get("/api/runs")
async def get_all_runs():
    """Returns metadata for all past run sessions, newest first."""
    return list_runs()

@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    """Returns the full data for a specific past run."""
    data = load_run(run_id)
    if not data:
        return {"error": f"Run '{run_id}' not found."}
    return data

@app.get("/api/brains")
async def get_brains():
    """Returns all available brains and their profiles."""
    brains = {}
    for brain_id, brain in BRAIN_REGISTRY.items():
        profile = brain.get_profile()
        brains[brain_id] = {
            "name": brain.get_name(),
            "profile": {
                "tick_interval": profile.get("tick_interval", Config.TICK_INTERVAL),
                "stop_loss_pct": profile.get("stop_loss_pct", Config.STOP_LOSS_PCT),
                "take_profit_pct": profile.get("take_profit_pct", Config.TAKE_PROFIT_PCT),
                "max_hold_candles": profile.get("max_hold_candles", None),
            },
            "active": brain_id == _get_active_brain_id(),
        }
    return brains

def _get_active_brain_id() -> str:
    """Helper to find the current active brain ID."""
    for brain_id, brain in BRAIN_REGISTRY.items():
        if brain is bot.strategy:
            return brain_id
    return "unknown"

class SwitchBrainRequest(BaseModel):
    brain_id: str

@app.post("/api/switch_brain")
async def switch_brain(request: SwitchBrainRequest):
    """Hot-swaps ADA's brain to a different strategy."""
    success = bot.switch_brain(request.brain_id)
    if success:
        return {
            "status": "success",
            "message": f"Switched to {bot.strategy.get_name()}",
            "brain": bot.strategy.get_name(),
            "profile": bot._get_active_profile(),
        }
    return {"status": "error", "message": f"Brain '{request.brain_id}' not found."}

@app.post("/api/reset")
async def reset_experiment():
    """Hard resets the experiment. Flattens open positions and wipes local DB."""
    if bot.order_manager.active_position:
        current_price = bot.state.get("current_price")
        if current_price and current_price > 0:
            logging.info("Reset triggered: Flattening active position via Market Sell.")
            bot.order_manager.execute_sell(bot.symbol, current_price)
            
    bot.thesis.reset()
    bot.order_manager.reset()
    
    # Clear snapshots for a truly clean slate
    if os.path.exists('data/snapshots'):
        for f in os.listdir('data/snapshots'):
            try:
                os.remove(os.path.join('data/snapshots', f))
            except: pass

    # Reset the run logger — starts a fresh experiment run
    bot.run_logger.reset(
        brain_name=bot.strategy.get_name(),
        brain_profile=bot._get_active_profile(),
        symbol=bot.symbol,
        starting_capital=bot.thesis.working_capital,
    )
    bot.order_manager.run_logger = bot.run_logger
    
    # Reset UI State variables
    bot.state["position"] = "None"
    bot.state["entry_price"] = 0.0
    bot.state["profit_loss_pct"] = 0.0
    bot.state["profit_loss_usd"] = 0.0
    bot.state["position_size"] = 0.0
    bot.state["latest_action"] = "RESET"
    bot.state["trade_stats"] = bot._get_trade_stats()
    bot.state["thesis"] = bot.thesis.get_state()
    
    return {"status": "success", "message": "Experiment reset successfully."}

# Serve the static UI files at the root
app.mount("/", StaticFiles(directory="web", html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    print("Welcome to ADA 2!")
    print(f"Active Brain: {BRAIN_REGISTRY[default_brain_id].get_name()}")
    print(f"Available Brains: {', '.join(BRAIN_REGISTRY.keys())}")
    print("Launching FastAPI Server and Trading Bot...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
