#!/usr/bin/env python3
"""
Script to clear database tables for fresh start
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set DATABASE_URL for local execution if not set
if not os.getenv('DATABASE_URL'):
    os.environ['DATABASE_URL'] = 'postgresql://crypto:crypto_pass@localhost:5432/crypto'

from database.db_manager import db_manager
from database.models import AISignal, TradePosition
from sqlalchemy import text

def clear_database():
    """Clear all signals and positions from database"""
    try:
        db_manager.init_db()
        session = db_manager.get_session()
        
        # Count records before deletion
        signals_count = session.query(AISignal).count()
        positions_count = session.query(TradePosition).count()
        
        print(f"Found {signals_count} signals and {positions_count} positions in database")
        
        # Delete all records
        deleted_signals = session.query(AISignal).delete()
        deleted_positions = session.query(TradePosition).delete()
        
        session.commit()
        session.close()
        
        print(f"✅ Deleted {deleted_signals} signals and {deleted_positions} positions")
        print("Database cleared successfully!")
        
    except Exception as e:
        print(f"❌ Error clearing database: {e}")
        raise

if __name__ == "__main__":
    clear_database()