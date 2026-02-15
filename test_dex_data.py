#!/usr/bin/env python3
"""
Test script to show what data we get from DexScreener API
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from collectors.dex_paprika import DexPaprikaCollector
import json

def main():
    print("🔍 Testing DexScreener API data collection...")
    print("=" * 60)

    collector = DexPaprikaCollector()

    # Get trending tokens
    print("\n📊 Getting trending tokens from API...")
    trending_tokens = collector.get_trending_tokens("ethereum", 20)

    print(f"📈 Retrieved {len(trending_tokens)} tokens from API")
    print("\n🔍 Raw API response sample (first 3 tokens):")
    print(json.dumps(trending_tokens[:3], indent=2, default=str))

    print("\n" + "=" * 60)
    print("🎯 Testing data filtering and validation...")

    # Test collection for analysis
    print("\n⚙️ Collecting data for analysis...")
    analysis_data = collector.collect_for_analysis("ethereum", 10)

    if analysis_data:
        print(f"✅ Successfully collected {len(analysis_data)} valid tokens")
        print("\n📋 Valid tokens data:")
        print("-" * 80)
        print("<10")
        print("-" * 80)

        for i, token in enumerate(analysis_data, 1):
            print("2d"
                  "8.6f"
                  "12.0f"
                  "12.0f"
                  "8d"
                  "8d"
                  "10.0f")

        print("-" * 80)
        print(f"📊 Total valid tokens: {len(analysis_data)}")

        # Show price distribution
        prices = [float(token['price_usd']) for token in analysis_data if token['price_usd']]
        if prices:
            print("
💰 Price statistics:"            print(".6f"            print(".6f"            print(".6f")

    else:
        print("❌ No valid data collected")

if __name__ == '__main__':
    main()