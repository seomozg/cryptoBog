import json
import requests
import logging
import time
from datetime import datetime
from typing import Dict, List, Any
from config.settings import Config
from analyzers.historical_stats import historical_stats

logger = logging.getLogger(__name__)

class DeepSeekAnalyzer:
    """Adapter for sending data to DeepSeek API and receiving signals"""

    def __init__(self):
        self.config = Config()
        self.api_key = self.config.DEEPSEEK_API_KEY
        self.api_base = self.config.DEEPSEEK_API_BASE
        self.model = self.config.DEEPSEEK_MODEL
        self.log_dir = 'logs'

    def _write_deepseek_log(self, batch_size: int, prompt: str, response_content: str, signals_count: int):
        """Универсальный метод логирования запросов DeepSeek - работает локально и в докере"""
        try:
            log_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'batch_size': batch_size,
                'prompt_sent': prompt,
                'raw_response': response_content,
                'signals_count': signals_count
            }

            import os
            os.makedirs(self.log_dir, exist_ok=True)

            log_filename = f'deepseek_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json'
            log_file = os.path.join(self.log_dir, log_filename)

            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            logger.info(f"✅ ЛОГ ЗАПИСАН: {log_filename}")

        except Exception as log_error:
            logger.warning(f"⚠️ НЕ КРИТИЧЕСКАЯ ОШИБКА ЗАПИСИ ЛОГА: {str(log_error)}")
            # ❗️ НЕ ВЫБРАСЫВАЕМ ИСКЛЮЧЕНИЕ! Лог не важнее реальных данных

    def analyze_market_data(self, market_data: List[Dict], news_summary: str) -> Dict:
        """
        Send collected market data to DeepSeek and get trading signals
        """
        if not self.api_key:
            logger.error("DeepSeek API key not configured")
            raise ValueError("DeepSeek API key is required for analysis")

        system_prompt = """You are a crypto trading analyst specializing in short-term swing trades on altcoins.

Your task: analyze the provided on-chain data including PRICE TRENDS (5m, 1h, 6h, 24h changes), trading activity, and liquidity:
1. Determine the current market phase (early bull, late bull, bear, consolidation)
2. Return ONLY 0-3 HIGHEST-QUALITY signals — quality over quantity. If no strong setups exist, return empty array.
3. For each selected asset provide:
   - Specific DIP entry price (below current price — we buy dips, not highs!)
   - Stop-loss: 5% below entry (entry * 0.95)
   - Take-profit: 10% above entry (entry * 1.10)
   - Probability: your estimate of success chance (50-90%)
   - Confidence: your REAL certainty in this signal reaching TP (75-90%). Only give 80+ if pattern is clear.
   - Risk/reward ratio (should be ~2.0)
   - Historical analog (similar pattern from past)
   - Brief reasoning in RUSSIAN LANGUAGE

CRITICAL RULES:
- confidence MUST reflect your genuine belief in a 10%+ move. If unsure, confidence < 75.
- Look for: price dropping (-5% to -15% in 6h/24h) but buying pressure increasing (buys > sells) = reversal signal
- Avoid: tokens pumping (+20%+ in 24h), selling pressure dominating, low liquidity
- Empty signals array is BETTER than weak signals. Only signal when you see a clear pattern.

IMPORTANT: You NEVER suggest buying at current highs. You specify DIP entry prices.
REASONING MUST BE IN RUSSIAN. All other fields remain in English.
Format response as strict JSON."""

        max_retries = 3
        retry_delay = 5  # seconds
        timeout = 120  # increased from 30 to 120 seconds

        try:
            batch_size = 20  # Smaller batch for better analysis quality
            signals: List[Dict[str, Any]] = []
            market_phase = "unknown"

            # Получаем актуальную статистику из базы данных
            stats_summary = historical_stats().format_prompt_summary()
            
            for batch_start in range(0, len(market_data), batch_size):
                batch = market_data[batch_start:batch_start + batch_size]
                user_prompt = f"""
=== ИСТОРИЧЕСКАЯ СТАТИСТИКА ИЗ БД ===
{stats_summary}

=== MARKET DATA ===
{json.dumps(batch, indent=2, default=str)}

=== NEWS SUMMARY ===
{news_summary}

=== REQUEST ===
Return JSON. Return 0-3 signals MAX. Empty array if no strong setups. Quality > quantity.
{{
  "market_phase": "bull/bear/consolidation",
  "signals": [
    {{
      "asset": "ETH",
      "action": "BUY_ON_DIP",
      "entry_min": 3000.0,
      "entry_max": 3100.0,
      "stop_loss": 2850.0,
      "take_profit": 3410.0,
      "probability": 75.0,
      "confidence": 85.0,
      "risk_reward": 2.0,
      "historical_analog": "March 2024 recovery",
      "reasoning": "Brief explanation IN RUSSIAN"
    }}
  ]
}}
"""

                # Retry logic for API calls
                last_error = None
                for attempt in range(max_retries):
                    try:
                        logger.info(f"DeepSeek API call attempt {attempt + 1}/{max_retries}")
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
                            timeout=timeout
                        )

                        response.raise_for_status()
                        result = response.json()
                        content = result["choices"][0]["message"]["content"]
                        batch_result = json.loads(content)
                        market_phase = batch_result.get("market_phase", market_phase)
                        signals.extend(batch_result.get("signals", []))
                        logger.info(f"DeepSeek API call successful, got {len(batch_result.get('signals', []))} signals")
                        
                        # ✅ Логирование полного запроса и ответа DeepSeek
                        self._write_deepseek_log(
                            batch_size=len(batch),
                            prompt=user_prompt,
                            response_content=content,
                            signals_count=len(batch_result.get('signals', []))
                        )
                        break  # Success, exit retry loop

                    except requests.exceptions.Timeout as te:
                        last_error = te
                        logger.warning(f"DeepSeek API timeout on attempt {attempt + 1}/{max_retries}: {te}")
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            logger.error("All retry attempts failed due to timeout")
                            raise

                    except requests.exceptions.RequestException as re:
                        last_error = re
                        logger.warning(f"DeepSeek API error on attempt {attempt + 1}/{max_retries}: {re}")
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            logger.error("All retry attempts failed")
                            raise

            return {
                "market_phase": market_phase,
                "signals": signals
            }

        except Exception as e:
            logger.error(f"DeepSeek API error after all retries: {e}")
            return self.analyze_with_mock(market_data, news_summary)

    def analyze_with_mock(self, market_data: List[Dict], news_summary: str) -> Dict:
        """Mock analysis for testing without API key"""
        logger.info("Using mock analysis (no DeepSeek API)")

        # ✅ Логирование и для тестового режима
        self._write_deepseek_log(
            batch_size=len(market_data),
            prompt='MOCK MODE',
            response_content='MOCK RESPONSE',
            signals_count=2
        )

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
