import logging
import os
from celery import Celery
from datetime import datetime
from collectors.dex_paprika import DexPaprikaCollector
from collectors.news_collector import NewsCollector
from analyzers.ai_adapter import DeepSeekAnalyzer
from analyzers.signal_generator import SignalGenerator
from telegram.bot import TelegramBot
from database.db_manager import db_manager

logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery('crypto_alpha')
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
def collect_data_task(network: str = "ethereum", limit: int = 30):
    """
    Periodic data collection task
    """
    try:
        logger.info(f"Starting data collection for {network}")

        # Collect market data
        collector = DexPaprikaCollector()
        market_data = collector.collect_for_analysis(network, limit)

        # Collect news
        news_collector = NewsCollector()
        news_data = news_collector.collect_news("BTC,ETH,SOL", 10)

        # Create news summary
        news_summary = " ".join([item['title'] for item in news_data[:5]])

        logger.info(f"Collected {len(market_data)} market data points and {len(news_data)} news items")

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

        # Analyze with AI
        analyzer = DeepSeekAnalyzer()
        analysis_result = analyzer.analyze_market_data(market_data, news_summary)

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
def send_signals_task():
    """
    Send unsent signals to Telegram
    """
    try:
        logger.info("Sending signals to Telegram")

        signal_generator = SignalGenerator()
        unsent_signals = signal_generator.get_unsent_signals()

        if unsent_signals:
            telegram_bot = TelegramBot()
            sent_count = telegram_bot.send_signals_batch(unsent_signals)
            logger.info(f"Sent {sent_count} signals to Telegram")
        else:
            logger.info("No unsent signals to send")

    except Exception as e:
        logger.error(f"Sending signals failed: {e}")
        raise

@celery_app.task
def full_cycle_task(network: str = "ethereum", limit: int = 30):
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

        # Step 4: Send signals
        send_signals_task()

        logger.info("Full analysis cycle completed")

        return {
            'signals_generated': signals_count,
            'market_phase': analysis_result.get('market_phase', 'unknown')
        }

    except Exception as e:
        logger.error(f"Full cycle failed: {e}")
        raise

# Periodic tasks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Collect data every 30 minutes
    sender.add_periodic_task(1800.0, collect_data_task.s(), name='collect-data')

    # Full cycle every hour
    sender.add_periodic_task(3600.0, full_cycle_task.s(), name='full-cycle')