#!/usr/bin/env python3
"""
Check the raw format of DexScreener API response
"""

import requests
import json

def check_api_format():
    print("🔍 Checking DexScreener API response format...")

    url = "https://api.dexscreener.com/latest/dex/search"
    params = {"q": "trending", "chainId": "ethereum", "limit": 3}

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        print(f"Status: {response.status_code}")
        print(f"Response keys: {list(data.keys())}")

        pairs = data.get("pairs", [])
        print(f"Number of pairs: {len(pairs)}")

        if pairs:
            print("\n" + "="*50)
            print("RAW JSON STRUCTURE OF FIRST PAIR:")
            print("="*50)
            print(json.dumps(pairs[0], indent=2))

            print("\n" + "="*50)
            print("EXTRACTED FIELDS:")
            print("="*50)

            pair = pairs[0]
            base_token = pair.get("baseToken", {})
            quote_token = pair.get("quoteToken", {})

            print(f"baseToken.address: {base_token.get('address')}")
            print(f"baseToken.symbol: {base_token.get('symbol')}")
            print(f"baseToken.name: {base_token.get('name')}")

            print(f"quoteToken.address: {quote_token.get('address')}")
            print(f"quoteToken.symbol: {quote_token.get('symbol')}")
            print(f"quoteToken.name: {quote_token.get('name')}")

            print(f"priceUsd: {pair.get('priceUsd')} (type: {type(pair.get('priceUsd'))})")
            print(f"marketCap: {pair.get('marketCap')} (type: {type(pair.get('marketCap'))})")
            print(f"fdv: {pair.get('fdv')} (type: {type(pair.get('fdv'))})")

            liquidity = pair.get("liquidity", {})
            print(f"liquidity.usd: {liquidity.get('usd')} (type: {type(liquidity.get('usd'))})")

            volume = pair.get("volume", {})
            print(f"volume.h24: {volume.get('h24')} (type: {type(volume.get('h24'))})")

            txns = pair.get("txns", {})
            h24_txns = txns.get("h24", {})
            print(f"txns.h24.buys: {h24_txns.get('buys')} (type: {type(h24_txns.get('buys'))})")
            print(f"txns.h24.sells: {h24_txns.get('sells')} (type: {type(h24_txns.get('sells'))})")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    check_api_format()