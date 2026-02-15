#!/usr/bin/env python3
"""
MEXC API client for automated trading
"""

import logging
import time
import hmac
import hashlib
import requests
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode
from config.settings import Config

logger = logging.getLogger(__name__)

class MEXCClient:
    """MEXC API client for spot trading"""

    def __init__(self):
        self.config = Config()
        self.api_key = self.config.MEXC_API_KEY
        self.secret_key = self.config.MEXC_SECRET_KEY
        self.base_url = self.config.MEXC_BASE_URL
        self.session = requests.Session()

        if not self.api_key or not self.secret_key:
            logger.warning("MEXC API keys not configured")

    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature"""
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _make_request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False) -> Dict:
        """Make API request"""
        url = f"{self.base_url}{endpoint}"

        if params is None:
            params = {}

        headers = {
            'X-MEXC-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }

        if signed:
            timestamp = str(int(time.time() * 1000))
            params['timestamp'] = timestamp

            # Build query string in the order parameters are added
            query_string = urlencode(params)
            params['signature'] = self._generate_signature(query_string)

        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, headers=headers)
            elif method.upper() == 'POST':
                response = self.session.post(url, params=params, headers=headers)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, params=params, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            response_text = None
            response_data = None
            if hasattr(e, 'response') and e.response is not None:
                try:
                    response_text = e.response.text
                    response_data = e.response.json()
                except Exception:
                    response_text = "<unable to read response body>"
            logger.error(f"MEXC API request failed: {e}. Response body: {response_text}")
            if isinstance(response_data, dict):
                return {
                    'error': response_data.get('msg', str(e)),
                    'code': response_data.get('code')
                }
            return {'error': str(e)}

    def get_account_info(self) -> Dict:
        """Get account information"""
        return self._make_request('GET', '/api/v3/account', signed=True)

    def get_symbol_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol"""
        try:
            data = self._make_request('GET', '/api/v3/ticker/price', {'symbol': symbol})
            if data and 'price' in data:
                return float(data['price'])
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
        return None

    def get_symbol_info(self, symbol: str) -> Dict:
        """Get symbol information"""
        try:
            data = self._make_request('GET', '/api/v3/exchangeInfo')
            if data and 'symbols' in data:
                for symbol_info in data['symbols']:
                    if symbol_info['symbol'] == symbol:
                        return symbol_info
        except Exception as e:
            logger.error(f"Failed to get symbol info for {symbol}: {e}")
        return {}

    def place_buy_order(self, symbol: str, amount_usdt: float) -> Dict:
        """Place market buy order for specified USDT amount"""
        try:
            logger.info(f"Attempting to place buy order for {symbol} with ${amount_usdt} USDT")

            # Get current price
            price = self.get_symbol_price(symbol)
            if not price:
                logger.error(f"Could not get price for {symbol}")
                return {'error': f'Could not get price for {symbol}'}

            logger.info(f"Current price for {symbol}: ${price}")

            # Calculate quantity to buy (for logging only)
            quantity = amount_usdt / price
            logger.info(f"Calculated quantity: {quantity} {symbol}")

            # Get symbol info for precision
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                logger.error(f"Could not get symbol info for {symbol}")
                return {'error': f'Could not get symbol info for {symbol}'}

            logger.info(f"Symbol info retrieved for {symbol}")

            # Apply precision - find LOT_SIZE filter
            filters = symbol_info.get('filters', [])
            step_size = '0.00000001'  # default
            for filter_info in filters:
                if filter_info.get('filterType') == 'LOT_SIZE':
                    step_size = filter_info.get('stepSize', '0.00000001')
                    break

            step_size = float(step_size)
            precision = len(str(step_size).split('.')[-1].rstrip('0'))
            quantity = round(quantity, precision)

            logger.info(f"Adjusted quantity with precision {precision}: {quantity} {symbol}")

            # Skip balance check for now - let MEXC API handle insufficient balance errors
            # This allows trading with funds in different networks (TRC20, ERC20, etc.)
            logger.info("Skipping balance check - ensure sufficient USDT funds are available on MEXC spot account")

            # Place market buy order
            # MEXC expects quoteOrderQty for MARKET BUY (amount in USDT)
            order_params = {
                'symbol': symbol,
                'side': 'BUY',
                'type': 'MARKET',
                'quoteOrderQty': amount_usdt
            }

            logger.info(f"Placing order with params: {order_params}")

            # Check if symbol is trading
            symbol_status = symbol_info.get('status', 'UNKNOWN')
            logger.info(f"Symbol {symbol} status: {symbol_status}")

            # MEXC uses different status values, accept both 'TRADING' and '1' as active
            if symbol_status not in ['TRADING', '1']:
                logger.error(f"Symbol {symbol} is not trading (status: {symbol_status})")
                return {'error': f'Symbol {symbol} is not trading (status: {symbol_status})'}
            else:
                logger.info(f"Symbol {symbol} is active for trading")

            order_result = self._make_request('POST', '/api/v3/order', order_params, signed=True)
            logger.info(f"Order result: {order_result}")

            if order_result and 'orderId' in order_result:
                # Ensure executedQty/price are available for downstream logic
                order_price = float(order_result.get('price', 0) or 0)
                if order_price == 0:
                    order_price = price
                executed_qty = float(order_result.get('executedQty', 0) or 0)
                if executed_qty == 0:
                    executed_qty = round(amount_usdt / order_price, precision)
                    order_result['executedQty'] = str(executed_qty)
                if not order_result.get('cummulativeQuoteQty'):
                    order_result['cummulativeQuoteQty'] = str(amount_usdt)
                order_result['price'] = str(order_price)
                logger.info(f"Successfully placed buy order for {quantity} {symbol} at ~${amount_usdt}")
                return order_result
            else:
                logger.error(f"Failed to place buy order: {order_result}")
                return {'error': 'Order placement failed'}

        except Exception as e:
            logger.error(f"Error placing buy order: {e}")
            return {'error': str(e)}

    def place_sell_order(self, symbol: str, quantity: float, symbol_info: Dict = None) -> Dict:
        """Place market sell order"""
        try:
            order_params = {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'MARKET',
                'quantity': quantity
            }

            order_result = self._make_request('POST', '/api/v3/order', order_params, signed=True)

            if order_result and 'orderId' in order_result:
                logger.info(f"Successfully placed sell order for {quantity} {symbol}")
                return order_result
            else:
                logger.error(f"Failed to place sell order: {order_result}")
                return {'error': 'Order placement failed'}

        except Exception as e:
            logger.error(f"Error placing sell order: {e}")
            return {'error': str(e)}

    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """Get open orders"""
        params = {}
        if symbol:
            params['symbol'] = symbol

        return self._make_request('GET', '/api/v3/openOrders', params, signed=True).get('orders', [])

    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """Cancel order"""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        return self._make_request('DELETE', '/api/v3/order', params, signed=True)

    def get_account_balance(self) -> Dict:
        """Get account balance"""
        account_info = self.get_account_info()
        if account_info and 'balances' in account_info:
            return {balance['asset']: float(balance['free']) for balance in account_info['balances'] if float(balance['free']) > 0}
        return {}

    def get_symbol_balance(self, symbol: str) -> float:
        """Get balance for specific symbol"""
        balances = self.get_account_balance()
        return balances.get(symbol, 0.0)