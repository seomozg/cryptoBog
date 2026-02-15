import click
import logging
from collectors.dex_paprika import DexPaprikaCollector
from collectors.news_collector import NewsCollector
from analyzers.ai_adapter import DeepSeekAnalyzer
from analyzers.signal_generator import SignalGenerator
from telegram.bot import TelegramBot
from database.db_manager import db_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.group()
def cli():
    """Crypto Alpha AI Advisor CLI"""
    pass

@cli.command()
@click.option('--network', default='ethereum', help='Network to collect data from')
@click.option('--limit', default=30, help='Number of tokens to collect')
def collect(network, limit):
    """Collect market data from APIs"""
    click.echo(f"📊 Collecting data from {network} (limit: {limit})")

    try:
        collector = DexPaprikaCollector()
        data = collector.collect_for_analysis(network, limit)
        click.echo(f"✅ Collected {len(data)} tokens")
    except Exception as e:
        click.echo(f"❌ Collection failed: {e}")

@cli.command()
@click.option('--limit', default=10, help='Number of news items to collect')
def news(limit):
    """Collect news data"""
    click.echo(f"📰 Collecting {limit} news items")

    try:
        news_collector = NewsCollector()
        news_data = news_collector.collect_news(limit)
        click.echo(f"✅ Collected {len(news_data)} news items")
    except Exception as e:
        click.echo(f"❌ News collection failed: {e}")

@cli.command()
@click.option('--mock/--no-mock', default=False, help='Use mock analysis instead of DeepSeek')
def analyze(mock):
    """Run AI analysis on collected data"""
    click.echo("🧠 Running AI analysis")

    try:
        # Initialize database if needed
        if db_manager.SessionLocal is None:
            db_manager.init_db()

        # Get recent market data (simplified)
        session = db_manager.get_session()
        # This is a simplified version - in real implementation you'd get recent data
        market_data = []
        news_summary = "Recent crypto news summary"

        analyzer = DeepSeekAnalyzer()
        if mock:
            result = analyzer.analyze_with_mock(market_data, news_summary)
        else:
            result = analyzer.analyze_market_data(market_data, news_summary)

        signals = result.get('signals', [])
        click.echo(f"✅ Analysis complete. Market phase: {result.get('market_phase', 'unknown')}")
        click.echo(f"📊 Generated {len(signals)} signals")

        # Filter and save signals
        signal_generator = SignalGenerator()
        filtered = signal_generator.filter_signals(signals)
        saved = signal_generator.save_signals(filtered, result.get('market_phase', 'unknown'))
        click.echo(f"✅ Saved {len(saved)} filtered signals")

    except Exception as e:
        click.echo(f"❌ Analysis failed: {e}")

@cli.command()
def send():
    """Send unsent signals to Telegram"""
    click.echo("📤 Sending signals to Telegram")

    try:
        # Initialize database if needed
        if db_manager.SessionLocal is None:
            db_manager.init_db()

        signal_generator = SignalGenerator()
        unsent_signals = signal_generator.get_unsent_signals()

        if unsent_signals:
            telegram_bot = TelegramBot()
            sent_count = telegram_bot.send_signals_batch(unsent_signals)
            click.echo(f"✅ Sent {sent_count} signals")
        else:
            click.echo("ℹ️ No unsent signals")

    except Exception as e:
        click.echo(f"❌ Sending failed: {e}")

@cli.command()
@click.option('--network', default='ethereum', help='Network to analyze')
@click.option('--limit', default=30, help='Number of tokens to collect')
def full_cycle(network, limit):
    """Run complete analysis cycle (simplified version)"""
    click.echo("🔄 Starting full analysis cycle")

    try:
        # Initialize database if needed
        if db_manager.SessionLocal is None:
            db_manager.init_db()

        # Simplified version without Celery
        collector = DexPaprikaCollector()
        market_data = collector.collect_for_analysis(network, limit)

        news_collector = NewsCollector()
        click.echo("📰 Collecting news...")
        news_data = news_collector.collect_news("BTC,ETH,SOL", 10)
        click.echo(f"📰 News data type: {type(news_data)}, length: {len(news_data) if news_data else 0}")

        news_summary = " ".join([item.get('title', '') for item in news_data[:5]]) if news_data else "No news data available"

        click.echo(f"📊 Collected {len(market_data)} market data points")
        click.echo(f"📰 News summary: {news_summary[:100]}...")

        analyzer = DeepSeekAnalyzer()
        click.echo("🤖 Starting AI analysis...")
        result = analyzer.analyze_market_data(market_data, news_summary)
        click.echo(f"🤖 AI result type: {type(result)}")

        if result is None:
            click.echo("❌ AI analysis returned None, using mock data")
            result = analyzer.analyze_with_mock(market_data, news_summary)
            click.echo(f"🤖 Mock result: {result}")

        signals = result.get('signals', [])
        signal_generator = SignalGenerator()
        filtered = signal_generator.filter_signals(signals)
        saved = signal_generator.save_signals(filtered, result.get('market_phase', 'unknown'))

        click.echo(f"✅ Cycle complete. Generated {len(saved)} signals")
        click.echo(f"📊 Market phase: {result.get('market_phase', 'unknown')}")
    except Exception as e:
        click.echo(f"❌ Full cycle failed: {e}")

@cli.command()
def init_db():
    """Initialize database schema"""
    click.echo("🗃️ Initializing database")

    try:
        db_manager.init_db()
        click.echo("✅ Database initialized")
    except Exception as e:
        click.echo(f"❌ Database initialization failed: {e}")

if __name__ == '__main__':
    cli()