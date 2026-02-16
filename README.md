# Crypto Alpha AI Advisor

Сервис вероятностного анализа крипторынка с веб-интерфейсом, AI-анализом и отправкой сигналов в Telegram.

---

## ✅ Что делает проект
- Собирает данные с DEX (DexPaprika/DexScreener).
- Формирует AI-сигналы и сохраняет историю в БД.
- Показывает историю запросов и торговых позиций в веб-интерфейсе.
- Отправляет сигналы в Telegram.

---

## 🚀 Быстрый старт (локально)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# Заполните ключи в .env

python init_db.py
python run.py
```

После запуска веб-интерфейс доступен на:
`http://127.0.0.1:5000/`

Планировщик (Celery):
```bash
# В одном терминале
celery -A scheduler.tasks worker --loglevel=info

# Во втором терминале
celery -A scheduler.tasks beat --loglevel=info
```

---

## ⚙️ Настройки
Файл: `user_settings.json`

```json
{
  "analysis": {
    "collection_interval_minutes": 30,
    "min_signal_confidence": 0.65,
    "max_signals_per_day": 30,
    "min_risk_reward": 1.5,
    "include_memecoins": true
  },
  "data_collection": {
    "min_market_cap_usd": 100000,
    "min_token_price_usd": 0.001,
    "min_liquidity_usd": 1000,
    "stablecoins": "USDT,USDC,BUSD,DAI,USDP",
    "stablecoin_min_price": 0.1,
    "stablecoin_max_price": 10
  },
  "trading": {
    "enable_auto_trading": true,
    "trade_amount_usdt": 10,
    "min_take_profit_percent": 1,
    "unsupported_symbols": ["BTCUSDT", "ETHUSDT"]
  }
}
```

Интервал сбора данных берётся из `analysis.collection_interval_minutes`.

Веб-страница для настроек:
`http://127.0.0.1:5000/settings`

---

## 🐳 Docker
См. `README_DOCKER.md` для запуска через Docker Compose.