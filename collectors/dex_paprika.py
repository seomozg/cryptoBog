import requests
import logging
from datetime import datetime
from typing import List, Dict, Any
from database.db_manager import db_manager
from database.models import TokenMetadata, PriceSnapshot, TradeActivity
from config.settings import Config

logger = logging.getLogger(__name__)

class DexPaprikaCollector:
    """Collector for DexScreener API data"""

    BASE_URL = "https://api.dexscreener.com"

    def __init__(self):
        self.session = requests.Session()
        self.config = Config()

    def get_trending_tokens(self, network: str = "ethereum", limit: int = 100) -> List[Dict]:
        """Get major tokens by searching for well-known symbols"""
        try:
            # Search for major tokens instead of "trending"
            major_tokens = [
                "ETH", "BTC", "SOL", "MATIC", "AVAX", "LINK", "UNI", "AAVE",
                "USDC", "USDT", "WBTC", "WETH", "BNB", "ADA", "DOT", "LTC",
                "ALGO", "VET", "ICP", "FIL", "TRX", "ETC", "XLM", "THETA",
                "FTM", "HBAR", "NEAR", "FLOW", "MANA", "SAND", "AXS", "ENJ"
            ]

            all_tokens = []
            seen_addresses = set()

            for symbol in major_tokens:
                try:
                    url = f"{self.BASE_URL}/latest/dex/search"
                    params = {"q": symbol, "chainId": network, "limit": 10}
                    response = self.session.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()

                    for pair in data.get("pairs", [])[:3]:  # Take first 3 pairs per symbol
                        base_token = pair.get("baseToken", {})
                        token_address = base_token.get("address", "")

                        # Skip if already processed this token
                        if token_address in seen_addresses:
                            continue
                        seen_addresses.add(token_address)

                        # Skip if no data
                        if not token_address or not base_token.get("symbol"):
                            continue

                        # Get market cap
                        market_cap = pair.get("marketCap", 0) or pair.get("fdv", 0) or 0

                        price_usd = float(pair.get("priceUsd", 0) or 0)

                        # Skip stablecoins with wrong prices
                        if symbol in self.config.STABLECOINS and (price_usd < self.config.STABLECOIN_MIN_PRICE or price_usd > self.config.STABLECOIN_MAX_PRICE):
                            continue

                        # Skip tokens with extremely low prices
                        if price_usd < self.config.MIN_TOKEN_PRICE_USD:
                            continue

                        token_data = {
                            "token_address": token_address,
                            "symbol": symbol,
                            "name": base_token.get("name", ""),
                            "price_usd": price_usd,
                            "liquidity_usd": pair.get("liquidity", {}).get("usd", 0),
                            "volume_24h": pair.get("volume", {}).get("h24", 0),
                            "buys_24h": pair.get("txns", {}).get("h24", {}).get("buys", 0),
                            "sells_24h": pair.get("txns", {}).get("h24", {}).get("sells", 0),
                            "buys_1h": pair.get("txns", {}).get("h1", {}).get("buys", 0),
                            "sells_1h": pair.get("txns", {}).get("h1", {}).get("sells", 0),
                            "txns_24h": pair.get("txns", {}).get("h24", {}).get("buys", 0) + pair.get("txns", {}).get("h24", {}).get("sells", 0),
                            "txns_1h": pair.get("txns", {}).get("h1", {}).get("buys", 0) + pair.get("txns", {}).get("h1", {}).get("sells", 0),
                            "volume_1h": pair.get("volume", {}).get("h1", 0),
                            "market_cap_usd": market_cap,
                            "fdv_usd": pair.get("fdv", 0)
                        }

                        all_tokens.append(token_data)

                        # Stop when we have enough tokens
                        if len(all_tokens) >= limit:
                            break

                    if len(all_tokens) >= limit:
                        break

                except Exception as e:
                    logger.warning(f"Failed to search for {symbol}: {e}")
                    continue

            logger.info(f"Collected {len(all_tokens)} major tokens from DexScreener")
            return all_tokens

        except requests.RequestException as e:
            logger.error(f"Failed to get trending tokens: {e}")
            return []

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

    def collect_for_analysis(self, network: str = "ethereum", limit: int = 30) -> List[Dict[str, Any]]:
        """
        Collect data for analysis from DexScreener
        Returns list of token data with metrics
        """
        collected_data = []
        trending_tokens = self.get_trending_tokens(network, limit * 3)  # Get more to filter

        if not trending_tokens:
            logger.error("Failed to collect trending tokens from API - no data available")
            return []

        logger.info(f"Retrieved {len(trending_tokens)} tokens from API, filtering for valid data...")

        for token_info in trending_tokens:
            token_address = token_info.get('token_address')
            if not token_address:
                continue

            # Validate data - skip tokens with invalid prices
            price_usd = token_info.get('price_usd', 0)
            symbol = token_info.get('symbol', '').upper()

            # Skip known stablecoins with wrong prices
            if symbol in self.config.STABLECOINS and (price_usd < self.config.STABLECOIN_MIN_PRICE or price_usd > self.config.STABLECOIN_MAX_PRICE):
                logger.debug(f"Skipping {symbol} - invalid stablecoin price: {price_usd}")
                continue

            # Skip tokens with extremely low prices (likely micro-cap or scam tokens)
            if price_usd < self.config.MIN_TOKEN_PRICE_USD:
                logger.debug(f"Skipping {symbol} - price too low: {price_usd}")
                continue

            # Skip tokens with no price or invalid price
            if not price_usd or price_usd <= 0:
                logger.debug(f"Skipping {symbol} - invalid price: {price_usd}")
                continue

            # Skip tokens with no liquidity
            liquidity_usd = token_info.get('liquidity_usd', 0)
            if not liquidity_usd or liquidity_usd < self.config.MIN_LIQUIDITY_USD:
                logger.debug(f"Skipping {symbol} - low liquidity: {liquidity_usd}")
                continue

            # Log valid token data
            logger.info(f"✓ Valid token: {token_info.get('symbol', 'UNKNOWN')} - Price: ${price_usd:.6f}, Liquidity: ${liquidity_usd:,.0f}")

            # Use data directly from trending tokens
            data = {
                'network': network,
                'token_address': token_address,
                'symbol': token_info.get('symbol', ''),
                'name': token_info.get('name', ''),
                'price_usd': price_usd,
                'liquidity_usd': liquidity_usd,
                'volume_24h': token_info.get('volume_24h', 0),
                'fdv_usd': token_info.get('fdv_usd', 0),
                'market_cap_usd': token_info.get('market_cap_usd', 0),
                'buys_1h': token_info.get('buys_1h', 0),
                'sells_1h': token_info.get('sells_1h', 0),
                'buys_24h': token_info.get('buys_24h', 0),
                'sells_24h': token_info.get('sells_24h', 0),
                'txns_1h': token_info.get('txns_1h', 0),
                'txns_24h': token_info.get('txns_24h', 0),
                'volume_1h': token_info.get('volume_1h', 0)
            }

            collected_data.append(data)

            # Save to database
            self._save_to_database(data)

            # Stop when we have enough valid tokens
            if len(collected_data) >= limit:
                break

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