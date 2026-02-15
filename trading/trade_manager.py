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

    def _get_telegram_bot(self):
        """Lazy initialization of Telegram bot"""
        if self.telegram_bot is None:
            from telegram.bot import TelegramBot
            self.telegram_bot = TelegramBot()
        return self.telegram_bot

    def execute_signal_buy(self, signal) -> bool:
        """Execute buy order for trading signal"""
        if not self.config.ENABLE_AUTO_TRADING:
            logger.info("Auto trading disabled, skipping buy order")
            return False

        try:
            # Convert symbol to MEXC format (add USDT)
            symbol = f"{signal.asset}USDT"

            if symbol in self.config.UNSUPPORTED_SYMBOLS:
                logger.warning(f"Skipping unsupported symbol for API trading: {symbol}")
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
                # If symbol is not supported by API, mark as traded and persist unsupported symbol
                if order_result.get('code') == 10007:
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
        """Check if position should be sold based on stop loss or take profit"""
        try:
            symbol = position.symbol.replace('USDT', '')  # Remove USDT suffix
            current_price = current_prices.get(symbol)

            if not current_price:
                return False

            entry_price = position.entry_price
            stop_loss = position.stop_loss
            take_profit = position.take_profit

            # Check stop loss (sell if price drops below stop loss)
            if current_price <= stop_loss:
                logger.info(f"Stop loss triggered for {position.symbol}: current ${current_price:.4f} <= stop ${stop_loss:.4f}")
                return True

            # Check take profit (sell if price reaches take profit)
            if current_price >= take_profit:
                logger.info(f"Take profit triggered for {position.symbol}: current ${current_price:.4f} >= target ${take_profit:.4f}")
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
        """Save trade position to database"""
        try:
            session = db_manager.get_session()

            executed_qty = float(order_result.get('executedQty', 0) or 0)
            total_usdt = float(order_result.get('cummulativeQuoteQty', 0) or 0)
            order_price = float(order_result.get('price', 0) or 0)
            if order_price == 0 and executed_qty > 0 and total_usdt > 0:
                order_price = total_usdt / executed_qty
            if order_price == 0:
                order_price = signal.entry_min

            position = TradePosition(
                symbol=f"{signal.asset}USDT",
                side=side,
                quantity=executed_qty,
                entry_price=order_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
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

            logger.info(f"Saved position for {asset}: {quantity} at ${entry_price:.4f}")

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
