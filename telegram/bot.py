import logging
from typing import List
from database.models import AISignal
from config.settings import Config
from analyzers.signal_generator import SignalGenerator
from trading.trade_manager import TradeManager

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram bot for sending trading signals"""

    def __init__(self):
        self.config = Config()
        self.bot_token = self.config.TELEGRAM_BOT_TOKEN
        self.chat_id = self.config.TELEGRAM_CHAT_ID
        self.signal_generator = SignalGenerator()

        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram bot not configured")

    def send_signal(self, signal: AISignal) -> bool:
        """
        Send a trading signal to Telegram
        """
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram bot not configured, skipping send")
            return False

        message = self._format_signal_message(signal)

        try:
            import requests
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }

            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()

            # Mark signal as sent
            self.signal_generator.mark_signal_sent(int(signal.id))

            # Execute automated buy order
            trade_manager = TradeManager()
            trade_manager.execute_signal_buy(signal)

            logger.info(f"Sent signal for {signal.asset} to Telegram")
            return True

        except Exception as e:
            logger.error(f"Failed to send signal to Telegram: {e}")
            return False

    def send_signals_batch(self, signals: List[AISignal]) -> int:
        """
        Send multiple signals to Telegram
        Returns number of successfully sent signals
        """
        sent_count = 0
        for signal in signals:
            if self.send_signal(signal):
                sent_count += 1
        return sent_count

    def _format_signal_message(self, signal: AISignal) -> str:
        """
        Format signal data into Telegram message
        """
        # Debug logging
        logger.info(f"Formatting signal for {signal.asset}: entry_min={signal.entry_min}, entry_max={signal.entry_max}, stop_loss={signal.stop_loss}, take_profit={signal.take_profit}")

        entry_range = f"${signal.entry_min:.2f}–{signal.entry_max:.2f}"
        stop_loss_pct = ((signal.stop_loss - signal.entry_min) / signal.entry_min) * 100 if signal.entry_min and signal.entry_min > 0 else 0
        take_profit_pct = ((signal.take_profit - signal.entry_max) / signal.entry_max) * 100 if signal.entry_max and signal.entry_max > 0 else 0

        message = f"""🎯 *СИГНАЛ [{signal.asset.upper()}]*

Действие: ПОКУПКА НА ОТКАТЕ
Вход: {entry_range}
Стоп-лосс: ${signal.stop_loss:.2f} ({stop_loss_pct:.1f}%)
Тейк-профит: ${signal.take_profit:.2f} (+{take_profit_pct:.1f}%)

🔥 Вероятность успеха: {signal.probability:.1f}%
⚡ Уверенность: {signal.confidence:.1f}%
📊 Risk/Reward: {signal.risk_reward:.1f}

📚 Исторический аналог: {signal.historical_analogs}
💡 Обоснование: {signal.reasoning}

⏳ Актуален: 48 часов"""

        return message

    def send_status_message(self, message: str) -> bool:
        """
        Send a status message to Telegram
        """
        if not self.bot_token or not self.chat_id:
            return False

        try:
            import requests
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }

            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            return True

        except Exception as e:
            logger.error(f"Failed to send status message: {e}")
            return False