import os
import json
from dotenv import load_dotenv

load_dotenv()

# Load user settings from JSON file
USER_SETTINGS_FILE = 'user_settings.json'
user_settings = {}
if os.path.exists(USER_SETTINGS_FILE):
    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            user_settings = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load user settings: {e}")
        user_settings = {}

class Config:
    # Database
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 5432))
    DB_NAME = os.getenv('DB_NAME', 'crypto_alpha')
    DB_USER = os.getenv('DB_USER', 'crypto')
    DB_PASS = os.getenv('DB_PASS', 'crypto_pass')

    # For production, use PostgreSQL
    USE_SQLITE = os.getenv('USE_SQLITE', 'false').lower() == 'true'

    # API Keys
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
    DEEPSEEK_API_BASE = os.getenv('DEEPSEEK_API_BASE', 'https://api.deepseek.com/v1')
    DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')

    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

    # Analysis settings (from user_settings.json)
    @property
    def COLLECTION_INTERVAL_MINUTES(self):
        return user_settings.get('analysis', {}).get('collection_interval_minutes', 30)

    @property
    def MIN_SIGNAL_CONFIDENCE(self):
        return user_settings.get('analysis', {}).get('min_signal_confidence', 0.65)

    @property
    def MAX_SIGNALS_PER_DAY(self):
        return user_settings.get('analysis', {}).get('max_signals_per_day', 10)

    @property
    def INCLUDE_MEMECOINS(self):
        return user_settings.get('analysis', {}).get('include_memecoins', True)

    @property
    def MIN_RISK_REWARD(self):
        return user_settings.get('analysis', {}).get('min_risk_reward', 1.5)

    @property
    def TIMEZONE(self):
        return user_settings.get('analysis', {}).get('timezone', 'GMT+7')

    # Data collection settings (from user_settings.json)
    @property
    def MIN_MARKET_CAP_USD(self):
        return user_settings.get('data_collection', {}).get('min_market_cap_usd', 1000000)

    @property
    def MIN_TOKEN_PRICE_USD(self):
        return user_settings.get('data_collection', {}).get('min_token_price_usd', 0.001)

    @property
    def MIN_LIQUIDITY_USD(self):
        return user_settings.get('data_collection', {}).get('min_liquidity_usd', 1000)

    @property
    def STABLECOINS(self):
        stablecoins_str = user_settings.get('data_collection', {}).get('stablecoins', 'USDT,USDC,BUSD,DAI,USDP')
        return stablecoins_str.split(',')

    @property
    def STABLECOIN_MIN_PRICE(self):
        return user_settings.get('data_collection', {}).get('stablecoin_min_price', 0.1)

    @property
    def STABLECOIN_MAX_PRICE(self):
        return user_settings.get('data_collection', {}).get('stablecoin_max_price', 10.0)

    # Trading settings (from user_settings.json)
    @property
    def ENABLE_AUTO_TRADING(self):
        return user_settings.get('trading', {}).get('enable_auto_trading', False)

    @property
    def TRADE_AMOUNT_USDT(self):
        return user_settings.get('trading', {}).get('trade_amount_usdt', 10.0)

    @property
    def MIN_TAKE_PROFIT_PERCENT(self):
        return user_settings.get('trading', {}).get('min_take_profit_percent', 1.0)

    @property
    def UNSUPPORTED_SYMBOLS(self):
        symbols = user_settings.get('trading', {}).get('unsupported_symbols', [])
        if isinstance(symbols, str):
            symbols = [s.strip().upper() for s in symbols.split(',') if s.strip()]
        return [s.upper() for s in symbols]

    def add_unsupported_symbol(self, symbol: str) -> bool:
        if not symbol:
            return False
        symbols = self.UNSUPPORTED_SYMBOLS
        symbol = symbol.upper()
        if symbol not in symbols:
            symbols.append(symbol)
            new_settings = {
                'trading': {
                    **user_settings.get('trading', {}),
                    'unsupported_symbols': symbols
                }
            }
            return self.save_user_settings(new_settings)
        return True

    # MEXC Trading API (from .env)
    MEXC_API_KEY = os.getenv('MEXC_API_KEY')
    MEXC_SECRET_KEY = os.getenv('MEXC_SECRET_KEY')
    MEXC_BASE_URL = os.getenv('MEXC_BASE_URL', 'https://api.mexc.com')

    @property
    def DATABASE_URL(self):
        # For development/testing, use SQLite if configured
        if self.USE_SQLITE:
            return "sqlite:///crypto_alpha.db"
        return f"postgresql://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @staticmethod
    def save_user_settings(new_settings: dict):
        """Save user settings to JSON file"""
        global user_settings
        user_settings.update(new_settings)
        try:
            with open(USER_SETTINGS_FILE, 'w') as f:
                json.dump(user_settings, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving user settings: {e}")
            return False

    def get_all_user_settings(self):
        """Get all user settings"""
        return user_settings
