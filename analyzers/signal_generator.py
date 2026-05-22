import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from database.db_manager import db_manager
from database.models import AISignal
from config.settings import Config
from analyzers.historical_stats import historical_stats

logger = logging.getLogger(__name__)

# Default trading parameters (fallback only if DeepSeek provides bad values)
DEFAULT_TAKE_PROFIT_PERCENT = 10.0
DEFAULT_STOP_LOSS_PERCENT = 5.0
MIN_ACCEPTABLE_TP_PERCENT = 3.0    # Below this, signal is suspicious (relaxed)
MAX_ACCEPTABLE_TP_PERCENT = 50.0   # Above this, unrealistically optimistic (relaxed)
MIN_ACCEPTABLE_SL_PERCENT = 1.0    # Below this, too tight — will get stopped out (relaxed)
MAX_ACCEPTABLE_SL_PERCENT = 20.0   # Above this, too loose — bad risk management (relaxed heavily)

# Minimum hourly transactions to consider a token "alive"
MIN_HOURLY_TXNS = 1  # Relaxed — allow low-activity tokens during testing

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

    def filter_dead_tokens(self, market_data: List[Dict]) -> List[Dict]:
        """
        Filter out dead tokens: stablecoins, tokens with no activity, suspiciously low/high prices
        Must be called BEFORE sending to DeepSeek to improve signal quality
        """
        filtered = []
        stablecoins_filtered = 0
        dead_filtered = 0
        low_activity_filtered = 0
        sus_price_filtered = 0
        
        for token in market_data:
            symbol = token.get('symbol', '')
            price = token.get('price_usd', 0)
            txns_1h = token.get('txns_1h', 0)
            txns_24h = token.get('txns_24h', 0)
            volume_24h = token.get('volume_24h', 0)
            buys_24h = token.get('buys_24h', 0)
            sells_24h = token.get('sells_24h', 0)
            price_change_24h = token.get('price_change_24h', 0)
            
            # Filter stablecoins (price between 0.95 and 1.05)
            if 0.95 <= price <= 1.05 and volume_24h > 1000:
                stablecoins = self.config.STABLECOINS
                if any(sc in symbol.upper() for sc in stablecoins):
                    stablecoins_filtered += 1
                    logger.debug(f"🪙 Filtered stablecoin: {symbol} (${price})")
                    continue
            
            # Filter suspicious price_change (garbage data from DEX Screener)
            if abs(price_change_24h) > 1000:
                sus_price_filtered += 1
                logger.debug(f"🚩 Filtered suspicious price_change: {symbol} ({price_change_24h}%)")
                continue
            
            # Filter dead tokens: very low 24h activity (catches Solana tokens with 0 txns/h)
            if txns_24h < 10:
                dead_filtered += 1
                logger.debug(f"💀 Filtered dead token: {symbol} ({txns_24h} txns/24h)")
                continue
            
            # Filter low-activity tokens: very few transactions per hour
            if txns_1h < MIN_HOURLY_TXNS and buys_24h + sells_24h < 30:
                low_activity_filtered += 1
                logger.debug(f"😴 Filtered low-activity token: {symbol} ({txns_1h} txns/h, {buys_24h+sells_24h} total/24h)")
                continue
            
            filtered.append(token)
        
        total_filtered = stablecoins_filtered + dead_filtered + low_activity_filtered + sus_price_filtered
        if total_filtered > 0:
            logger.info(
                f"🧹 Data quality filter: removed {total_filtered}/{len(market_data)} tokens "
                f"(stablecoins={stablecoins_filtered}, dead={dead_filtered}, low_activity={low_activity_filtered}, sus_price={sus_price_filtered})"
            )
        
        return filtered

    def filter_quality_dips(self, market_data: List[Dict]) -> List[Dict]:
        """
        Filter tokens for dip-buying strategy: only keep tokens that show clear reversal patterns.
        Conditions: price dropped 3-15% in 24h, buying pressure > selling, alive token.
        """
        filtered = []
        pumped_out = 0
        no_dip = 0
        selling_pressure = 0
        
        for token in market_data:
            symbol = token.get('symbol', '')
            price_change_24h = token.get('price_change_24h', 0)
            buys_1h = token.get('buys_1h', 0)
            sells_1h = token.get('sells_1h', 0)
            buys_24h = token.get('buys_24h', 0)
            sells_24h = token.get('sells_24h', 0)
            
            # Skip pumped tokens (>0% in 24h — we buy dips, not highs)
            if price_change_24h > 0:
                pumped_out += 1
                logger.debug(f"📈 Skipped pumped token: {symbol} (+{price_change_24h}% 24h)")
                continue
            
            # Skip tokens that didn't dip enough or crashed too hard
            if price_change_24h > -3:
                no_dip += 1
                logger.debug(f"➡️ Skipped flat token: {symbol} ({price_change_24h}% 24h)")
                continue
            
            if price_change_24h < -25:
                no_dip += 1
                logger.debug(f"📉 Skipped crashed token: {symbol} ({price_change_24h}% 24h)")
                continue
            
            # Check buying pressure: 1h window is best for timing
            if buys_1h > 0 and sells_1h > 0 and buys_1h <= sells_1h:
                selling_pressure += 1
                logger.debug(f"📊 Skipped selling pressure: {symbol} (buys={buys_1h} sells={sells_1h} 1h)")
                continue
            
            # Also check 24h window as fallback
            if buys_1h == 0 and sells_1h == 0 and buys_24h > 0 and buys_24h <= sells_24h:
                selling_pressure += 1
                logger.debug(f"📊 Skipped 24h selling pressure: {symbol}")
                continue
            
            filtered.append(token)
        
        total_filtered = pumped_out + no_dip + selling_pressure
        if total_filtered > 0:
            logger.info(
                f"🎯 Quality dip filter: kept {len(filtered)}/{len(market_data)} tokens "
                f"(pumped={pumped_out}, no_dip={no_dip}, selling={selling_pressure})"
            )
        
        return filtered

    def normalize_signal_parameters(self, signal: Dict) -> Dict:
        """
        Smart normalization: respect DeepSeek's TP/SL when reasonable, 
        apply defaults only when values are missing or absurd.
        REJECTS signals with dangerously wide SL or unrealistically high TP.
        
        Returns signal with added '_rejected' key if signal should be discarded.
        """
        entry_price = signal.get('entry_max', signal.get('entry_min', 0))
        original_sl = signal.get('stop_loss', 0)
        original_tp = signal.get('take_profit', 0)
        asset = signal.get('asset', 'unknown')
        
        if entry_price <= 0:
            logger.warning(f"Invalid entry price for signal {asset}: {entry_price}")
            signal['_rejected'] = True
            signal['_reject_reason'] = 'Invalid entry price'
            return signal
        
        # If DeepSeek didn't provide TP/SL, use defaults
        if original_sl <= 0 or original_tp <= 0:
            logger.info(f"📊 {asset}: DeepSeek didn't provide TP/SL, using defaults (TP=+{DEFAULT_TAKE_PROFIT_PERCENT}%, SL=-{DEFAULT_STOP_LOSS_PERCENT}%)")
            normalized = signal.copy()
            normalized['stop_loss'] = round(entry_price * (1 - DEFAULT_STOP_LOSS_PERCENT / 100), 6)
            normalized['take_profit'] = round(entry_price * (1 + DEFAULT_TAKE_PROFIT_PERCENT / 100), 6)
            normalized['risk_reward'] = round(DEFAULT_TAKE_PROFIT_PERCENT / DEFAULT_STOP_LOSS_PERCENT, 2)
            return normalized
        
        # Calculate what DeepSeek suggested as percentages
        sl_percent = (entry_price - original_sl) / entry_price * 100
        tp_percent = (original_tp - entry_price) / entry_price * 100
        
        # REJECT signals with dangerously wide stop-loss (>8%)
        if sl_percent > MAX_ACCEPTABLE_SL_PERCENT:
            logger.warning(f"⛔ REJECTED {asset}: SL={sl_percent:.1f}% exceeds max {MAX_ACCEPTABLE_SL_PERCENT}%")
            signal['_rejected'] = True
            signal['_reject_reason'] = f'Stop-loss too wide: {sl_percent:.1f}%'
            return signal
        
        # REJECT signals with unbelievably high take-profit (>30%)
        if tp_percent > MAX_ACCEPTABLE_TP_PERCENT:
            logger.warning(f"⛔ REJECTED {asset}: TP={tp_percent:.1f}% exceeds max {MAX_ACCEPTABLE_TP_PERCENT}%")
            signal['_rejected'] = True
            signal['_reject_reason'] = f'Take-profit unrealistically high: {tp_percent:.1f}%'
            return signal
        
        # REJECT signals with TP < SL (negative risk/reward)
        if tp_percent <= sl_percent:
            logger.warning(f"⛔ REJECTED {asset}: TP={tp_percent:.1f}% <= SL={sl_percent:.1f}% (bad risk/reward)")
            signal['_rejected'] = True
            signal['_reject_reason'] = f'TP ({tp_percent:.1f}%) <= SL ({sl_percent:.1f}%)'
            return signal
        
        # If DeepSeek's SL is too tight (<2%), widen to min acceptable
        if sl_percent < MIN_ACCEPTABLE_SL_PERCENT:
            logger.info(f"📊 {asset}: SL too tight ({sl_percent:.1f}%), widening to {MIN_ACCEPTABLE_SL_PERCENT}%")
            sl_percent = MIN_ACCEPTABLE_SL_PERCENT
        
        # If DeepSeek's TP is too low (<5%), it's probably not worth trading
        if tp_percent < MIN_ACCEPTABLE_TP_PERCENT:
            logger.warning(f"⛔ REJECTED {asset}: TP={tp_percent:.1f}% below min {MIN_ACCEPTABLE_TP_PERCENT}%")
            signal['_rejected'] = True
            signal['_reject_reason'] = f'Take-profit too low: {tp_percent:.1f}%'
            return signal
        
        # Accept DeepSeek's values (with SL widened if needed)
        normalized = signal.copy()
        normalized['stop_loss'] = round(entry_price * (1 - sl_percent / 100), 6)
        normalized['take_profit'] = round(entry_price * (1 + tp_percent / 100), 6)
        
        # Recalculate risk/reward
        risk = entry_price - normalized['stop_loss']
        reward = normalized['take_profit'] - entry_price
        normalized['risk_reward'] = round(reward / risk, 2) if risk > 0 else 0
        
        if sl_percent != (entry_price - original_sl) / entry_price * 100 or tp_percent != (original_tp - entry_price) / entry_price * 100:
            logger.info(
                f"📊 Normalized {asset}: "
                f"SL {original_sl:.4f}→{normalized['stop_loss']:.4f} ({sl_percent:.1f}%), "
                f"TP {original_tp:.4f}→{normalized['take_profit']:.4f} (+{tp_percent:.1f}%)"
            )
        
        return normalized

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
            logger.info(f"🔴 Низкий винрейт {stats['win_rate_percent']}%: повышены пороги фильтрации "
                       f"(confidence≥{min_confidence:.1f}, RR≥{min_risk_reward:.1f})")
        
        # Если винрейт < 15% - поднимаем планку в 2 раза
        elif stats['win_rate_percent'] < 15:
            min_confidence *= 2.0
            min_risk_reward *= 1.8
            logger.info(f"🚨 ОЧЕНЬ НИЗКИЙ винрейт {stats['win_rate_percent']}%: ПОРОГИ ПОВЫШЕНЫ В 2 РАЗА "
                       f"(confidence≥{min_confidence:.1f}, RR≥{min_risk_reward:.1f})")

        # Cap min_confidence at 95 (don't make it impossible)
        if min_confidence > 95:
            min_confidence = 95
            logger.info(f"⚠️ min_confidence capped at 95")

        rejected_count = 0
        for signal in raw_signals:
            # Skip already rejected signals
            if signal.get('_rejected'):
                rejected_count += 1
                continue
                
            confidence = signal.get('confidence', 0)
            risk_reward = signal.get('risk_reward', 0)
            asset = signal.get('asset', '')
            
            # Проверка статистики по конкретному активу
            asset_stats = historical_stats().get_asset_stats(asset)
            
            # Если по этому активу больше 2 убыточных сделок подряд - пропускаем
            if asset_stats['count'] >= 3 and asset_stats['win_rate'] < 20:
                logger.info(f"⏭️  Пропущен сигнал по {asset}: исторический винрейт {asset_stats['win_rate']}%")
                rejected_count += 1
                continue

            # ✅ Проверка что токен реально существует и торгуется на MEXC
            from trading.mexc_client import MEXCClient
            mexc = MEXCClient()
            
            # Проверяем что символ существует и доступен для торговли
            symbol_info = mexc.get_symbol_info(f"{asset}USDT")
            if not symbol_info:
                logger.info(f"⏭️  Пропущен сигнал по {asset}: токен не найден на MEXC")
                rejected_count += 1
                continue
            
            symbol_status = symbol_info.get('status', 'UNKNOWN')
            if symbol_status not in ['TRADING', '1']:
                logger.info(f"⏭️  Пропущен сигнал по {asset}: статус торговли {symbol_status}")
                rejected_count += 1
                continue
                
            logger.debug(f"✅ Токен {asset} проверен на MEXC, доступен для торговли")

            # Применяем динамические фильтры
            if confidence < min_confidence:
                logger.debug(f"⏭️  {asset}: confidence {confidence:.1f} < {min_confidence:.1f}")
                rejected_count += 1
                continue
                
            if risk_reward < min_risk_reward:
                logger.debug(f"⏭️  {asset}: risk_reward {risk_reward:.1f} < {min_risk_reward:.1f}")
                rejected_count += 1
                continue
                
            filtered_signals.append(signal)

        # Нормализуем параметры сигналов — уважаем DeepSeek, применяем дефолты только при необходимости
        normalized_signals = [self.normalize_signal_parameters(sig) for sig in filtered_signals]
        # Filter out any signals that got rejected during normalization
        normalized_signals = [s for s in normalized_signals if not s.get('_rejected')]

        logger.info(f"Filtered {len(raw_signals)} signals to {len(normalized_signals)} | "
                   f"min_confidence={min_confidence:.1f} min_risk_reward={min_risk_reward:.1f} | "
                   f"rejected={rejected_count}")
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