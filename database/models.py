from sqlalchemy import Column, Integer, String, Float, TIMESTAMP, Text, Boolean, DECIMAL, func, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

Base = declarative_base()

class TokenMetadata(Base):
    __tablename__ = 'token_metadata'

    id = Column(Integer, primary_key=True)
    network = Column(String(50), nullable=False)
    token_address = Column(String(255), nullable=False)
    symbol = Column(String(50))
    name = Column(String(255))
    first_seen = Column(TIMESTAMP, default=func.now())
    last_updated = Column(TIMESTAMP, default=func.now())

class PriceSnapshot(Base):
    __tablename__ = 'price_snapshots'

    time = Column(TIMESTAMP(timezone=True), primary_key=True, nullable=False)
    token_id = Column(Integer, primary_key=True)
    price_usd = Column(DECIMAL(20, 8))
    liquidity_usd = Column(DECIMAL(20, 2))
    volume_24h = Column(DECIMAL(20, 2))
    fdv_usd = Column(DECIMAL(20, 2))
    market_cap_usd = Column(DECIMAL(20, 2))

class TradeActivity(Base):
    __tablename__ = 'trade_activity'

    time = Column(TIMESTAMP(timezone=True), primary_key=True, nullable=False)
    token_id = Column(Integer, primary_key=True)
    buys_1h = Column(Integer)
    sells_1h = Column(Integer)
    buys_24h = Column(Integer)
    sells_24h = Column(Integer)
    txns_1h = Column(Integer)
    txns_24h = Column(Integer)
    volume_1h = Column(DECIMAL(20, 2))



class AISignal(Base):
    __tablename__ = 'ai_signals'

    id = Column(Integer, primary_key=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    asset = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    entry_min = Column(Float, nullable=False)
    entry_max = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    probability = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    risk_reward = Column(Float, nullable=False)
    historical_analogs = Column(Text)
    reasoning = Column(Text)
    sent_to_telegram = Column(Boolean, default=False)

class TradePosition(Base):
    __tablename__ = 'trade_positions'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False)  # e.g., 'ETHUSDT'
    side = Column(String(10), nullable=False)    # 'BUY' or 'SELL'
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    order_id = Column(String(50), nullable=False)
    status = Column(String(20), default='OPEN')  # 'OPEN', 'CLOSED'
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
