
from prometheus_client import Gauge, Counter


# --- Intent Metrics ---
intents_submitted = Counter('intents_submitted_total', 'Total number of submitted intents', ['strategy_id'])
intents_completed = Counter('intents_completed_total', 'Total number of completed intents', ['strategy_id', 'status'])
intent_processing_time = Gauge('intent_processing_time_seconds', 'Time to process an intent', ['strategy_id'])

# --- Strategy Metrics ---
strategy_pnl = Gauge('strategy_pnl_total', 'Profit and loss for a strategy', ['strategy_id'])
strategy_active_intents = Gauge('strategy_active_intents', 'Number of active intents for a strategy', ['strategy_id'])

# --- System Metrics ---
system_errors = Counter('system_errors_total', 'Total number of system errors', ['service'])
