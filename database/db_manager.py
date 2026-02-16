from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import logging
import os

from .models import Base
from config.settings import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.config = Config()
        self.engine = None
        self.SessionLocal = None

    def init_db(self):
        """Initialize database connection and create tables"""
        try:
            # Try to get DATABASE_URL from environment first
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                # Hardcode for worker container
                if os.path.exists('/app'):
                    db_url = 'postgresql://crypto:crypto_pass@postgres:5432/crypto'
                else:
                    # Fall back to config
                    db_url = self.config.DATABASE_URL
            print(f"DEBUG: Using DATABASE_URL: {db_url}")
            self.engine = create_engine(db_url)

            # Create tables
            Base.metadata.create_all(bind=self.engine)

            # Note: TimescaleDB hypertables will be created manually if needed
            # For production, run these SQL commands:
            # SELECT create_hypertable('price_snapshots', 'time', if_not_exists => TRUE);
            # SELECT create_hypertable('trade_activity', 'time', if_not_exists => TRUE);

            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            logger.info("Database initialized successfully")
        except SQLAlchemyError as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    def get_session(self) -> Session:
        """Get database session"""
        if self.SessionLocal is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return self.SessionLocal()

    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()

# Global instance
db_manager = DatabaseManager()