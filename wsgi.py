"""WSGI entry point for Railway/production deployment."""
import sys
import os
import logging
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

# Ensure data directory exists
Path("data").mkdir(exist_ok=True)

from config import load_config
from utils.logger import setup_logging
from models.database import Database
from monitor.api import APIRegistry
from monitor.monitor import BitcoinMonitor
from monitor.cycle import CycleAnalyzer
from alerts.rules_manager import RulesManager
from alerts.engine import AlertEngine
from alerts.channels import FileChannel, EmailChannel
from alerts.nadeau_signals import NadeauSignalEvaluator
from dca.portfolio import PortfolioTracker
from dca.goals import GoalTracker
from utils.action_engine import ActionEngine
from web.app import create_app

logger = logging.getLogger("btcmonitor.wsgi")

setup_logging(os.environ.get("BTC_MONITOR_LOG_LEVEL", "INFO"))
config = load_config()

db_path = os.environ.get("BTC_MONITOR_DB_PATH", config["database"]["path"])
db = Database(db_path)
db.connect()

api = APIRegistry(config)
monitor = BitcoinMonitor(db, api, config)
cycle = CycleAnalyzer(db)

rules = RulesManager("config/alerts_rules.yaml")
channels = [FileChannel()]
if config.get("email", {}).get("critical_alerts_enabled", False):
    channels.append(EmailChannel(config))
alert_engine = AlertEngine(rules, db, channels)

nadeau = NadeauSignalEvaluator(db)
dca_tracker = PortfolioTracker(db)
goal_tracker = GoalTracker(db)
action_engine = ActionEngine(cycle, monitor, goal_tracker)

engines = {
    "monitor": monitor,
    "cycle": cycle,
    "alert_engine": alert_engine,
    "nadeau": nadeau,
    "action_engine": action_engine,
    "db": db,
    "dca_portfolio": dca_tracker,
    "goal_tracker": goal_tracker,
}

app = create_app(config, engines)

# On startup, fetch initial data so the dashboard has something to show
try:
    snapshot = monitor.fetch_and_store()
    if snapshot:
        logger.info(f"Startup fetch: BTC ${snapshot.price.price_usd:,.0f}")
except Exception as e:
    logger.warning(f"Startup fetch failed (will retry on page load): {e}")
