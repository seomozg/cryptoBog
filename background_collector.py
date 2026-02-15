#!/usr/bin/env python3
"""
Background data collector for the web interface
Runs periodic data collection tasks
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from collectors.dex_paprika import DexPaprikaCollector
from analyzers.ai_adapter import DeepSeekAnalyzer
from analyzers.signal_generator import SignalGenerator
from telegram.bot import TelegramBot
from trading.trade_manager import TradeManager
from database.db_manager import db_manager
from database.models import AISignal
from config.settings import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BackgroundCollector:
    def __init__(self):
        self.config = Config()
        self.running = False
        self.thread = None

    def collect_data(self):
        """Collect market data and news"""
        try:
            logger.info("Starting data collection")

            # Initialize database if needed
            if db_manager.SessionLocal is None:
                db_manager.init_db()

            # Collect market data
            collector = DexPaprikaCollector()
            market_data = collector.collect_for_analysis("ethereum", 100)

            if not market_data:
                logger.error("No market data collected - aborting cycle")
                return None

            logger.info(f"Collected {len(market_data)} market data points")

            # Log prices for debugging
            logger.info("=== MARKET DATA PRICES ===")
            for token in market_data[:10]:  # Log first 10 tokens
                price = token.get('price_usd', 0)
                symbol = token.get('symbol', 'UNKNOWN')
                logger.info(f"{symbol}: ${price:.6f}")

            if len(market_data) > 10:
                logger.info(f"... and {len(market_data) - 10} more tokens")

            # Collect news (disabled due to API issues)
            # news_collector = NewsCollector()
            # news_data = news_collector.collect_news("BTC,ETH,SOL", 10)
            news_data = []
            news_summary = "News collection disabled due to API issues"
            logger.info("News collection disabled")

            return {
                'market_data': market_data,
                'news_summary': news_summary
            }

        except Exception as e:
            logger.error(f"Data collection failed: {e}")
            return None

    def analyze_and_process(self, collected_data):
        """Run AI analysis and process signals"""
        try:
            logger.info("Starting AI analysis")

            market_data = collected_data.get('market_data', [])
            news_summary = collected_data.get('news_summary', '')

            # Get list of assets that can receive signals (respecting open positions)
            signal_generator = SignalGenerator()

            # Get assets with open positions (don't trade what we already hold)
            session = db_manager.get_session()
            from database.models import TradePosition
            open_positions = session.query(TradePosition).filter(
                TradePosition.status == 'OPEN'
            ).all()

            open_position_assets = set(position.symbol.replace('USDT', '') for position in open_positions)
            session.close()

            # Filter market data to only include assets that can receive signals
            allowed_market_data = [
                token for token in market_data
                if token.get('symbol', '').upper() not in open_position_assets
            ]

            logger.info(f"AI analysis: {len(market_data)} total tokens, {len(allowed_market_data)} allowed for signals")
            logger.info(f"Assets with open positions: {list(open_position_assets)}")

            if not allowed_market_data:
                logger.info("No assets available for new signals (all have open positions)")
                return 0

            # Analyze with AI using only allowed assets
            analyzer = DeepSeekAnalyzer()
            analysis_result = analyzer.analyze_market_data(allowed_market_data, news_summary)

            if analysis_result:
                logger.info(f"AI analysis complete. Market phase: {analysis_result.get('market_phase', 'unknown')}")

                # Process signals
                raw_signals = analysis_result.get('signals', [])
                market_phase = analysis_result.get('market_phase', 'unknown')

                filtered_signals = signal_generator.filter_signals(raw_signals)
                saved_signals = signal_generator.save_signals(filtered_signals, market_phase)

                logger.info(f"Processed {len(saved_signals)} signals")

                return len(saved_signals)
            else:
                logger.warning("AI analysis returned no result")
                return 0

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return 0

    def execute_automated_trades(self, signals_count):
        """Execute automated trades for generated signals"""
        try:
            logger.info("Executing automated trades for signals")

            # Get sendable signals (those that haven't been traded recently)
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
            return 0

    def run_cycle(self):
        """Run complete analysis cycle"""
        logger.info("Starting full analysis cycle")

        # Step 1: Collect data
        collected_data = self.collect_data()
        if not collected_data:
            return

        # Step 2: Analyze and process
        signals_count = self.analyze_and_process(collected_data)

        # Step 3: Execute automated trades for signals
        trade_count = self.execute_automated_trades(signals_count)

        # Step 4: Check and execute sell orders for open positions
        try:
            # Create price mapping for sell checks
            current_prices = {token.get('symbol', ''): token.get('price_usd', 0) for token in collected_data.get('market_data', [])}
            trade_manager = TradeManager()
            sell_count = trade_manager.check_and_execute_sells(current_prices)
        except Exception as e:
            logger.error(f"Error checking sell orders: {e}")
            sell_count = 0

        logger.info(f"Cycle complete: {signals_count} signals generated, {trade_count} automated trades executed, {sell_count} positions closed")

    def background_loop(self):
        """Main background loop"""
        collection_interval = self.config.COLLECTION_INTERVAL_MINUTES * 60  # Convert to seconds
        cycle_count = 0

        while self.running:
            try:
                cycle_count += 1
                logger.info(f"Starting cycle #{cycle_count}")

                self.run_cycle()

                # Wait for next cycle
                logger.info(f"Waiting {collection_interval} seconds until next cycle")
                time.sleep(collection_interval)

            except Exception as e:
                logger.error(f"Error in background loop: {e}")
                time.sleep(60)  # Wait a minute before retrying

    def start(self):
        """Start the background collector"""
        if self.running:
            logger.warning("Background collector is already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self.background_loop, daemon=True)
        self.thread.start()
        logger.info("Background collector started")

    def stop(self):
        """Stop the background collector"""
        if not self.running:
            logger.warning("Background collector is not running")
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Background collector stopped")

def main():
    """Main function to run the background collector"""
    collector = BackgroundCollector()

    try:
        logger.info("Starting background data collector")
        collector.start()

        # Keep the main thread alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        collector.stop()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        collector.stop()

if __name__ == '__main__':
    main()