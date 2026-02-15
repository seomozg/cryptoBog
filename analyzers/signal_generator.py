import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from database.db_manager import db_manager
from database.models import AISignal
from config.settings import Config

logger = logging.getLogger(__name__)

class SignalGenerator:
    """Generates and filters trading signals"""

    def __init__(self):
        self.config = Config()

    def filter_signals(self, raw_signals: List[Dict]) -> List[Dict]:
        """
        Filter signals based on confidence, risk/reward, and other criteria
        """
        filtered_signals = []

        for signal in raw_signals:
            confidence = signal.get('confidence', 0)
            risk_reward = signal.get('risk_reward', 0)

            # Apply filters
            if confidence >= self.config.MIN_SIGNAL_CONFIDENCE:
                if risk_reward >= self.config.MIN_RISK_REWARD:
                    filtered_signals.append(signal)

        logger.info(f"Filtered {len(raw_signals)} signals to {len(filtered_signals)}")
        return filtered_signals

    def save_signals(self, signals: List[Dict], market_phase: str) -> List[AISignal]:
        """
        Save filtered signals to database
        """
        saved_signals = []

        try:
            session = db_manager.get_session()

            for signal_data in signals:
                # Check if we haven't exceeded daily limit
                today_signals = session.query(AISignal).filter(
                    AISignal.generated_at >= datetime.utcnow().date(),
                    AISignal.sent_to_telegram == False
                ).count()

                if today_signals >= self.config.MAX_SIGNALS_PER_DAY:
                    logger.info("Daily signal limit reached")
                    break

                # Create signal object
                signal = AISignal(
                    asset=signal_data['asset'],
                    action=signal_data['action'],
                    entry_min=signal_data['entry_min'],
                    entry_max=signal_data['entry_max'],
                    stop_loss=signal_data['stop_loss'],
                    take_profit=signal_data['take_profit'],
                    probability=signal_data['probability'],
                    confidence=signal_data['confidence'],
                    risk_reward=signal_data['risk_reward'],
                    reasoning=signal_data['reasoning'],
                    historical_analogs=signal_data['historical_analog']
                )

                session.add(signal)
                saved_signals.append(signal)

            session.commit()
            session.close()

            logger.info(f"Saved {len(saved_signals)} signals to database")
            return saved_signals

        except Exception as e:
            logger.error(f"Failed to save signals: {e}")
            return []

    def get_unsent_signals(self) -> List[AISignal]:
        """
        Get signals that haven't been sent to Telegram yet
        """
        try:
            session = db_manager.get_session()
            signals = session.query(AISignal).filter(
                AISignal.sent_to_telegram == False
            ).all()
            session.close()
            return signals
        except Exception as e:
            logger.error(f"Failed to get unsent signals: {e}")
            return []

    def get_sendable_signals(self) -> List[AISignal]:
        """
        Get signals that can be sent to Telegram (respecting 48-hour cooldown per asset)
        """
        try:
            session = db_manager.get_session()

            # Get all unsent signals
            unsent_signals = session.query(AISignal).filter(
                AISignal.sent_to_telegram == False
            ).all()

            sendable_signals = []
            cutoff_time = datetime.utcnow() - timedelta(hours=48)

            for signal in unsent_signals:
                # Check if we sent a signal for this asset in the last 48 hours
                last_sent_signal = session.query(AISignal).filter(
                    AISignal.asset == signal.asset,
                    AISignal.sent_to_telegram == True,
                    AISignal.generated_at >= cutoff_time
                ).order_by(AISignal.generated_at.desc()).first()

                if last_sent_signal is None:
                    # No recent signal for this asset, can send
                    sendable_signals.append(signal)
                    logger.info(f"Signal for {signal.asset} is sendable (no recent signals)")
                else:
                    # Recent signal exists, skip
                    time_since_last = datetime.utcnow() - last_sent_signal.generated_at
                    hours_since_last = time_since_last.total_seconds() / 3600
                    logger.info(f"Signal for {signal.asset} skipped - last signal sent {hours_since_last:.1f} hours ago")

            session.close()
            logger.info(f"Found {len(sendable_signals)} sendable signals out of {len(unsent_signals)} unsent")
            return sendable_signals

        except Exception as e:
            logger.error(f"Failed to get sendable signals: {e}")
            return []

    def mark_signal_sent(self, signal_id: int):
        """
        Mark signal as sent to Telegram
        """
        try:
            session = db_manager.get_session()
            signal = session.query(AISignal).filter(AISignal.id == signal_id).first()
            if signal:
                signal.sent_to_telegram = True
                session.commit()
            session.close()
        except Exception as e:
            logger.error(f"Failed to mark signal as sent: {e}")