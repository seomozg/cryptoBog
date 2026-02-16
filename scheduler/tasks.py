import logging
import os
from celery import Celery
from datetime import datetime
from collectors.dex_paprika import DexPaprikaCollector
from analyzers.ai_adapter import DeepSeekAnalyzer
from analyzers.signal_generator import SignalGenerator
from trading.trade_manager import TradeManager
from database.db_manager import db_manager
from database.models import TradePosition
from config.settings import Config

logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery('crypto_alpha')
config = Config()
celery_app.conf.update(
    broker_url=os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0'),
    result_backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0'),
    timezone='UTC',
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=50,
)

@celery_app.task
def collect_data_task(network: str = "ethereum", limit: int = 100):
    """
    Periodic data collection task
    """
    try:
        logger.info(f"Starting data collection for {network}")

        # Collect market data
        collector = DexPaprikaCollector()
        market_data = collector.collect_for_analysis(network, limit)

        news_summary = "News collection disabled due to API issues"
        logger.info(f"Collected {len(market_data)} market data points")

        return {
            'market_data': market_data,
            'news_summary': news_summary
        }

    except Exception as e:
        logger.error(f"Data collection failed: {e}")
        raise

@celery_app.task
def analyze_data_task(collected_data: dict):
    """
    AI analysis task
    """
    try:
        logger.info("Starting AI analysis")

        market_data = collected_data.get('market_data', [])
        news_summary = collected_data.get('news_summary', '')

        # Exclude assets with open positions
        session = db_manager.get_session()
        open_positions = session.query(TradePosition).filter(
            TradePosition.status == 'OPEN'
        ).all()
        session.close()

        open_position_assets = set(position.symbol.replace('USDT', '') for position in open_positions)
        allowed_market_data = [
            token for token in market_data
            if token.get('symbol', '').upper() not in open_position_assets
        ]

        logger.info(
            f"AI analysis: {len(market_data)} total tokens, {len(allowed_market_data)} allowed for signals"
        )
        logger.info(f"Assets with open positions: {list(open_position_assets)}")

        if not allowed_market_data:
            logger.info("No assets available for new signals (all have open positions)")
            return {
                'market_phase': 'unknown',
                'signals': []
            }

        # Analyze with AI
        analyzer = DeepSeekAnalyzer()
        analysis_result = analyzer.analyze_market_data(allowed_market_data, news_summary)

        logger.info(f"AI analysis complete. Market phase: {analysis_result.get('market_phase', 'unknown')}")

        return analysis_result

    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        raise

@celery_app.task
def process_signals_task(analysis_result: dict):
    """
    Process and filter signals
    """
    try:
        logger.info("Processing signals")

        raw_signals = analysis_result.get('signals', [])
        market_phase = analysis_result.get('market_phase', 'unknown')

        # Filter and save signals
        signal_generator = SignalGenerator()
        filtered_signals = signal_generator.filter_signals(raw_signals)
        saved_signals = signal_generator.save_signals(filtered_signals, market_phase)

        logger.info(f"Processed {len(saved_signals)} signals")

        return len(saved_signals)

    except Exception as e:
        logger.error(f"Signal processing failed: {e}")
        raise

@celery_app.task
def execute_trades_task():
    """
    Execute automated trades for sendable signals
    """
    try:
        logger.info("Executing automated trades for signals")

        signal_generator = SignalGenerator()
        sendable_signals = signal_generator.get_sendable_signals()

        if not sendable_signals:
            logger.info("No sendable signals for automated trading")
            return 0

        trade_manager = TradeManager()
        trade_count = 0

        for signal in sendable_signals:
            logger.info(f"Attempting automated trade for {signal.asset}")
            if trade_manager.execute_signal_buy(signal):
                trade_count += 1
                logger.info(f"Successfully executed automated trade for {signal.asset}")
            else:
                logger.error(f"Failed to execute automated trade for {signal.asset}")

        logger.info(f"Executed {trade_count} automated trades")
        return trade_count

    except Exception as e:
        logger.error(f"Error executing automated trades: {e}")
        raise


@celery_app.task
def check_sells_task(collected_data: dict):
    """
    Check open positions and execute sells based on latest prices
    """
    try:
        market_data = collected_data.get('market_data', [])
        current_prices = {token.get('symbol', ''): token.get('price_usd', 0) for token in market_data}
        trade_manager = TradeManager()
        sell_count = trade_manager.check_and_execute_sells(current_prices)
        return sell_count
    except Exception as e:
        logger.error(f"Error checking sell orders: {e}")
        raise

@celery_app.task
def full_cycle_task(network: str = "ethereum", limit: int = 100):
    """
    Complete analysis cycle: collect -> analyze -> process -> send
    """
    try:
        logger.info("Starting full analysis cycle")

        # Step 1: Collect data
        collected_data = collect_data_task(network, limit)

        # Step 2: Analyze
        analysis_result = analyze_data_task(collected_data)

        # Step 3: Process signals
        signals_count = process_signals_task(analysis_result)

        # Step 4: Execute automated trades
        trades_count = execute_trades_task()

        # Step 5: Check and execute sells
        sells_count = check_sells_task(collected_data)

        logger.info("Full analysis cycle completed")

        return {
            'signals_generated': signals_count,
            'trades_executed': trades_count,
            'sells_executed': sells_count,
            'market_phase': analysis_result.get('market_phase', 'unknown')
        }

    except Exception as e:
        logger.error(f"Full cycle failed: {e}")
        raise

# Periodic tasks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    collection_interval_seconds = max(60, int(config.COLLECTION_INTERVAL_MINUTES) * 60)

    # Collect data every configured interval
    sender.add_periodic_task(collection_interval_seconds, collect_data_task.s(), name='collect-data')

    # Full cycle every configured interval
    sender.add_periodic_task(collection_interval_seconds, full_cycle_task.s(), name='full-cycle')