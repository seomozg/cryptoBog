import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from database.db_manager import db_manager
from database.models import AISignal
from config.settings import Config
from analyzers.historical_stats import historical_stats

logger = logging.getLogger(__name__)

# Trading parameters - aggressive strategy
TAKE_PROFIT_PERCENT = 10.0  # 10% take-profit
STOP_LOSS_PERCENT = 5.0     # 5% stop-loss

class SignalGenerator:
    """Generates and filters trading signals"""

    def __init__(self):
        self.config = Config()

    def filter_blocked_tokens(self, market_data: List[Dict]) -> List[Dict]:
        """
        Отфильтровать токены, которые заблокированы из-за плохой торговой истории
        Вызывается ПЕРЕД отправкой в DeepSeek, чтобы не тратить API вызовы на заведомо неподходящие токены
        """
        from trading.trade_manager import TradeManager
        
        # Создаем временный TradeManager для проверки токенов
        tm = TradeManager()
        
        filtered_data = []
        blocked_count = 0
        
        for token in market_data:
            symbol = f"{token.get('symbol', '')}USDT"
            allowed, reason = tm.check_token_allowed(symbol)
            
            if allowed:
                filtered_data.append(token)
            else:
                blocked_count += 1
                logger.debug(f"🚫 Токен {token.get('symbol', 'unknown')} заблокирован (история сделок), исключен из анализа DeepSeek")
        
        if blocked_count > 0:
            logger.info(f"🚫 Отфильтровано {blocked_count} заблокированных токенов из {len(market_data)} (плохая история сделок)")
        return filtered_data

    def normalize_signal_parameters(self, signal: Dict) -> Dict:
        """
        Normalize signal to enforce 10% take-profit and 5% stop-loss
        This ensures consistent trading parameters regardless of AI suggestions
        """
        entry_price = signal.get('entry_max', signal.get('entry_min', 0))
        
        if entry_price <= 0:
            logger.warning(f"Invalid entry price for signal {signal.get('asset', 'unknown')}: {entry_price}")
            return signal
        
        # Calculate normalized stop-loss and take-profit
        normalized_stop_loss = entry_price * (1 - STOP_LOSS_PERCENT / 100)
        normalized_take_profit = entry_price * (1 + TAKE_PROFIT_PERCENT / 100)
        
        # Check if the signal's values differ significantly from our targets
        original_sl = signal.get('stop_loss', 0)
        original_tp = signal.get('take_profit', 0)
        
        sl_differs = original_sl > 0 and abs(original_sl - normalized_stop_loss) / normalized_stop_loss > 0.05
        tp_differs = original_tp > 0 and abs(original_tp - normalized_take_profit) / normalized_take_profit > 0.05
        
        if sl_differs or tp_differs:
            logger.info(f"📊 Нормализация параметров для {signal.get('asset', 'unknown')}:")
            if sl_differs:
                logger.info(f"  Стоп-лосс: {original_sl:.4f} -> {normalized_stop_loss:.4f} ({STOP_LOSS_PERCENT}%)")
            if tp_differs:
                logger.info(f"  Тейк-профит: {original_tp:.4f} -> {normalized_take_profit:.4f} (+{TAKE_PROFIT_PERCENT}%)")
        
        # Create normalized signal
        normalized_signal = signal.copy()
        normalized_signal['stop_loss'] = round(normalized_stop_loss, 6)
        normalized_signal['take_profit'] = round(normalized_take_profit, 6)
        
        # Recalculate risk/reward ratio based on normalized values
        risk = entry_price - normalized_stop_loss
        reward = normalized_take_profit - entry_price
        normalized_signal['risk_reward'] = round(reward / risk, 2) if risk > 0 else 0
        
        return normalized_signal

    def filter_signals(self, raw_signals: List[Dict]) -> List[Dict]:
        """
        Filter signals based on confidence, risk/reward, and historical statistics
        """
        filtered_signals = []
        
        # Получаем актуальную статистику для динамической коррекции фильтров
        stats = historical_stats().get_summary_stats()
        
        # Динамически корректируем пороги в зависимости от реального процента успеха
        min_confidence = self.config.MIN_SIGNAL_CONFIDENCE
        min_risk_reward = self.config.MIN_RISK_REWARD
        
        # Если общий винрейт < 30% - поднимаем планку на 20%
        if stats['win_rate_percent'] < 30:
            min_confidence *= 1.2
            min_risk_reward *= 1.3
            logger.info(f"🔴 Низкий винрейт {stats['win_rate_percent']}%: повышены пороги фильтрации")
        
        # Если винрейт < 15% - поднимаем планку в 2 раза
        elif stats['win_rate_percent'] < 15:
            min_confidence *= 2.0
            min_risk_reward *= 1.8
            logger.info(f"🚨 ОЧЕНЬ НИЗКИЙ винрейт {stats['win_rate_percent']}%: ПОРОГИ ПОВЫШЕНЫ В 2 РАЗА")

        for signal in raw_signals:
            confidence = signal.get('confidence', 0)
            risk_reward = signal.get('risk_reward', 0)
            asset = signal.get('asset', '')
            
            # Проверка статистики по конкретному активу
            asset_stats = historical_stats().get_asset_stats(asset)
            
            # Если по этому активу больше 2 убыточных сделок подряд - пропускаем
            if asset_stats['count'] >= 3 and asset_stats['win_rate'] < 20:
                logger.info(f"⏭️  Пропущен сигнал по {asset}: исторический винрейт {asset_stats['win_rate']}%")
                continue

            # ✅ Проверка что токен реально существует и торгуется на MEXC
            from trading.mexc_client import MEXCClient
            mexc = MEXCClient()
            
            # Проверяем что символ существует и доступен для торговли
            symbol_info = mexc.get_symbol_info(f"{asset}USDT")
            if not symbol_info:
                logger.info(f"⏭️  Пропущен сигнал по {asset}: токен не найден на MEXC")
                continue
            
            symbol_status = symbol_info.get('status', 'UNKNOWN')
            if symbol_status not in ['TRADING', '1']:
                logger.info(f"⏭️  Пропущен сигнал по {asset}: статус торговли {symbol_status}")
                continue
                
            logger.debug(f"✅ Токен {asset} проверен на MEXC, доступен для торговли")

            # Применяем динамические фильтры
            if confidence >= min_confidence:
                if risk_reward >= min_risk_reward:
                    filtered_signals.append(signal)

        # Нормализуем параметры сигналов - устанавливаем тейк-профит 10% и стоп-лосс 5%
        normalized_signals = [self.normalize_signal_parameters(sig) for sig in filtered_signals]

        logger.info(f"Filtered {len(raw_signals)} signals to {len(normalized_signals)} | "
                   f"min_confidence={min_confidence:.1f} min_risk_reward={min_risk_reward:.1f} | "
                   f"TP=+{TAKE_PROFIT_PERCENT}% SL=-{STOP_LOSS_PERCENT}%")
        return normalized_signals

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