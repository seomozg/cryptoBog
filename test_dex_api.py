#!/usr/bin/env python3
"""
Test script to directly check DexScreener API data format and prices
"""

import requests
import json
from typing import Dict, List

def test_dexscreener_api():
    """Test DexScreener API directly"""
    print("🔍 Testing DexScreener API directly...")
    print("=" * 60)

    base_url = "https://api.dexscreener.com"
    session = requests.Session()

    try:
        # Test trending search endpoint
        print("\n📊 Testing /latest/dex/search endpoint...")
        url = f"{base_url}/latest/dex/search"
        params = {"q": "trending", "chainId": "ethereum", "limit": 10}

        print(f"URL: {url}")
        print(f"Params: {params}")

        response = session.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        print(f"✅ Response received. Status: {response.status_code}")
        print(f"📦 Data keys: {list(data.keys())}")

        pairs = data.get("pairs", [])
        print(f"📊 Found {len(pairs)} pairs")

        if pairs:
            print("\n🔍 First 3 pairs analysis:")
            for i, pair in enumerate(pairs[:3], 1):
                print(f"\n--- Pair {i} ---")
                print(f"Pair address: {pair.get('pairAddress', 'N/A')}")

                base_token = pair.get("baseToken", {})
                quote_token = pair.get("quoteToken", {})

                print(f"Base token: {base_token.get('symbol', 'N/A')} ({base_token.get('name', 'N/A')})")
                print(f"Quote token: {quote_token.get('symbol', 'N/A')} ({quote_token.get('name', 'N/A')})")

                price_usd = pair.get("priceUsd")
                print(f"Price USD: {price_usd} (type: {type(price_usd)})")

                if price_usd:
                    try:
                        price_float = float(price_usd)
                        print(f"  → Converted to float: ${price_float:.6f}")
                    except ValueError as e:
                        print(f"❌ Cannot convert price to float: {e}")

                liquidity = pair.get("liquidity", {})
                print(f"Liquidity USD: {liquidity.get('usd', 'N/A')}")

                volume = pair.get("volume", {})
                print(f"Volume 24h: {volume.get('h24', 'N/A')}")

                txns = pair.get("txns", {})
                h24_txns = txns.get("h24", {})
                print(f"Txns 24h: buys={h24_txns.get('buys', 0)}, sells={h24_txns.get('sells', 0)}")

        # Test if we can find USDT
        print("\n💰 Looking for USDT pairs...")
        usdt_pairs = [p for p in pairs if p.get("baseToken", {}).get("symbol", "").upper() == "USDT" or
                     p.get("quoteToken", {}).get("symbol", "").upper() == "USDT"]

        if usdt_pairs:
            print(f"✅ Found {len(usdt_pairs)} USDT pairs")
            for i, pair in enumerate(usdt_pairs[:2], 1):
                price = pair.get("priceUsd")
                base = pair.get("baseToken", {}).get("symbol")
                quote = pair.get("quoteToken", {}).get("symbol")
                print(".6f"        else:
            print("❌ No USDT pairs found in trending")

        # Test raw JSON structure
        print("\n🔧 Raw JSON structure of first pair:")
        if pairs:
            print(json.dumps(pairs[0], indent=2, default=str)[:1000] + "...")

    except requests.RequestException as e:
        print(f"❌ API request failed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

def test_price_parsing():
    """Test price parsing logic"""
    print("\n" + "=" * 60)
    print("🧮 Testing price parsing logic...")

    test_prices = [
        "0.00000714",  # Problematic USDT price
        "3500.50",     # Normal ETH price
        "1.001",       # USDC price
        "95000.25",    # BTC price
        None,          # None value
        "0",           # Zero
        "",            # Empty string
    ]

    for price_str in test_prices:
        print(f"\nTesting price: {repr(price_str)}")
        try:
            if price_str is None or price_str == "":
                print("  → Skipped (None/empty)")
                continue

            price_float = float(price_str)
            print(".6f"
            # Check if it's a stablecoin with wrong price
            if price_float < 0.1 or price_float > 10:
                print("  ⚠️  Would be flagged as invalid stablecoin price"            else:
                print("  ✅ Valid stablecoin price range"

            # Check if it's too low
            if price_float < 0.001:
                print("  ⚠️  Would be flagged as too low price"            else:
                print("  ✅ Price above minimum threshold"

        except ValueError as e:
            print(f"  ❌ Conversion failed: {e}")

if __name__ == '__main__':
    test_dexscreener_api()
    test_price_parsing()