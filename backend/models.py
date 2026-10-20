from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    user: Mapped[User] = relationship(back_populates="sessions")


class InstrumentRecord(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("exchange", "symbol", name="uq_instrument_exchange_symbol"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    sector: Mapped[str | None] = mapped_column(String(128))
    data_source: Mapped[str] = mapped_column(String(64), default="unavailable")


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("instrument_id", "timeframe", "timestamp", name="uq_candle_instrument_time"),
        CheckConstraint("high >= low", name="ck_candle_high_low"),
        CheckConstraint("volume >= 0", name="ck_candle_volume_nonnegative"),
        Index("ix_candles_instrument_timestamp", "instrument_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    timeframe: Mapped[str] = mapped_column(String(16))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open: Mapped[float] = mapped_column(Numeric(18, 6))
    high: Mapped[float] = mapped_column(Numeric(18, 6))
    low: Mapped[float] = mapped_column(Numeric(18, 6))
    close: Mapped[float] = mapped_column(Numeric(18, 6))
    volume: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(64))


class SavedScreen(Base):
    __tablename__ = "saved_screens"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_saved_screen_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    filters: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_portfolio_user_name"),
        CheckConstraint("initial_cash >= 0", name="ck_portfolio_initial_cash_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    initial_cash: Mapped[float] = mapped_column(
        Numeric(18, 6), default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    transactions: Mapped[list["PortfolioTransaction"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_transaction_quantity_positive"),
        CheckConstraint("price >= 0 AND fees >= 0", name="ck_transaction_costs_nonnegative"),
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_transaction_side"),
        Index("ix_transactions_portfolio_timestamp", "portfolio_id", "transacted_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[float] = mapped_column(Numeric(18, 6))
    price: Mapped[float] = mapped_column(Numeric(18, 6))
    fees: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    transacted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "instrument_id", name="uq_watchlist_instrument"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    watchlist_id: Mapped[str] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"))
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    configuration: Mapped[dict] = mapped_column(JSON)
    results: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True)
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quantity: Mapped[float] = mapped_column(Numeric(18, 6))
    entry_price: Mapped[float] = mapped_column(Numeric(18, 6))
    exit_price: Mapped[float] = mapped_column(Numeric(18, 6))
    net_pnl: Mapped[float] = mapped_column(Numeric(18, 6))


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_news_source_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(128))
    source_id: Mapped[str] = mapped_column(String(255))
    headline: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(2048))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    related_symbols: Mapped[list] = mapped_column(JSON, default=list)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"))
    condition: Mapped[dict] = mapped_column(JSON)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        Index("ix_alert_events_alert_created", "alert_id", "created_at"),
        UniqueConstraint(
            "alert_id", "data_timestamp", name="uq_alert_event_data_timestamp"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"))
    message: Mapped[str] = mapped_column(String(512))
    triggered_value: Mapped[float] = mapped_column(Numeric(18, 6))
    data_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AIConversationMetadata(Base):
    __tablename__ = "ai_conversation_metadata"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
