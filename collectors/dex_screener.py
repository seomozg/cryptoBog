import requests
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class DexScreenerCollector:
    """Collector for DexScreener API data"""

    BASE_URL = "https://api.dexscreener.com"

    def __init__(self):
        self.session = requests.Session()

    def get_trending_pairs(self, chain_id: str = "ethereum", limit: int = 30) -> List[Dict]:
        """Get trending pairs from DexScreener"""
        try:
            url = f"{self.BASE_URL}/latest/dex/tokens"
            params = {"chainId": chain_id, "limit": limit}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('pairs', [])
        except requests.RequestException as e:
            logger.error(f"Failed to get trending pairs: {e}")
            return []

    def get_pair_details(self, pair_address: str) -> Dict:
        """Get detailed pair information"""
        try:
            url = f"{self.BASE_URL}/latest/dex/pairs/{pair_address}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get pair details for {pair_address}: {e}")
            return {}

    def collect_new_pairs(self, chain_id: str = "ethereum", limit: int = 30) -> List[Dict[str, Any]]:
        """
        Collect new pairs data for analysis
        """
        collected_data = []
        trending_pairs = self.get_trending_pairs(chain_id, limit)

        for pair in trending_pairs:
            pair_address = pair.get('pairAddress')
            if not pair_address:
                continue

            details = self.get_pair_details(pair_address)
            if not details:
                continue

            # Extract relevant data
            data = {
                'chain_id': chain_id,
                'pair_address': pair_address,
                'base_token': details.get('baseToken', {}),
                'quote_token': details.get('quoteToken', {}),
                'price_usd': details.get('priceUsd', 0),
                'liquidity_usd': details.get('liquidity', {}).get('usd', 0),
                'volume_24h': details.get('volume', {}).get('h24', 0),
                'txns_24h': details.get('txns', {}).get('h24', 0),
                'created_at': details.get('pairCreatedAt', 0)
            }

            collected_data.append(data)

        logger.info(f"Collected data for {len(collected_data)} pairs from DexScreener")
        return collected_data