import json
import requests
import logging
from datetime import datetime
from typing import Dict, List, Any
from config.settings import Config

logger = logging.getLogger(__name__)

class DeepSeekAnalyzer:
    """Adapter for sending data to DeepSeek API and receiving signals"""

    def __init__(self):
        self.config = Config()
        self.api_key = self.config.DEEPSEEK_API_KEY
        self.api_base = self.config.DEEPSEEK_API_BASE
        self.model = self.config.DEEPSEEK_MODEL

    def analyze_market_data(self, market_data: List[Dict], news_summary: str) -> Dict:
        """
        Send collected market data to DeepSeek and get trading signals
        """
        if not self.api_key:
            logger.error("DeepSeek API key not configured")
            raise ValueError("DeepSeek API key is required for analysis")

        system_prompt = """You are a probabilistic crypto analyst with access to historical patterns from 2019-2026.

Your task: based on provided on-chain data, trading activity, and news:
1. Determine the current market phase (early bull, late bull, bear, consolidation)
2. Identify top 3 most promising assets for BUY ON DIP (not on highs!)
3. For each asset provide:
   - Specific entry price range (min-max)
   - Stop-loss (in $ and %)
   - Take-profit (in $ and %)
   - Success probability (0-100%)
   - Confidence in signal (0-100%)
   - Risk/reward ratio
   - Historical analog (specific period)
   - Brief reasoning in RUSSIAN LANGUAGE

IMPORTANT: You NEVER suggest buying at current highs. You specify DIP entry prices.
REASONING MUST BE IN RUSSIAN. All other fields remain in English.
Format response as strict JSON."""

        user_prompt = f"""
=== MARKET DATA ===
{json.dumps(market_data[:20], indent=2, default=str)[:3000]}...(truncated)

=== NEWS SUMMARY ===
{news_summary}

=== REQUEST ===
Return JSON in format:
{{
  "market_phase": "bull/bear/consolidation",
  "signals": [
    {{
      "asset": "BTC",
      "action": "BUY_ON_DIP",
      "entry_min": 60000.0,
      "entry_max": 61000.0,
      "stop_loss": 58000.0,
      "take_profit": 67000.0,
      "probability": 75.0,
      "confidence": 80.0,
      "risk_reward": 2.1,
      "historical_analog": "January 2024, pre-ETF",
      "reasoning": "Brief explanation"
    }}
  ]
}}
"""

        try:
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"}
                },
                timeout=30
            )

            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            return json.loads(content)

        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            return self.analyze_with_mock(market_data, news_summary)

    def analyze_with_mock(self, market_data: List[Dict], news_summary: str) -> Dict:
        """Mock analysis for testing without API key"""
        logger.info("Using mock analysis (no DeepSeek API)")

        return {
            "market_phase": "early altseason",
            "signals": [
                {
                    "asset": "ETH",
                    "action": "BUY_ON_DIP",
                    "entry_min": 3450.0,
                    "entry_max": 3550.0,
                    "stop_loss": 3300.0,
                    "take_profit": 4000.0,
                    "probability": 72.0,
                    "confidence": 78.0,
                    "risk_reward": 2.0,
                    "historical_analog": "March 2024, pre-ETF hype",
                    "reasoning": "ETH обновляет ATH на ожиданиях ETF, активность L2 растет, киты накапливают"
                },
                {
                    "asset": "RENDER",
                    "action": "BUY_ON_DIP",
                    "entry_min": 8.2,
                    "entry_max": 8.6,
                    "stop_loss": 7.5,
                    "take_profit": 11.0,
                    "probability": 68.0,
                    "confidence": 65.0,
                    "risk_reward": 2.4,
                    "historical_analog": "February 2024, AI season",
                    "reasoning": "AI нарратив возвращается, объемы растут, сильная поддержка"
                }
            ]
        }
