import logging
from datetime import datetime, timedelta
from sqlalchemy import func, case
from database.db_manager import db_manager
from database.models import AISignal, TradePosition

logger = logging.getLogger(__name__)


class HistoricalStatistics:
    """
    Модуль для расчёта реальной статистики сигналов и позиций из базы данных
    Используется перед генерацией новых сигналов для предоставления DeepSeek
    актуальной картины успешности прошлых событий
    """

    def __init__(self):
        self.session = db_manager.get_session()

    def get_summary_stats(self) -> dict:
        """Получить общую сводку статистики"""
        try:
            total_signals = self.session.query(AISignal).count()

            # Статистика закрытых позиций
            closed_positions = self.session.query(TradePosition).filter(
                TradePosition.status == 'CLOSED'
            ).all()

            total_closed = len(closed_positions)
            if total_closed == 0:
                return self._get_empty_stats()

            winning = 0
            losing = 0
            total_pnl = 0.0

            for pos in closed_positions:
                if pos.exit_price and pos.entry_price:
                    if pos.side == 'BUY':
                        pnl = (pos.exit_price - pos.entry_price) / pos.entry_price * 100
                    else:
                        pnl = (pos.entry_price - pos.exit_price) / pos.entry_price * 100

                    total_pnl += pnl
                    if pnl > 0:
                        winning += 1
                    else:
                        losing += 1

            win_rate = (winning / total_closed) * 100 if total_closed > 0 else 0
            avg_pnl = total_pnl / total_closed if total_closed > 0 else 0

            # Статистика за последние 7 дней
            week_ago = datetime.utcnow() - timedelta(days=7)
            week_positions = self.session.query(TradePosition).filter(
                TradePosition.status == 'CLOSED',
                TradePosition.closed_at >= week_ago
            ).count()

            return {
                'total_signals': total_signals,
                'total_closed_positions': total_closed,
                'winning_trades': winning,
                'losing_trades': losing,
                'win_rate_percent': round(win_rate, 1),
                'average_pnl_percent': round(avg_pnl, 2),
                'positions_last_7d': week_positions,
                'generated_at': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to calculate stats: {e}")
            return self._get_empty_stats()
        finally:
            self.session.close()

    def get_asset_stats(self, asset: str) -> dict:
        """Статистика по конкретному активу"""
        try:
            positions = self.session.query(TradePosition).filter(
                TradePosition.symbol == asset,
                TradePosition.status == 'CLOSED'
            ).all()

            if not positions:
                return {'count': 0, 'win_rate': 0, 'last_trade': None}

            wins = sum(1 for p in positions if
                       (p.side == 'BUY' and p.exit_price > p.entry_price) or
                       (p.side == 'SELL' and p.exit_price < p.entry_price))

            last = max(p.closed_at for p in positions) if positions else None

            return {
                'count': len(positions),
                'win_rate': round((wins / len(positions)) * 100, 1),
                'last_trade': last
            }

        except Exception as e:
            logger.error(f"Failed to get asset stats {asset}: {e}")
            return {'count': 0, 'win_rate': 0, 'last_trade': None}

    def get_all_assets_stats(self) -> list:
        """Получить статистику по всем активам у которых есть закрытые сделки"""
        try:
            # Получаем все уникальные символы из закрытых позиций
            symbols = self.session.query(TradePosition.symbol)\
                .filter(TradePosition.status == 'CLOSED')\
                .distinct()\
                .all()
            
            assets_stats = []
            for (symbol,) in symbols:
                stat = self.get_asset_stats(symbol)
                if stat['count'] >= 2:  # Только токены по которым было минимум 2 сделки
                    assets_stats.append({
                        'symbol': symbol.replace('USDT', ''),
                        'total_trades': stat['count'],
                        'win_rate': stat['win_rate']
                    })
            
            # Сортируем по количеству сделок по убыванию
            assets_stats.sort(key=lambda x: x['total_trades'], reverse=True)
            return assets_stats
            
        except Exception as e:
            logger.error(f"Failed to get all assets stats: {e}")
            return []

    def format_prompt_summary(self) -> str:
        """Форматировать статистику в вид для вставки в промпт DeepSeek"""
        stats = self.get_summary_stats()
        assets_stats = self.get_all_assets_stats()

        if stats['total_closed_positions'] == 0:
            return """⚠️ Ещё нет закрытых позиций для анализа статистики.

📋 ИНСТРУКЦИЯ ПО ТОРГОВЛЕ:
- Тейк-профит: +10% от цены входа
- Стоп-лосс: -5% от цены входа
- Торгуй агрессивнее и быстрее - фиксируй прибыль на 10%
- Выбирай только высококачественные сигналы с четкими паттернами"""

        emoji = "🔴" if stats['win_rate_percent'] < 30 else "🟡" if stats['win_rate_percent'] < 50 else "🟢"

        result = f"""
📊 РЕАЛЬНАЯ СТАТИСТИКА ИЗ БАЗЫ ДАННЫХ:
{emoji} ВСЕГО ЗАКРЫТЫХ СДЕЛОК: {stats['total_closed_positions']}
✅ УСПЕШНЫХ: {stats['winning_trades']} ({stats['win_rate_percent']}%)
❌ УБЫТОЧНЫХ: {stats['losing_trades']} ({100 - stats['win_rate_percent']}%)
📈 СРЕДНИЙ PNL НА СДЕЛКУ: {stats['average_pnl_percent']}%

📊 СТАТИСТИКА ПО ОТДЕЛЬНЫМ ТОКЕНАМ:
        """.strip()

        if assets_stats:
            result += "\n"
            for asset in assets_stats[:15]:  # Топ 15 самых торгуемых токенов
                asset_emoji = "✅" if asset['win_rate'] >= 50 else "❌"
                result += f"\n{asset_emoji} {asset['symbol']}: {asset['total_trades']} сделок, {asset['win_rate']}% успешных"

        result += f"""

📋 ИНСТРУКЦИЯ ПО ТОРГОВЛЕ:
- Тейк-профит: +10% от цены входа (фиксируй прибыль быстро!)
- Стоп-лосс: -5% от цены входа (режь убытки коротко)
- Торгуй агрессивнее - лучше взять 10% сейчас, чем ждать 50% и упустить

⚠️ КРИТИЧЕСКИ ВАЖНО:
Твой исторический винрейт всего {stats['win_rate_percent']}%. Это значит, что большинство прошлых сигналов были убыточными.

🎯 КАК УЛУЧШИТЬ РЕЗУЛЬТАТЫ:
1. Используй эту статистику чтобы ОТСЕИВАТЬ плохие паттерны, а не чтобы избегать торговли
2. Анализируй: какие токены показывали лучший винрейт? Ищи похожие паттерны сейчас
3. Избегай токены с винрейтом < 40% - они исторически убыточны
4. Отдавай предпочтение токенам с винрейтом > 50% - они показывают хорошую динамику
5. Генерируй сигналы ТОЛЬКО когда видишь четкий высококачественный паттерн
6. Не генерируй сигналы "на всякий случай" - только когда уверен на 80%+

💡 ПОМНИ: Лучше пропустить сомнительную возможность, чем войти и получить убыток.
        """

        return result

    def _get_empty_stats(self) -> dict:
        return {
            'total_signals': 0,
            'total_closed_positions': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate_percent': 0,
            'average_pnl_percent': 0,
            'positions_last_7d': 0,
            'generated_at': datetime.utcnow().isoformat()
        }


# Singleton instance (lazy initialized)
_historical_stats_instance = None

def historical_stats():
    global _historical_stats_instance
    if _historical_stats_instance is None:
        _historical_stats_instance = HistoricalStatistics()
    return _historical_stats_instance
