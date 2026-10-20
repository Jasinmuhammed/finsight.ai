from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
import os
from typing import AsyncIterator, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.alert_scheduler import create_alert_scheduler
from backend.alerts import poll_alerts
from backend.auth import get_current_user, router as auth_router, verify_request_origin
from backend.database import get_db
from backend.models import (
    Alert,
    AlertEvent,
    BacktestRun,
    BacktestTrade as BacktestTradeRecord,
    InstrumentRecord,
    Portfolio,
    PortfolioTransaction,
    SavedScreen,
    User,
    Watchlist,
    WatchlistItem,
)
from backend.portfolio import (
    PortfolioRisk,
    PortfolioTransactionInput,
    calculate_ledger,
    calculate_portfolio_risk,
)
from backend.market_data import (
    HistoricalCandles,
    InstrumentMetadata,
    ProviderUnavailable,
    get_market_data_provider,
)
from backend.backtesting import BacktestResult, StrategyConfig, run_backtest
from backend.screener import (
    AdvancedScreenerRequest,
    AdvancedScreenerResponse,
    screen_historical_instruments,
)
from backend.analytics import (
    PatternDetection,
    calculate_indicators,
    detect_range_breakouts,
)
from backend.news import (
    NewsServiceError,
    NewsServiceUnavailable,
    fetch_financial_news,
    summarize_news_with_gemini,
)


class Instrument(BaseModel):
    symbol: str
    name: str
    exchange: Literal["NSE", "BSE"]
    currency: Literal["INR"] = "INR"
    price: float = Field(gt=0)
    change_percent: float
    volume: int = Field(ge=0)
    source: Literal["illustrative_demo"] = "illustrative_demo"


class ScreenerRequest(BaseModel):
    min_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    min_change_percent: float | None = Field(default=None, allow_inf_nan=False)
    max_change_percent: float | None = Field(default=None, allow_inf_nan=False)
    min_volume: int | None = Field(default=None, ge=0)
    exchange: Literal["NSE", "BSE"] | None = None
    combine: Literal["AND", "OR"] = "AND"

    @model_validator(mode="after")
    def validate_ranges(self) -> "ScreenerRequest":
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price must be less than or equal to max_price")
        if (
            self.min_change_percent is not None
            and self.max_change_percent is not None
            and self.min_change_percent > self.max_change_percent
        ):
            raise ValueError(
                "min_change_percent must be less than or equal to max_change_percent"
            )
        return self


class ScreenerResponse(BaseModel):
    results: list[Instrument]
    count: int
    data_as_of: datetime
    data_status: Literal["DEMO"]
    source: str


class SavedScreenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    filters: AdvancedScreenerRequest


class SavedScreenResponse(BaseModel):
    id: str
    name: str
    filters: dict
    created_at: datetime
    updated_at: datetime


class IndicatorResponse(BaseModel):
    symbol: str
    exchange: Literal["NSE", "BSE"]
    timeframe: Literal["1d"]
    data_status: Literal["HISTORICAL"]
    source: str
    data_as_of: datetime | None
    indicators: dict[str, list[float | None]]


class PatternResponse(BaseModel):
    symbol: str
    exchange: Literal["NSE", "BSE"]
    timeframe: Literal["1d"]
    data_status: Literal["HISTORICAL"]
    source: str
    patterns: list[PatternDetection]


class NewsArticleResponse(BaseModel):
    source: str
    source_id: str
    headline: str
    summary: str
    url: str
    published_at: datetime
    related_symbols: list[str]


class NewsResponse(BaseModel):
    data_status: Literal["NEWS"]
    source: str
    articles: list[NewsArticleResponse]
    ai_status: Literal["NOT_REQUESTED", "NO_ARTICLES", "UNAVAILABLE", "AVAILABLE"]
    ai_summary: str | None


class CreateWatchlistRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class WatchlistInstrumentRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    exchange: Literal["NSE", "BSE"]

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return InstrumentMetadata(
            symbol=value, exchange="NSE", name=value
        ).symbol


class WatchlistInstrumentResponse(BaseModel):
    id: str
    symbol: str
    exchange: Literal["NSE", "BSE"]
    added_at: datetime


class WatchlistResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    instruments: list[WatchlistInstrumentResponse]


class CreateAlertRequest(WatchlistInstrumentRequest):
    operator: Literal["ABOVE", "BELOW"]
    target_price: float = Field(gt=0, allow_inf_nan=False)
    cooldown_seconds: int = Field(default=3600, ge=60, le=604800)


class AlertResponse(BaseModel):
    id: str
    symbol: str
    exchange: Literal["NSE", "BSE"]
    operator: Literal["ABOVE", "BELOW"]
    target_price: float
    cooldown_seconds: int
    enabled: bool
    created_at: datetime


class UpdateAlertRequest(BaseModel):
    enabled: bool


class AlertEventResponse(BaseModel):
    id: str
    alert_id: str
    symbol: str
    exchange: Literal["NSE", "BSE"]
    message: str
    triggered_value: float
    data_status: Literal["HISTORICAL", "UNAVAILABLE"]
    data_as_of: datetime | None
    created_at: datetime
    read_at: datetime | None


class AlertPollResponse(BaseModel):
    created_events: int
    skipped_alerts: int
    data_status: Literal["HISTORICAL"]
    message: str


class RunBacktestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    exchange: Literal["NSE", "BSE"]
    start: date | None = None
    end: date | None = None
    strategy: StrategyConfig

    @model_validator(mode="after")
    def validate_date_range(self) -> "RunBacktestRequest":
        if self.start and self.end and self.start > self.end:
            raise ValueError("start date must be on or before end date")
        return self


class RunBacktestResponse(BaseModel):
    id: str
    symbol: str
    exchange: Literal["NSE", "BSE"]
    source: str
    result: BacktestResult


class CreatePortfolioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    initial_cash: float = Field(default=0, ge=0, allow_inf_nan=False)


class PortfolioResponse(BaseModel):
    id: str
    name: str
    currency: str
    initial_cash: float
    created_at: datetime


class HoldingResponse(BaseModel):
    symbol: str
    exchange: Literal["NSE", "BSE"]
    quantity: float
    average_cost: float
    historical_last_close: float | None
    market_value: float | None
    realized_pnl: float
    unrealized_pnl: float | None
    allocation_percent: float | None
    price_status: Literal["HISTORICAL", "UNAVAILABLE"]
    price_as_of: datetime | None


class PortfolioOverviewResponse(BaseModel):
    portfolio_id: str
    initial_cash: float
    cash_balance: float
    cash_allocation_percent: float | None
    total_value: float | None
    realized_pnl: float
    unrealized_pnl: float | None
    valuation_status: Literal["HISTORICAL", "PARTIAL", "UNAVAILABLE", "CASH_ONLY"]
    data_as_of: datetime | None
    holdings: list[HoldingResponse]
    risk: PortfolioRisk


class PortfolioTransactionResponse(BaseModel):
    id: str
    symbol: str
    exchange: Literal["NSE", "BSE"]
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float
    fees: float
    transacted_at: datetime


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    scheduler = create_alert_scheduler()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(
    title="FinSight AI API",
    version="0.1.0",
    description="FinSight AI development API. The bundled instrument set is illustrative demo data.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "AUTH_ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(auth_router, prefix="/api/v1")

DEMO_INSTRUMENTS = [
    Instrument(
        symbol="DEMO1",
        name="Example Industries",
        exchange="NSE",
        price=1250.0,
        change_percent=1.42,
        volume=1523400,
    ),
    Instrument(
        symbol="DEMO2",
        name="Illustrative Technologies",
        exchange="BSE",
        price=842.5,
        change_percent=-0.68,
        volume=734200,
    ),
    Instrument(
        symbol="DEMO3",
        name="Sample Consumer Ltd",
        exchange="NSE",
        price=2310.75,
        change_percent=2.15,
        volume=2891000,
    ),
    Instrument(
        symbol="DEMO4",
        name="Placeholder Finance",
        exchange="NSE",
        price=486.2,
        change_percent=-1.1,
        volume=418600,
    ),
]


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "finsight-api"}


@app.get("/api/v1/health/ready")
def readiness(database: Session = Depends(get_db)) -> dict[str, str]:
    try:
        database.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503, detail="Database readiness check failed."
        ) from error
    return {"status": "ready", "database": "ok"}


@app.get("/api/v1/instruments", response_model=list[Instrument])
def list_instruments() -> list[Instrument]:
    return DEMO_INSTRUMENTS


@app.post("/api/v1/screener", response_model=ScreenerResponse)
def screen_instruments(filters: ScreenerRequest) -> ScreenerResponse:
    predicates = []
    if filters.min_price is not None:
        predicates.append(lambda item: item.price >= filters.min_price)
    if filters.max_price is not None:
        predicates.append(lambda item: item.price <= filters.max_price)
    if filters.min_change_percent is not None:
        predicates.append(
            lambda item: item.change_percent >= filters.min_change_percent
        )
    if filters.max_change_percent is not None:
        predicates.append(
            lambda item: item.change_percent <= filters.max_change_percent
        )
    if filters.min_volume is not None:
        predicates.append(lambda item: item.volume >= filters.min_volume)
    if filters.exchange is not None:
        predicates.append(lambda item: item.exchange == filters.exchange)

    def matches(item: Instrument) -> bool:
        if not predicates:
            return True
        outcomes = [predicate(item) for predicate in predicates]
        return all(outcomes) if filters.combine == "AND" else any(outcomes)

    return ScreenerResponse(
        results=[item for item in DEMO_INSTRUMENTS if matches(item)],
        count=sum(matches(item) for item in DEMO_INSTRUMENTS),
        data_as_of=datetime.now(timezone.utc),
        data_status="DEMO",
        source="Illustrative demo dataset; not market data",
    )


@app.get("/api/v1/instruments/{symbol}", response_model=Instrument)
def get_instrument(symbol: str) -> Instrument:
    for instrument in DEMO_INSTRUMENTS:
        if instrument.symbol == symbol.upper():
            return instrument
    raise HTTPException(status_code=404, detail="Instrument not found")


@app.get("/api/v1/market-data/status")
def market_data_status() -> dict[str, str | bool]:
    return get_market_data_provider().status()


@app.get("/api/v1/news", response_model=NewsResponse)
def financial_news(
    limit: int = Query(default=20, ge=1, le=50),
    symbol: str | None = Query(default=None, min_length=1, max_length=32),
    summarize_ai: bool = False,
) -> NewsResponse:
    try:
        articles = fetch_financial_news(limit=limit, symbol=symbol)
        summary = summarize_news_with_gemini(articles) if summarize_ai else None
    except NewsServiceUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except NewsServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return NewsResponse(
        data_status="NEWS",
        source="Finnhub",
        articles=articles,
        ai_status=(
            "NOT_REQUESTED"
            if not summarize_ai
            else "NO_ARTICLES"
            if not articles
            else "AVAILABLE"
            if summary
            else "UNAVAILABLE"
        ),
        ai_summary=summary,
    )


def _watchlist_for_user(
    watchlist_id: UUID, user: User, database: Session
) -> Watchlist:
    watchlist = database.scalar(
        select(Watchlist).where(
            Watchlist.id == str(watchlist_id),
            Watchlist.user_id == user.id,
        )
    )
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return watchlist


def _alert_for_user(alert_id: UUID, user: User, database: Session) -> Alert:
    alert = database.scalar(
        select(Alert).where(Alert.id == str(alert_id), Alert.user_id == user.id)
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


def _alert_response(alert: Alert, instrument: InstrumentRecord) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        operator=alert.condition["operator"],
        target_price=float(alert.condition["target_price"]),
        cooldown_seconds=alert.cooldown_seconds,
        enabled=alert.enabled,
        created_at=alert.created_at,
    )


@app.post(
    "/api/v1/watchlists",
    response_model=WatchlistResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def create_watchlist(
    payload: CreateWatchlistRequest,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> WatchlistResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Watchlist name cannot be empty")
    watchlist = Watchlist(user_id=user.id, name=name)
    database.add(watchlist)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=409, detail="A watchlist with this name already exists"
        ) from error
    database.refresh(watchlist)
    return WatchlistResponse(
        id=watchlist.id,
        name=watchlist.name,
        created_at=watchlist.created_at,
        instruments=[],
    )


@app.get("/api/v1/watchlists", response_model=list[WatchlistResponse])
def list_watchlists(
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> list[WatchlistResponse]:
    watchlists = list(
        database.scalars(
            select(Watchlist)
            .where(Watchlist.user_id == user.id)
            .order_by(Watchlist.created_at, Watchlist.id)
        )
    )
    if not watchlists:
        return []
    items = database.execute(
        select(WatchlistItem, InstrumentRecord)
        .join(InstrumentRecord, InstrumentRecord.id == WatchlistItem.instrument_id)
        .where(WatchlistItem.watchlist_id.in_([item.id for item in watchlists]))
        .order_by(WatchlistItem.added_at, WatchlistItem.id)
    ).all()
    instruments_by_watchlist: dict[str, list[WatchlistInstrumentResponse]] = {
        watchlist.id: [] for watchlist in watchlists
    }
    for item, instrument in items:
        instruments_by_watchlist[item.watchlist_id].append(
            WatchlistInstrumentResponse(
                id=item.id,
                symbol=instrument.symbol,
                exchange=instrument.exchange,
                added_at=item.added_at,
            )
        )
    return [
        WatchlistResponse(
            id=watchlist.id,
            name=watchlist.name,
            created_at=watchlist.created_at,
            instruments=instruments_by_watchlist[watchlist.id],
        )
        for watchlist in watchlists
    ]


@app.delete(
    "/api/v1/watchlists/{watchlist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_request_origin)],
)
def delete_watchlist(
    watchlist_id: UUID,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> Response:
    watchlist = _watchlist_for_user(watchlist_id, user, database)
    database.execute(
        delete(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist.id)
    )
    database.delete(watchlist)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/v1/watchlists/{watchlist_id}/items",
    response_model=WatchlistInstrumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def add_watchlist_instrument(
    watchlist_id: UUID,
    payload: WatchlistInstrumentRequest,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> WatchlistInstrumentResponse:
    watchlist = _watchlist_for_user(watchlist_id, user, database)
    instrument = _instrument_for_transaction(
        payload.symbol, payload.exchange, database
    )
    item = WatchlistItem(
        watchlist_id=watchlist.id,
        instrument_id=instrument.id,
    )
    database.add(item)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=409, detail="Instrument is already in this watchlist"
        ) from error
    database.refresh(item)
    return WatchlistInstrumentResponse(
        id=item.id,
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        added_at=item.added_at,
    )


@app.delete(
    "/api/v1/watchlists/{watchlist_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_request_origin)],
)
def remove_watchlist_instrument(
    watchlist_id: UUID,
    item_id: UUID,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> Response:
    watchlist = _watchlist_for_user(watchlist_id, user, database)
    item = database.scalar(
        select(WatchlistItem).where(
            WatchlistItem.id == str(item_id),
            WatchlistItem.watchlist_id == watchlist.id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist instrument not found")
    database.delete(item)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/v1/alerts",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def create_alert(
    payload: CreateAlertRequest,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> AlertResponse:
    instrument = _instrument_for_transaction(
        payload.symbol, payload.exchange, database
    )
    alert = Alert(
        user_id=user.id,
        instrument_id=instrument.id,
        condition={
            "operator": payload.operator,
            "target_price": payload.target_price,
        },
        cooldown_seconds=payload.cooldown_seconds,
        enabled=True,
    )
    database.add(alert)
    database.commit()
    database.refresh(alert)
    return _alert_response(alert, instrument)


@app.get("/api/v1/alerts", response_model=list[AlertResponse])
def list_alerts(
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> list[AlertResponse]:
    rows = database.execute(
        select(Alert, InstrumentRecord)
        .join(InstrumentRecord, InstrumentRecord.id == Alert.instrument_id)
        .where(Alert.user_id == user.id)
        .order_by(Alert.created_at.desc(), Alert.id)
    ).all()
    return [_alert_response(alert, instrument) for alert, instrument in rows]


@app.patch(
    "/api/v1/alerts/{alert_id}",
    response_model=AlertResponse,
    dependencies=[Depends(verify_request_origin)],
)
def update_alert(
    alert_id: UUID,
    payload: UpdateAlertRequest,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> AlertResponse:
    alert = _alert_for_user(alert_id, user, database)
    alert.enabled = payload.enabled
    database.commit()
    database.refresh(alert)
    instrument = database.get(InstrumentRecord, alert.instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Alert instrument not found")
    return _alert_response(alert, instrument)


@app.delete(
    "/api/v1/alerts/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_request_origin)],
)
def delete_alert(
    alert_id: UUID,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> Response:
    alert = _alert_for_user(alert_id, user, database)
    database.execute(delete(AlertEvent).where(AlertEvent.alert_id == alert.id))
    database.delete(alert)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/v1/alerts/poll",
    response_model=AlertPollResponse,
    dependencies=[Depends(verify_request_origin)],
)
def poll_user_alerts(
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> AlertPollResponse:
    provider = get_market_data_provider()
    provider_status = provider.status()
    if not provider_status.get("configured", False):
        raise HTTPException(
            status_code=503,
            detail=str(provider_status.get("message", "Historical data is unavailable.")),
        )
    try:
        result = poll_alerts(database, provider, user_id=user.id)
    except ProviderUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return AlertPollResponse(
        created_events=result.created_events,
        skipped_alerts=result.skipped_alerts,
        data_status="HISTORICAL",
        message=(
            "Evaluated newly timestamped user-supplied daily bars only. "
            "This is not live-price monitoring."
            + (
                f" {result.skipped_alerts} alerts were skipped because their history was unavailable or invalid."
                if result.skipped_alerts
                else ""
            )
        ),
    )


@app.get("/api/v1/alerts/events", response_model=list[AlertEventResponse])
def list_alert_events(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> list[AlertEventResponse]:
    rows = database.execute(
        select(AlertEvent, Alert, InstrumentRecord)
        .join(Alert, Alert.id == AlertEvent.alert_id)
        .join(InstrumentRecord, InstrumentRecord.id == Alert.instrument_id)
        .where(Alert.user_id == user.id)
        .order_by(AlertEvent.created_at.desc(), AlertEvent.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        AlertEventResponse(
            id=event.id,
            alert_id=alert.id,
            symbol=instrument.symbol,
            exchange=instrument.exchange,
            message=event.message,
            triggered_value=float(event.triggered_value),
            data_status="HISTORICAL" if event.data_timestamp else "UNAVAILABLE",
            data_as_of=event.data_timestamp,
            created_at=event.created_at,
            read_at=event.read_at,
        )
        for event, alert, instrument in rows
    ]


@app.put(
    "/api/v1/alerts/events/{event_id}/read",
    response_model=AlertEventResponse,
    dependencies=[Depends(verify_request_origin)],
)
def mark_alert_event_read(
    event_id: UUID,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> AlertEventResponse:
    row = database.execute(
        select(AlertEvent, Alert, InstrumentRecord)
        .join(Alert, Alert.id == AlertEvent.alert_id)
        .join(InstrumentRecord, InstrumentRecord.id == Alert.instrument_id)
        .where(AlertEvent.id == str(event_id), Alert.user_id == user.id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Alert event not found")
    event, alert, instrument = row
    event.read_at = datetime.now(timezone.utc)
    database.commit()
    return AlertEventResponse(
        id=event.id,
        alert_id=alert.id,
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        message=event.message,
        triggered_value=float(event.triggered_value),
        data_status="HISTORICAL" if event.data_timestamp else "UNAVAILABLE",
        data_as_of=event.data_timestamp,
        created_at=event.created_at,
        read_at=event.read_at,
    )


@app.post(
    "/api/v1/market-data/screener",
    response_model=AdvancedScreenerResponse,
)
def screen_historical_data(
    filters: AdvancedScreenerRequest,
) -> AdvancedScreenerResponse:
    try:
        return screen_historical_instruments(
            get_market_data_provider(), filters
        )
    except ProviderUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/v1/market-data/instruments/search", response_model=list[InstrumentMetadata])
def search_market_instruments(
    query: str = Query(default="", max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[InstrumentMetadata]:
    try:
        return get_market_data_provider().search_instruments(query, limit)
    except ProviderUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get(
    "/api/v1/market-data/instruments/{exchange}/{symbol}/candles",
    response_model=HistoricalCandles,
)
def historical_candles(
    exchange: Literal["NSE", "BSE"],
    symbol: str,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=2000, ge=1, le=5000),
) -> HistoricalCandles:
    provider = get_market_data_provider()
    try:
        candles = provider.historical_daily_candles(symbol, exchange, start, end)
    except ProviderUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    candles = candles[-limit:]
    return HistoricalCandles(
        symbol=symbol.upper(),
        exchange=exchange,
        timeframe="1d",
        candles=candles,
        data_status="HISTORICAL",
        source="User-supplied CSV",
        data_as_of=candles[-1].timestamp if candles else None,
        provenance_note="User-supplied CSV; source provenance is not independently verified.",
    )


@app.get(
    "/api/v1/market-data/instruments/{exchange}/{symbol}/indicators",
    response_model=IndicatorResponse,
)
def instrument_indicators(
    exchange: Literal["NSE", "BSE"],
    symbol: str,
    sma_period: int = Query(default=20, ge=1, le=252),
    ema_period: int = Query(default=20, ge=1, le=252),
    rsi_period: int = Query(default=14, ge=1, le=252),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=2000, ge=1, le=5000),
) -> IndicatorResponse:
    provider = get_market_data_provider()
    try:
        candles = provider.historical_daily_candles(symbol, exchange, start, end)
    except ProviderUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    candles = candles[-limit:]
    return IndicatorResponse(
        symbol=symbol.upper(),
        exchange=exchange,
        timeframe="1d",
        data_status="HISTORICAL",
        source="User-supplied CSV",
        data_as_of=candles[-1].timestamp if candles else None,
        indicators=calculate_indicators(
            candles, sma_period=sma_period, ema_period=ema_period, rsi_period=rsi_period
        ),
    )


@app.get(
    "/api/v1/market-data/instruments/{exchange}/{symbol}/patterns",
    response_model=PatternResponse,
)
def instrument_patterns(
    exchange: Literal["NSE", "BSE"],
    symbol: str,
    lookback: int = Query(default=20, ge=2, le=252),
    volume_multiplier: float = Query(default=1.5, gt=0, le=100),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=2000, ge=1, le=5000),
) -> PatternResponse:
    provider = get_market_data_provider()
    try:
        candles = provider.historical_daily_candles(symbol, exchange, start, end)
    except ProviderUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    candles = candles[-limit:]
    return PatternResponse(
        symbol=symbol.upper(),
        exchange=exchange,
        timeframe="1d",
        data_status="HISTORICAL",
        source="User-supplied CSV",
        patterns=detect_range_breakouts(
            candles, lookback=lookback, volume_multiplier=volume_multiplier
        ),
    )


@app.post(
    "/api/v1/backtests/run",
    response_model=RunBacktestResponse,
    dependencies=[Depends(verify_request_origin)],
)
def run_historical_backtest(
    payload: RunBacktestRequest,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> RunBacktestResponse:
    provider = get_market_data_provider()
    try:
        candles = provider.historical_daily_candles(
            payload.symbol, payload.exchange, payload.start, payload.end
        )
    except ProviderUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if len(candles) < 2:
        raise HTTPException(
            status_code=422, detail="At least two historical daily candles are required."
        )
    if len(candles) > 5000:
        raise HTTPException(
            status_code=422,
            detail="Backtests are limited to 5,000 daily candles. Narrow the selected date range.",
        )
    try:
        result = run_backtest(candles, payload.strategy)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    run = BacktestRun(
        user_id=user.id,
        configuration={
            **payload.model_dump(mode="json", exclude={"strategy"}),
            "strategy": payload.strategy.model_dump(mode="json"),
        },
        results=result.model_dump(mode="json"),
    )
    database.add(run)
    database.flush()
    database.add_all(
        [
            BacktestTradeRecord(
                run_id=run.id,
                entry_at=trade.entry_at,
                exit_at=trade.exit_at,
                quantity=trade.quantity,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                net_pnl=trade.net_pnl,
            )
            for trade in result.trades
        ]
    )
    database.commit()
    return RunBacktestResponse(
        id=run.id,
        symbol=payload.symbol.upper(),
        exchange=payload.exchange,
        source="User-supplied CSV",
        result=result,
    )


def _portfolio_for_user(
    portfolio_id: UUID, user: User, database: Session
) -> Portfolio:
    portfolio = database.scalar(
        select(Portfolio).where(
            Portfolio.id == str(portfolio_id),
            Portfolio.user_id == user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


def _transaction_input(
    transaction: PortfolioTransaction, instrument: InstrumentRecord
) -> PortfolioTransactionInput:
    transacted_at = transaction.transacted_at
    if transacted_at.tzinfo is None:
        transacted_at = transacted_at.replace(tzinfo=timezone.utc)
    return PortfolioTransactionInput(
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        side=transaction.side,
        quantity=float(transaction.quantity),
        price=float(transaction.price),
        fees=float(transaction.fees),
        transacted_at=transacted_at,
    )


def _portfolio_transaction_rows(
    portfolio_id: str, database: Session
) -> list[tuple[PortfolioTransaction, InstrumentRecord]]:
    return list(
        database.execute(
            select(PortfolioTransaction, InstrumentRecord)
            .join(InstrumentRecord, InstrumentRecord.id == PortfolioTransaction.instrument_id)
            .where(PortfolioTransaction.portfolio_id == portfolio_id)
            .order_by(PortfolioTransaction.transacted_at, PortfolioTransaction.id)
        ).all()
    )


def _instrument_for_transaction(
    symbol: str, exchange: str, database: Session
) -> InstrumentRecord:
    instrument = database.scalar(
        select(InstrumentRecord).where(
            InstrumentRecord.symbol == symbol,
            InstrumentRecord.exchange == exchange,
        )
    )
    if instrument:
        return instrument
    instrument = InstrumentRecord(
        symbol=symbol,
        exchange=exchange,
        name=symbol,
        currency="INR",
        data_source="user_entered",
    )
    database.add(instrument)
    database.flush()
    return instrument


@app.post(
    "/api/v1/portfolios",
    response_model=PortfolioResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def create_portfolio(
    payload: CreatePortfolioRequest,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> Portfolio:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Portfolio name cannot be empty")
    portfolio = Portfolio(
        user_id=user.id,
        name=name,
        currency="INR",
        initial_cash=payload.initial_cash,
    )
    database.add(portfolio)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=409, detail="A portfolio with this name already exists"
        ) from error
    database.refresh(portfolio)
    return portfolio


@app.get("/api/v1/portfolios", response_model=list[PortfolioResponse])
def list_portfolios(
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> list[Portfolio]:
    return list(
        database.scalars(
            select(Portfolio)
            .where(Portfolio.user_id == user.id)
            .order_by(Portfolio.created_at.desc())
        )
    )


@app.post(
    "/api/v1/portfolios/{portfolio_id}/transactions",
    response_model=PortfolioTransactionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def create_portfolio_transaction(
    portfolio_id: UUID,
    payload: PortfolioTransactionInput,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> PortfolioTransactionResponse:
    portfolio = _portfolio_for_user(portfolio_id, user, database)
    rows = _portfolio_transaction_rows(portfolio.id, database)
    entries = [_transaction_input(transaction, instrument) for transaction, instrument in rows]
    try:
        calculate_ledger(float(portfolio.initial_cash), [*entries, payload])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    instrument = _instrument_for_transaction(
        payload.symbol, payload.exchange, database
    )
    transaction = PortfolioTransaction(
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        side=payload.side,
        quantity=payload.quantity,
        price=payload.price,
        fees=payload.fees,
        transacted_at=payload.transacted_at,
    )
    database.add(transaction)
    database.commit()
    database.refresh(transaction)
    return PortfolioTransactionResponse(
        id=transaction.id,
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        side=transaction.side,
        quantity=float(transaction.quantity),
        price=float(transaction.price),
        fees=float(transaction.fees),
        transacted_at=transaction.transacted_at.replace(tzinfo=timezone.utc)
        if transaction.transacted_at.tzinfo is None
        else transaction.transacted_at,
    )


@app.get(
    "/api/v1/portfolios/{portfolio_id}/transactions",
    response_model=list[PortfolioTransactionResponse],
)
def list_portfolio_transactions(
    portfolio_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> list[PortfolioTransactionResponse]:
    portfolio = _portfolio_for_user(portfolio_id, user, database)
    rows = _portfolio_transaction_rows(portfolio.id, database)
    return [
        PortfolioTransactionResponse(
            id=transaction.id,
            symbol=instrument.symbol,
            exchange=instrument.exchange,
            side=transaction.side,
            quantity=float(transaction.quantity),
            price=float(transaction.price),
            fees=float(transaction.fees),
            transacted_at=transaction.transacted_at.replace(tzinfo=timezone.utc)
            if transaction.transacted_at.tzinfo is None
            else transaction.transacted_at,
        )
        for transaction, instrument in rows[offset : offset + limit]
    ]


@app.put(
    "/api/v1/portfolios/{portfolio_id}/transactions/{transaction_id}",
    response_model=PortfolioTransactionResponse,
    dependencies=[Depends(verify_request_origin)],
)
def update_portfolio_transaction(
    portfolio_id: UUID,
    transaction_id: UUID,
    payload: PortfolioTransactionInput,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> PortfolioTransactionResponse:
    portfolio = _portfolio_for_user(portfolio_id, user, database)
    target = database.scalar(
        select(PortfolioTransaction).where(
            PortfolioTransaction.id == str(transaction_id),
            PortfolioTransaction.portfolio_id == portfolio.id,
        )
    )
    if not target:
        raise HTTPException(status_code=404, detail="Transaction not found")
    rows = _portfolio_transaction_rows(portfolio.id, database)
    entries = [
        _transaction_input(transaction, instrument)
        for transaction, instrument in rows
        if transaction.id != target.id
    ]
    try:
        calculate_ledger(float(portfolio.initial_cash), [*entries, payload])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    instrument = _instrument_for_transaction(
        payload.symbol, payload.exchange, database
    )
    target.instrument_id = instrument.id
    target.side = payload.side
    target.quantity = payload.quantity
    target.price = payload.price
    target.fees = payload.fees
    target.transacted_at = payload.transacted_at
    database.commit()
    database.refresh(target)
    return PortfolioTransactionResponse(
        id=target.id,
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        side=target.side,
        quantity=float(target.quantity),
        price=float(target.price),
        fees=float(target.fees),
        transacted_at=target.transacted_at.replace(tzinfo=timezone.utc)
        if target.transacted_at.tzinfo is None
        else target.transacted_at,
    )


@app.delete(
    "/api/v1/portfolios/{portfolio_id}/transactions/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_request_origin)],
)
def delete_portfolio_transaction(
    portfolio_id: UUID,
    transaction_id: UUID,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> Response:
    portfolio = _portfolio_for_user(portfolio_id, user, database)
    target = database.scalar(
        select(PortfolioTransaction).where(
            PortfolioTransaction.id == str(transaction_id),
            PortfolioTransaction.portfolio_id == portfolio.id,
        )
    )
    if not target:
        raise HTTPException(status_code=404, detail="Transaction not found")
    rows = _portfolio_transaction_rows(portfolio.id, database)
    entries = [
        _transaction_input(transaction, instrument)
        for transaction, instrument in rows
        if transaction.id != target.id
    ]
    try:
        calculate_ledger(float(portfolio.initial_cash), entries)
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=f"Transaction cannot be removed because the remaining ledger is invalid: {error}",
        ) from error
    database.delete(target)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/api/v1/portfolios/{portfolio_id}/overview",
    response_model=PortfolioOverviewResponse,
)
def portfolio_overview(
    portfolio_id: UUID,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> PortfolioOverviewResponse:
    portfolio = _portfolio_for_user(portfolio_id, user, database)
    rows = _portfolio_transaction_rows(portfolio.id, database)
    inputs = [_transaction_input(transaction, instrument) for transaction, instrument in rows]
    try:
        ledger = calculate_ledger(float(portfolio.initial_cash), inputs)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=f"Portfolio ledger is invalid: {error}") from error

    provider = get_market_data_provider()
    holdings: list[HoldingResponse] = []
    history: dict[str, list[tuple[datetime, float]]] = {}
    weights: dict[str, float] = {}
    data_dates = []
    unavailable_count = 0
    total_market_value = 0.0
    total_unrealized = 0.0
    for instrument_key, state in ledger.holdings.items():
        if state.quantity <= 0:
            continue
        exchange, symbol = instrument_key.split(":", 1)
        instrument = database.scalar(
            select(InstrumentRecord).where(
                InstrumentRecord.exchange == exchange,
                InstrumentRecord.symbol == symbol,
            )
        )
        if not instrument:
            raise HTTPException(
                status_code=409,
                detail=f"Instrument metadata missing for portfolio holding {instrument_key}.",
            )
        last_price = None
        price_as_of = None
        try:
            candles = provider.historical_daily_candles(
                instrument.symbol, instrument.exchange, None, None
            )
        except ProviderUnavailable:
            candles = []
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        candles = candles[-5000:]
        if candles:
            last_price = candles[-1].close
            price_as_of = candles[-1].timestamp
            data_dates.append(price_as_of)
            history[instrument_key] = [
                (candle.timestamp, candle.close) for candle in candles
            ]
            market_value = float(state.quantity) * last_price
            unrealized = (last_price - float(state.average_cost)) * float(state.quantity)
            weights[instrument_key] = market_value
            total_market_value += market_value
            total_unrealized += unrealized
        else:
            unavailable_count += 1
            market_value = None
            unrealized = None
        holdings.append(
            HoldingResponse(
                symbol=instrument.symbol,
                exchange=instrument.exchange,
                quantity=float(state.quantity),
                average_cost=float(state.average_cost),
                historical_last_close=last_price,
                market_value=market_value,
                realized_pnl=float(state.realized_pnl),
                unrealized_pnl=unrealized,
                allocation_percent=None,
                price_status="HISTORICAL" if last_price is not None else "UNAVAILABLE",
                price_as_of=price_as_of,
            )
        )

    all_prices_available = unavailable_count == 0
    total_value = (
        float(ledger.cash_balance) + total_market_value if all_prices_available else None
    )
    if not holdings:
        valuation_status = "CASH_ONLY"
        unrealized_total = 0.0
        total_value = float(ledger.cash_balance)
    elif unavailable_count == 0:
        valuation_status = "HISTORICAL"
        unrealized_total = total_unrealized
    elif unavailable_count < len(holdings):
        valuation_status = "PARTIAL"
        unrealized_total = None
    else:
        valuation_status = "UNAVAILABLE"
        unrealized_total = None

    if total_value is not None and total_value > 0:
        for holding in holdings:
            if holding.market_value is not None:
                holding.allocation_percent = holding.market_value / total_value * 100
    risk = calculate_portfolio_risk(history, weights)
    return PortfolioOverviewResponse(
        portfolio_id=portfolio.id,
        initial_cash=float(portfolio.initial_cash),
        cash_balance=float(ledger.cash_balance),
        cash_allocation_percent=(
            float(ledger.cash_balance) / total_value * 100
            if total_value is not None and total_value > 0
            else None
        ),
        total_value=total_value,
        realized_pnl=float(ledger.realized_pnl),
        unrealized_pnl=unrealized_total,
        valuation_status=valuation_status,
        data_as_of=max(data_dates, default=None),
        holdings=holdings,
        risk=risk,
    )


@app.get("/api/v1/screens", response_model=list[SavedScreenResponse])
def list_saved_screens(
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> list[SavedScreen]:
    return list(
        database.scalars(
            select(SavedScreen)
            .where(SavedScreen.user_id == user.id)
            .order_by(SavedScreen.updated_at.desc())
        )
    )


@app.get("/api/v1/screens/{screen_id}/results", response_model=AdvancedScreenerResponse)
def run_saved_screen(
    screen_id: UUID,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> AdvancedScreenerResponse:
    screen = database.scalar(
        select(SavedScreen).where(
            SavedScreen.id == str(screen_id),
            SavedScreen.user_id == user.id,
        )
    )
    if not screen:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    filters = AdvancedScreenerRequest.model_validate(screen.filters)
    try:
        return screen_historical_instruments(get_market_data_provider(), filters)
    except ProviderUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/v1/screens",
    response_model=SavedScreenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def save_screen(
    payload: SavedScreenRequest,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> SavedScreen:
    screen = SavedScreen(
        user_id=user.id,
        name=payload.name.strip(),
        filters=payload.filters.model_dump(exclude_none=True),
    )
    if not screen.name:
        raise HTTPException(status_code=422, detail="Screen name cannot be empty")
    database.add(screen)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=409, detail="A screen with this name already exists"
        ) from error
    database.refresh(screen)
    return screen


@app.delete(
    "/api/v1/screens/{screen_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_request_origin)],
)
def delete_saved_screen(
    screen_id: UUID,
    user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
) -> Response:
    screen = database.scalar(
        select(SavedScreen).where(
            SavedScreen.id == str(screen_id),
            SavedScreen.user_id == user.id,
        )
    )
    if not screen:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    database.delete(screen)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
