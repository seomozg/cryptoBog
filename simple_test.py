#!/usr/bin/env python3
"""
Simple test to check DexScreener API data
"""

import requests
import json

def main():
    print("Testing DexScreener API...")

    url = "https://api.dexscreener.com/latest/dex/search"
    params = {"q": "trending", "chainId": "ethereum", "limit": 5}

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        pairs = data.get("pairs", [])
        print(f"Found {len(pairs)} pairs")

        for i, pair in enumerate(pairs[:3], 1):
            print(f"\nPair {i}:")
            base = pair.get("baseToken", {})
            quote = pair.get("quoteToken", {})
            price = pair.get("priceUsd")

            print(f"  {base.get('symbol')} / {quote.get('symbol')}")
            print(f"  Price: {price}")
            print(f"  Type: {type(price)}")

            if price:
                try:
                    price_float = float(price)
                    print(f"  Float: {price_float}")
                except:
                    print("  Cannot convert to float")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()