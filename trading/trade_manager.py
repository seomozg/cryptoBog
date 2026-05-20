#!/usr/bin/env python3
"""
Trade manager for automated trading operations
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from database.db_manager import db_manager
from database.models import TradePosition, AISignal
from trading.mexc_client import MEXCClient
from config.settings import Config

logger = logging.getLogger(__name__)

class TradeManager:
    """Manages automated trading operations"""

    def __init__(self):
        self.config = Config()
        self.mexc_client = MEXCClient()
        self.telegram_bot = None
        self._blocked_tokens = {}  # token -> (reason, blocked_at)
        self._daily_pnl = 0.0
        self._daily_pnl_date = None
        self._trailing_stops = {}  # symbol -> highest_price_seen

    def _get_telegram_bot(self):
        """Lazy initialization of Telegram bot"""
        if self.telegram_bot is None:
            import sys
            import os
            # Add parent directory to path to import local telegram module
            parent_dir = os.path.dirname(os.path.dirname(__file__))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            from telegram.bot import TelegramBot
            self.telegram_bot = TelegramBot()
        return self.telegram_bot

    def _is_valid_symbol(self, asset: str) -> bool:
        """Check if asset name is valid for MEXC API"""
        if not asset:
            return False
        # Check for spaces, special characters, or too long names
        if ' ' in asset or len(asset) > 20:
            return False
        # Check for only alphanumeric characters
        if not asset.replace('_', '').isalnum():
            return False
        return True

    def analyze_token_trades(self, symbol: str) -> Dict:
        """
        Analyze closed trades for a specific token to determine if it should be blocked.
        Returns dict with analysis results.
        """
        from datetime import timedelta
        
        try:
            session = db_manager.get_session()
            lookback_time = datetime.utcnow() - timedelta(days=self.config.TOKEN_LOSS_LOOKBACK_DAYS)
            
            # Get closed positions for this symbol in lookback period
            closed_positions = session.query(TradePosition).filter(
                TradePosition.symbol == symbol,
                TradePosition.status == 'CLOSED',
                TradePosition.closed_at >= lookback_time
            ).order_by(TradePosition.closed_at.desc()).all()
            
            if not closed_positions:
                session.close()
                return {
                    'should_block': False,
                    'reason': 'No trades for this token',
                    'total_trades': 0,
                    'wins': 0,
                    'losses': 0,
                    'loss_ratio': 0
                }
            
            wins = 0
            losses = 0
            
            for pos in closed_positions:
                if pos.exit_price is None or pos.entry_price is None or pos.entry_price == 0:
                    continue
                
                # FIXED: Use PERCENTAGE PnL for classification, not absolute value
                # Previously: absolute PnL made high-price tokens always appear worse
                pnl_percent = (pos.exit_price - pos.entry_price) / pos.entry_price * 100
                if pnl_percent > 0:
                    wins += 1
                else:
                    losses += 1
            
            total_trades = wins + losses
            loss_ratio = (losses / total_trades * 100) if total_trades > 0 else 0
            
            # Determine if token should be blocked
            should_block = False
            reason = ""
            
            min_trades = self.config.TOKEN_MIN_TRADES_FOR_BLOCK
            max_loss_ratio = self.config.TOKEN_MAX_LOSS_RATIO_PERCENT
            
            if total_trades >= min_trades and loss_ratio >= max_loss_ratio:
                should_block = True
                reason = f"🚫 Токен {symbol} заблокирован: {losses} убыточных из {total_trades} сделок ({loss_ratio:.0f}%) за {self.config.TOKEN_LOSS_LOOKBACK_DAYS} дней"
            
            session.close()
            
            return {
                'should_block': should_block,
                'reason': reason,
                'total_trades': total_trades,
                'wins': wins,
                'losses': losses,
                'loss_ratio': loss_ratio
            }
            
        except Exception as e:
            logger.error(f"Error analyzing token trades for {symbol}: {e}")
            return {
                'should_block': False,
                'reason': f'Error: {str(e)}',
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'loss_ratio': 0
            }

    def check_token_allowed(self, symbol: str) -> tuple[bool, str]:
        """
        Check if trading is allowed for a specific token.
        Returns (allowed, reason) tuple.
        """
        # Check if token is in blocked list
        if symbol in self._blocked_tokens:
            return False, self._blocked_tokens[symbol]
            
        analysis = self.analyze_token_trades(symbol)
        
        if analysis['should_block']:
            self._blocked_tokens[symbol] = analysis['reason']
            logger.warning(f"⚠️ {analysis['reason']}")
            
            # Send notification about blocked token
            try:
                telegram_bot = self._get_telegram_bot()
                message = f"""🚫 *ТОКЕН ЗАБЛОКИРОВАН* 🚫

🎯 **{symbol.replace('USDT', '')}**

📊 Статистика за {self.config.TOKEN_LOSS_LOOKBACK_DAYS} дней:
• Всего сделок: {analysis['total_trades']}
• Прибыльных: {analysis['wins']}
• Убыточных: {analysis['losses']}
• Процент убыточных: {analysis['loss_ratio']:.0f}%

💡 Токен добавлен в стоп-лист. Покупки этого токена пропускаются."""
                telegram_bot.send_status_message(message)
            except Exception as e:
                logger.error(f"Error sending block notification: {e}")
                
            return False, analysis['reason']
            
        return True, ""

    def execute_signal_buy(self, signal) -> bool:
        """Execute buy order for trading signal"""
        if not self.config.ENABLE_AUTO_TRADING:
            logger.info("Auto trading disabled, skipping buy order")
            return False

        try:
            # Validate asset name
            if not self._is_valid_symbol(signal.asset):
                logger.warning(f"Skipping invalid asset name for API trading: {signal.asset}")
                self._mark_signal_traded(signal)
                return False

            # Convert symbol to MEXC format (add USDT)
            symbol = f"{signal.asset}USDT"

            # Check if token is allowed based on its trade history
            allowed, reason = self.check_token_allowed(symbol)
            if not allowed:
                logger.warning(f"⚠️ Token blocked: {reason}")
                self._mark_signal_traded(signal)
                return False

            if symbol in self.config.UNSUPPORTED_SYMBOLS:
                logger.warning(f"Skipping unsupported symbol for API trading: {symbol}")
                self._mark_signal_traded(signal)
                return False

            # Check if there's already an open position for this asset
            session = db_manager.get_session()
            existing_position = session.query(TradePosition).filter(
                TradePosition.symbol == symbol,
                TradePosition.status == 'OPEN'
            ).first()
            session.close()

            if existing_position:
                logger.warning(f"⚠️ Already have open position for {symbol}, skipping buy")
                self._mark_signal_traded(signal)
                return False

            # Place buy order
            order_result = self.mexc_client.place_buy_order(symbol, self.config.TRADE_AMOUNT_USDT)

            if 'error' not in order_result:
                # Save position to database
                self._save_position(signal, order_result, 'BUY')
                logger.info(f"Successfully executed buy order for {signal.asset}")

                # Mark signal as used to prevent re-trading
                self._mark_signal_traded(signal)

                # Send Telegram notification about the trade
                self._send_buy_notification(signal, order_result)
                return True
            else:
                logger.error(f"Failed to execute buy order for {signal.asset}: {order_result['error']}")
                # If symbol is not supported by API (code -1121 or 10007), mark as traded and add to unsupported
                error_code = order_result.get('code')
                if error_code in [-1121, 10007]:
                    logger.warning(f"Symbol {symbol} not found on MEXC, adding to unsupported list")
                    self.config.add_unsupported_symbol(symbol)
                    self._mark_signal_traded(signal)
                return False

        except Exception as e:
            logger.error(f"Error executing buy order: {e}")
            return False

    def check_and_execute_sells(self, current_prices: Dict[str, float]) -> int:
        """Check open positions and execute sell orders if conditions met"""
        logger.info(f"🔍 Checking sell conditions for {len(current_prices)} price updates")

        if not self.config.ENABLE_AUTO_TRADING:
            logger.info("❌ Auto trading disabled, skipping sell checks")
            return 0

        try:
            # Get all open positions
            session = db_manager.get_session()
            open_positions = session.query(TradePosition).filter(
                TradePosition.status == 'OPEN'
            ).all()
            session.close()

            logger.info(f"📊 Found {len(open_positions)} open positions to check")

            if not open_positions:
                logger.info("ℹ️  No open positions to check")
                return 0

            sell_count = 0

            for position in open_positions:
                logger.info(f"🔎 Checking position {position.symbol}: entry=${position.entry_price:.4f}, stop=${position.stop_loss:.4f}, target=${position.take_profit:.4f}")
                if self._should_sell_position(position, current_prices):
                    logger.info(f"🎯 Sell condition met for {position.symbol}")
                    if self._execute_sell_order(position):
                        sell_count += 1
                        logger.info(f"✅ Successfully closed position {position.symbol}")
                    else:
                        logger.error(f"❌ Failed to close position {position.symbol}")
                else:
                    logger.info(f"⏳ Position {position.symbol} still open - conditions not met")

            logger.info(f"📈 Sell check complete: {sell_count} positions closed")
            return sell_count

        except Exception as e:
            logger.error(f"❌ Error checking sell conditions: {e}")
            return 0

    def _should_sell_position(self, position, current_prices: Dict[str, float]) -> bool:
        """
        Check if position should be sold based on:
        1. Stop loss
        2. Take profit
        3. Trailing stop (if enabled)
        4. Position age timeout (force close after N hours)
        5. Daily loss limit breach
        """
        try:
            symbol = position.symbol.replace('USDT', '')  # Remove USDT suffix
            current_price = current_prices.get(symbol)

            # If price not found in DEX data, try to get from MEXC API
            if not current_price:
                logger.info(f"📊 Price for {symbol} not in DEX data, fetching from MEXC...")
                current_price = self.mexc_client.get_symbol_price(position.symbol)
                if current_price:
                    logger.info(f"💰 MEXC price for {position.symbol}: ${current_price:.4f}")
                else:
                    logger.warning(f"⚠️ Could not get price for {position.symbol} from any source")
                    return False

            entry_price = position.entry_price
            original_stop_loss = position.stop_loss
            take_profit = position.take_profit

            # === TRAILING STOP LOGIC ===
            effective_stop_loss = original_stop_loss
            if self.config.TRAILING_STOP_ENABLED:
                trigger_pct = self.config.TRAILING_STOP_TRIGGER_PERCENT / 100.0
                distance_pct = self.config.TRAILING_STOP_DISTANCE_PERCENT / 100.0
                trigger_price = entry_price * (1 + trigger_pct)
                
                # Track highest price seen for this position
                if position.symbol not in self._trailing_stops:
                    self._trailing_stops[position.symbol] = current_price
                
                if current_price > self._trailing_stops[position.symbol]:
                    self._trailing_stops[position.symbol] = current_price
                
                highest_price = self._trailing_stops[position.symbol]
                
                # Activate trailing stop only after price rises above trigger
                if highest_price >= trigger_price:
                    trailing_sl = highest_price * (1 - distance_pct)
                    if trailing_sl > effective_stop_loss:
                        effective_stop_loss = trailing_sl
                        logger.info(f"📈 {position.symbol}: Trailing stop activated at ${effective_stop_loss:.4f} "
                                   f"(highest=${highest_price:.4f}, distance={distance_pct*100:.1f}%)")

            logger.info(f"📈 {position.symbol}: current=${current_price:.4f}, entry=${entry_price:.4f}, "
                       f"stop=${effective_stop_loss:.4f}, target=${take_profit:.4f}")

            # Check stop loss (including trailing stop)
            if current_price <= effective_stop_loss:
                reason = "trailing stop" if effective_stop_loss > original_stop_loss else "stop loss"
                logger.info(f"🛑 {reason.title()} triggered for {position.symbol}: current ${current_price:.4f} <= stop ${effective_stop_loss:.4f}")
                return True

            # Check take profit
            if current_price >= take_profit:
                logger.info(f"🎯 Take profit triggered for {position.symbol}: current ${current_price:.4f} >= target ${take_profit:.4f}")
                return True

            # === POSITION AGE TIMEOUT ===
            if position.opened_at:
                age_hours = (datetime.utcnow() - position.opened_at).total_seconds() / 3600
                max_age = self.config.MAX_POSITION_AGE_HOURS
                if age_hours >= max_age:
                    pnl_pct = (current_price - entry_price) / entry_price * 100
                    logger.info(f"⏰ Timeout for {position.symbol}: age={age_hours:.1f}h >= max={max_age}h, PnL={pnl_pct:+.1f}%")
                    return True

            # === DAILY LOSS LIMIT CHECK ===
            today = datetime.utcnow().date()
            if self._daily_pnl_date != today:
                self._daily_pnl = 0.0
                self._daily_pnl_date = today
            
            unrealized_pnl = (current_price - entry_price) * position.quantity
            projected_daily_pnl = self._daily_pnl + unrealized_pnl
            
            max_daily_loss = self.config.MAX_DAILY_LOSS_USDT
            if projected_daily_pnl <= -max_daily_loss:
                logger.warning(f"⚠️ Daily loss limit breach for {position.symbol}: projected PnL=${projected_daily_pnl:.2f} <= -${max_daily_loss}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking sell conditions for {position.symbol}: {e}")
            return False

    def _execute_sell_order(self, position) -> bool:
        """Execute sell order for position"""
        try:
            # Get current balance
            balance = self.mexc_client.get_symbol_balance(position.symbol.replace('USDT', ''))

            if balance <= 0:
                logger.warning(f"No balance to sell for {position.symbol}")
                return False

            # Place sell order
            order_result = self.mexc_client.place_sell_order(position.symbol, balance)

            if 'error' not in order_result:
                # Update position status
                self._update_position_status(position, order_result, 'CLOSED')
                logger.info(f"Successfully executed sell order for {position.symbol}")

                # Send Telegram notification about the trade
                self._send_sell_notification(position, order_result)
                
                return True
            else:
                logger.error(f"Failed to execute sell order for {position.symbol}: {order_result['error']}")
                return False

        except Exception as e:
            logger.error(f"Error executing sell order: {e}")
            return False

    def _save_position(self, signal, order_result: Dict, side: str):
        """Save trade position to database — recalculates SL/TP from ACTUAL fill price"""
        try:
            session = db_manager.get_session()

            executed_qty = float(order_result.get('executedQty', 0) or 0)
            total_usdt = float(order_result.get('cummulativeQuoteQty', 0) or 0)
            order_price = float(order_result.get('price', 0) or 0)
            if order_price == 0 and executed_qty > 0 and total_usdt > 0:
                order_price = total_usdt / executed_qty
            if order_price == 0:
                order_price = signal.entry_min

            # CRITICAL FIX: Recalculate SL/TP from ACTUAL fill price, not from signal's estimated entry
            # The signal's SL/TP were based on entry_min/entry_max, but market orders execute at different prices
            # This caused SL to be ABOVE entry for low-cap tokens, triggering instant stop-loss
            actual_stop_loss = round(order_price * 0.95, 8)  # Always 5% below actual fill
            actual_take_profit = round(order_price * 1.10, 8)  # Always 10% above actual fill
            
            # Validate: SL must be below entry, TP must be above entry
            if actual_stop_loss >= order_price or actual_take_profit <= order_price:
                logger.error(f"CRITICAL: Computed SL={actual_stop_loss:.8f} >= entry={order_price:.8f} or TP={actual_take_profit:.8f} <= entry. Position NOT saved.")
                session.close()
                return
            
            logger.info(f"📊 SL/TP recalculated for {signal.asset}: signal_entry={signal.entry_min:.6f}, actual_fill=${order_price:.6f}, SL=${actual_stop_loss:.6f} (-5.0%), TP=${actual_take_profit:.6f} (+10.0%)")

            position = TradePosition(
                symbol=f"{signal.asset}USDT",
                side=side,
                quantity=executed_qty,
                entry_price=order_price,
                stop_loss=actual_stop_loss,
                take_profit=actual_take_profit,
                order_id=str(order_result.get('orderId', '')),
                status='OPEN',
                opened_at=datetime.utcnow()
            )

            session.add(position)
            session.commit()
            # Access values before closing session
            quantity = position.quantity
            entry_price = position.entry_price
            asset = signal.asset
            session.close()

            logger.info(f"Saved position for {asset}: {quantity} at ${entry_price:.4f}, SL=${actual_stop_loss:.4f}, TP=${actual_take_profit:.4f}")

        except Exception as e:
            logger.error(f"Error saving position: {e}")

    def _update_position_status(self, position, order_result: Dict, status: str):
        """Update position status in database"""
        try:
            session = db_manager.get_session()

            db_position = session.query(TradePosition).filter(TradePosition.id == position.id).first()
            if db_position:
                db_position.status = status
                db_position.closed_at = datetime.utcnow()
                db_position.exit_price = float(order_result.get('price', 0)) if 'price' in order_result else None
                session.commit()
                logger.info(f"Updated position {db_position.symbol} to {status}")
            session.close()

        except Exception as e:
            logger.error(f"Error updating position status: {e}")

    def get_open_positions(self) -> List[TradePosition]:
        """Get all open positions"""
        try:
            session = db_manager.get_session()
            positions = session.query(TradePosition).filter(
                TradePosition.status == 'OPEN'
            ).all()
            session.close()
            return positions
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []

    def get_account_summary(self) -> Dict:
        """Get account summary"""
        try:
            balances = self.mexc_client.get_account_balance()
            positions = self.get_open_positions()

            return {
                'balances': balances,
                'open_positions': len(positions),
                'positions': [{
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'entry_price': p.entry_price,
                    'current_value': p.quantity * (balances.get(p.symbol.replace('USDT', ''), 0) if p.symbol.endswith('USDT') else 0)
                } for p in positions]
            }
        except Exception as e:
            logger.error(f"Error getting account summary: {e}")
            return {'error': str(e)}

    def _send_buy_notification(self, signal, order_result: Dict):
        """Send Telegram notification about successful buy order"""
        try:
            telegram_bot = self._get_telegram_bot()
            quantity = float(order_result.get('executedQty', 0) or 0)
            price = float(order_result.get('price', 0) or 0)
            total_usdt = float(order_result.get('cummulativeQuoteQty', 0) or 0)

            if total_usdt == 0 and price > 0:
                total_usdt = quantity * price

            stop_loss_pct = ((signal.stop_loss - signal.entry_min) / signal.entry_min) * 100 if signal.entry_min else 0
            take_profit_pct = ((signal.take_profit - signal.entry_max) / signal.entry_max) * 100 if signal.entry_max else 0

            message = f"""🟢 *ПОКУПКА ВЫПОЛНЕНА* 🟢

🎯 **{signal.asset}**
📊 Количество: {quantity:.6f}
💰 Цена входа: ${price:.4f}
💵 Общая сумма: ${total_usdt:.2f}

🎚️ Стоп-лосс: ${signal.stop_loss:.4f} ({stop_loss_pct:.1f}%)
🎯 Тейк-профит: ${signal.take_profit:.4f} (+{take_profit_pct:.1f}%)

💡 Обоснование: {signal.reasoning}
📈 AI Confidence: {signal.confidence:.1f}%
🤖 Автоматическая торговля MEXC"""

            telegram_bot.send_status_message(message)
            logger.info(f"Sent buy notification to Telegram for {signal.asset}")

        except Exception as e:
            logger.error(f"Error sending buy notification: {e}")

    def _send_sell_notification(self, position, order_result: Dict):
        """Send Telegram notification about successful sell order"""
        try:
            telegram_bot = self._get_telegram_bot()
            exit_price = float(order_result.get('price', 0))
            entry_price = position.entry_price
            quantity = position.quantity

            # Calculate P&L
            pnl = (exit_price - entry_price) * quantity
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100

            # Determine if it was stop loss or take profit
            reason = ""
            if exit_price <= position.stop_loss:
                reason = "🛑 СТОП-ЛОСС"
            elif exit_price >= position.take_profit:
                reason = "🎯 ТЕЙК-ПРОФИТ"
            else:
                reason = "📊 РУЧНАЯ ПРОДАЖА"

            emoji = "🟢" if pnl > 0 else "🔴"

            message = f"""{emoji} *ПРОДАЖА ВЫПОЛНЕНА* {emoji}

🎯 **{position.symbol.replace('USDT', '')}**
📊 Количество: {quantity:.6f}
💰 Цена входа: ${entry_price:.4f}
💸 Цена выхода: ${exit_price:.4f}

💵 P&L: ${pnl:.2f} ({pnl_percent:+.1f}%)

{reason}

🤖 Автоматическая торговля MEXC"""

            telegram_bot.send_status_message(message)
            logger.info(f"Sent sell notification to Telegram for {position.symbol}")

        except Exception as e:
            logger.error(f"Error sending sell notification: {e}")

    def _mark_signal_traded(self, signal):
        """Mark signal as traded to avoid re-trading"""
        try:
            session = db_manager.get_session()
            db_signal = session.query(AISignal).filter(AISignal.id == signal.id).first()
            if db_signal:
                db_signal.sent_to_telegram = True
                session.commit()
            session.close()
        except Exception as e:
            logger.error(f"Error marking signal as traded: {e}")

    def get_blocked_tokens(self) -> Dict:
        """Get list of blocked tokens"""
        return self._blocked_tokens.copy()

    def unblock_token(self, symbol: str) -> bool:
        """
        Remove token from blocked list.
        Returns True if token was unblocked.
        """
        if symbol in self._blocked_tokens:
            del self._blocked_tokens[symbol]
            logger.info(f"✅ Токен {symbol} разблокирован")
            return True
        return False

    def get_token_stats(self, symbol: str) -> Dict:
        """Get trading statistics for a specific token"""
        return self.analyze_token_trades(symbol)
