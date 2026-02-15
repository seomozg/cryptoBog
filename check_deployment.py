#!/usr/bin/env python3
"""
Deployment check script for Docker environment
"""

import os
import sys
import requests
from config.settings import Config

def check_environment():
    """Check if all required environment variables are set"""
    config = Config()

    required_vars = [
        ('DEEPSEEK_API_KEY', config.DEEPSEEK_API_KEY),
        ('TELEGRAM_BOT_TOKEN', config.TELEGRAM_BOT_TOKEN),
        ('TELEGRAM_CHAT_ID', config.TELEGRAM_CHAT_ID),
    ]

    missing = []
    for name, value in required_vars:
        if not value or value.startswith('...') or value == 'sk-...':
            missing.append(name)

    if missing:
        print(f"❌ Missing required environment variables: {', '.join(missing)}")
        return False

    print("✅ All required environment variables are set")
    return True

def check_database():
    """Check database connection"""
    try:
        from database.db_manager import db_manager
        session = db_manager.get_session()
        session.close()
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def check_redis():
    """Check Redis connection"""
    try:
        import redis
        r = redis.Redis(host='redis', port=6379, db=0)
        r.ping()
        print("✅ Redis connection successful")
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def check_apis():
    """Check API endpoints"""
    config = Config()

    # Check DeepSeek API
    try:
        response = requests.post(
            f"{config.DEEPSEEK_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "test"}]},
            timeout=10
        )
        if response.status_code in [200, 400, 401]:  # 400/401 means API works but invalid request
            print("✅ DeepSeek API accessible")
        else:
            print(f"❌ DeepSeek API error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ DeepSeek API check failed: {e}")
        return False

    # Check Telegram API
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getMe",
            timeout=10
        )
        if response.status_code == 200:
            print("✅ Telegram API accessible")
        else:
            print(f"❌ Telegram API error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Telegram API check failed: {e}")
        return False

    return True

def main():
    """Run all checks"""
    print("🔍 Checking Crypto Alpha AI Advisor deployment...\n")

    checks = [
        ("Environment variables", check_environment),
        ("Database connection", check_database),
        ("Redis connection", check_redis),
        ("API endpoints", check_apis),
    ]

    passed = 0
    total = len(checks)

    for name, check_func in checks:
        print(f"📋 Checking {name}...")
        if check_func():
            passed += 1
        print()

    print(f"🎯 Deployment check complete: {passed}/{total} checks passed")

    if passed == total:
        print("🎉 All systems operational! Ready for production.")
        return 0
    else:
        print("⚠️ Some checks failed. Please review the errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())