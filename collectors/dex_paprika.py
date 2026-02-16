import requests
import logging
import time
from datetime import datetime
from typing import List, Dict, Any
from database.db_manager import db_manager
from database.models import TokenMetadata, PriceSnapshot, TradeActivity
from config.settings import Config
from trading.mexc_client import MEXCClient

logger = logging.getLogger(__name__)

class DexPaprikaCollector:
    """Collector for DexScreener API data"""

    BASE_URL = "https://api.dexscreener.com"

    def __init__(self):
        self.session = requests.Session()
        self.config = Config()

    def get_latest_token_profiles(self) -> List[Dict[str, Any]]:
        """Get latest token profiles from DexScreener."""
        try:
            url = f"{self.BASE_URL}/token-profiles/latest/v1"
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        except requests.RequestException as e:
            logger.error(f"Failed to get latest token profiles: {e}")
            return []

    def get_token_pairs(self, chain_id: str, token_address: str) -> List[Dict[str, Any]]:
        """Get pools for a token address."""
        try:
            url = f"{self.BASE_URL}/token-pairs/v1/{chain_id}/{token_address}"
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        except requests.RequestException as e:
            logger.error(f"Failed to get token pairs for {token_address}: {e}")
            return []

    def _select_best_pair(self, pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not pairs:
            return {}
        return max(pairs, key=lambda pair: pair.get("liquidity", {}).get("usd", 0) or 0)

    def get_token_details(self, network: str, token_address: str) -> Dict:
        """Get detailed token information"""
        try:
            url = f"{self.BASE_URL}/v1/tokens/{network}/{token_address}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get token details for {token_address}: {e}")
            return {}

    def collect_for_analysis(self, network: str = "ethereum", limit: int | None = None, persist: bool = True) -> List[Dict[str, Any]]:
        """
        Collect data for analysis from DexScreener
        Returns list of token data with metrics
        """
        collected_data = []
        seen_addresses = set()

        mexc_client = MEXCClient()
        mexc_symbols = mexc_client.get_exchange_symbols("USDT")
        base_symbols = [s.get("baseAsset") for s in (mexc_symbols or []) if s.get("baseAsset")]

        if not base_symbols:
            logger.error("Failed to collect MEXC symbols - no data available")
            return []

        logger.info(f"Retrieved {len(base_symbols)} MEXC base symbols, searching DexScreener...")

        for symbol in base_symbols:
            if len(symbol) < 2:
                continue
            try:
                search_url = f"{self.BASE_URL}/latest/dex/search"
                response = self.session.get(search_url, params={"q": symbol, "chainId": network}, timeout=10)
                response.raise_for_status()
                search_data = response.json()
            except requests.RequestException as e:
                logger.warning(f"Failed to search DexScreener for {symbol}: {e}")
                continue

            pairs = search_data.get("pairs", []) if isinstance(search_data, dict) else []
            if not pairs:
                continue

            best_pair = self._select_best_pair(pairs)
            if not best_pair:
                continue

            token_address = best_pair.get('baseToken', {}).get('address')
            if not token_address:
                continue
            if token_address in seen_addresses:
                continue

            base_token = best_pair.get('baseToken', {})
            price_usd = float(best_pair.get('priceUsd', 0) or 0)
            liquidity_usd = best_pair.get('liquidity', {}).get('usd', 0) or 0

            if price_usd < self.config.MIN_TOKEN_PRICE_USD:
                continue
            if liquidity_usd < self.config.MIN_LIQUIDITY_USD:
                continue

            data = {
                'network': network,
                'token_address': token_address,
                'symbol': base_token.get('symbol', '').upper(),
                'name': base_token.get('name', ''),
                'price_usd': price_usd,
                'liquidity_usd': liquidity_usd,
                'volume_24h': best_pair.get('volume', {}).get('h24', 0),
                'fdv_usd': best_pair.get('fdv', 0),
                'market_cap_usd': best_pair.get('marketCap', 0),
                'buys_1h': best_pair.get('txns', {}).get('h1', {}).get('buys', 0),
                'sells_1h': best_pair.get('txns', {}).get('h1', {}).get('sells', 0),
                'buys_24h': best_pair.get('txns', {}).get('h24', {}).get('buys', 0),
                'sells_24h': best_pair.get('txns', {}).get('h24', {}).get('sells', 0),
                'txns_1h': best_pair.get('txns', {}).get('h1', {}).get('buys', 0) + best_pair.get('txns', {}).get('h1', {}).get('sells', 0),
                'txns_24h': best_pair.get('txns', {}).get('h24', {}).get('buys', 0) + best_pair.get('txns', {}).get('h24', {}).get('sells', 0),
                'volume_1h': best_pair.get('volume', {}).get('h1', 0)
            }

            seen_addresses.add(token_address)
            collected_data.append(data)
            if persist:
                self._save_to_database(data)

            if limit and len(collected_data) >= limit:
                break

            time.sleep(0.15)

        if len(collected_data) == 0:
            logger.error("No valid tokens found after filtering - check API response or network connectivity")
        else:
            logger.info(f"Successfully collected data for {len(collected_data)} valid tokens")

        return collected_data

    def _get_mock_tokens(self, limit: int) -> List[Dict]:
        """Generate mock token data for testing"""
        import random
        mock_tokens = [
            {
                'token_address': '0xa0b86a33e6c0c1ba7c46c1e0b1a3c1e0b1a3c1e0',
                'symbol': 'ETH',
                'name': 'Ethereum',
                'price_usd': 3500 + random.uniform(-100, 100),
                'liquidity_usd': 50000000,
                'volume_24h': 25000000,
                'fdv_usd': 420000000000,
                'market_cap_usd': 420000000000,
                'buys_1h': random.randint(1000, 2000),
                'sells_1h': random.randint(800, 1500),
                'buys_24h': random.randint(5000, 10000),
                'sells_24h': random.randint(4000, 8000),
                'txns_1h': random.randint(2000, 4000),
                'txns_24h': random.randint(10000, 20000),
                'volume_1h': random.uniform(1000000, 5000000)
            },
            {
                'token_address': '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',
                'symbol': 'WBTC',
                'name': 'Wrapped Bitcoin',
                'price_usd': 95000 + random.uniform(-2000, 2000),
                'liquidity_usd': 30000000,
                'volume_24h': 15000000,
                'fdv_usd': 1900000000000,
                'market_cap_usd': 1900000000000,
                'buys_1h': random.randint(500, 1000),
                'sells_1h': random.randint(400, 800),
                'buys_24h': random.randint(2500, 5000),
                'sells_24h': random.randint(2000, 4000),
                'txns_1h': random.randint(1000, 2000),
                'txns_24h': random.randint(5000, 10000),
                'volume_1h': random.uniform(500000, 2000000)
            },
            {
                'token_address': '0x6b175474e89094c44da98b954eedeac495271d0f',
                'symbol': 'USDC',
                'name': 'USD Coin',
                'price_usd': 1.0 + random.uniform(-0.01, 0.01),
                'liquidity_usd': 100000000,
                'volume_24h': 50000000,
                'fdv_usd': 35000000000,
                'market_cap_usd': 35000000000,
                'buys_1h': random.randint(5000, 10000),
                'sells_1h': random.randint(4500, 9500),
                'buys_24h': random.randint(25000, 50000),
                'sells_24h': random.randint(22500, 47500),
                'txns_1h': random.randint(10000, 20000),
                'txns_24h': random.randint(50000, 100000),
                'volume_1h': random.uniform(5000000, 20000000)
            }
        ]
        return mock_tokens[:limit]

    def _save_to_database(self, data: Dict[str, Any]):
        """Save collected data to database"""
        try:
            session = db_manager.get_session()

            # Get or create token metadata
            token = session.query(TokenMetadata).filter_by(
                network=data['network'],
                token_address=data['token_address']
            ).first()

            if not token:
                token = TokenMetadata(
                    network=data['network'],
                    token_address=data['token_address'],
                    symbol=data['symbol'],
                    name=data['name']
                )
                session.add(token)
                session.commit()

            # Save price snapshot
            price_snapshot = PriceSnapshot(
                time=datetime.utcnow(),
                token_id=token.id,
                price_usd=data['price_usd'],
                liquidity_usd=data['liquidity_usd'],
                volume_24h=data['volume_24h'],
                fdv_usd=data['fdv_usd'],
                market_cap_usd=data['market_cap_usd']
            )
            session.add(price_snapshot)

            # Save trade activity
            trade_activity = TradeActivity(
                time=datetime.utcnow(),
                token_id=token.id,
                buys_1h=data['buys_1h'],
                sells_1h=data['sells_1h'],
                buys_24h=data['buys_24h'],
                sells_24h=data['sells_24h'],
                txns_1h=data['txns_1h'],
                txns_24h=data['txns_24h'],
                volume_1h=data['volume_1h']
            )
            session.add(trade_activity)

            session.commit()
            session.close()

        except Exception as e:
            logger.error(f"Failed to save data to database: {e}")