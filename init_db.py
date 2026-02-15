#!/usr/bin/env python3
"""
Database initialization script for Docker
"""

import time
import logging
from database.db_manager import db_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def wait_for_db(max_attempts=30):
    """Wait for database to be ready"""
    for attempt in range(max_attempts):
        try:
            db_manager.init_db()
            logger.info("Database initialized successfully")
            return True
        except Exception as e:
            logger.warning(f"Database not ready (attempt {attempt + 1}/{max_attempts}): {e}")
            time.sleep(2)
    return False

if __name__ == '__main__':
    if wait_for_db():
        logger.info("Database setup complete")
    else:
        logger.error("Failed to initialize database")
        exit(1)