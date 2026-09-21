from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class RiskConfig(Base):
    __tablename__ = 'risk_configs'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)
    max_order_idr: Mapped[int] = mapped_column(BigInteger, default=settings.max_order_idr)
    max_daily_loss_idr: Mapped[int] = mapped_column(BigInteger, default=settings.max_daily_loss_idr)
    max_open_orders: Mapped[int] = mapped_column(Integer, default=settings.max_open_orders)
    max_position_idr: Mapped[int] = mapped_column(BigInteger, default=settings.max_position_idr)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    emergency_stop: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    client_order_id: Mapped[str] = mapped_column(String(36), unique=True)
    indodax_order_id: Mapped[str | None] = mapped_column(String(64))
    pair: Mapped[str] = mapped_column(String(40))
    side: Mapped[str] = mapped_column(String(4))
    order_type: Mapped[str] = mapped_column(String(12), default='LIMIT')
    price: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    amount: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    filled_amount: Mapped[Decimal] = mapped_column(Numeric(30, 10), default=0)
    status: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Recommendation(Base):
    __tablename__ = 'recommendations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    pair: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(4))
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 10))
    take_profit_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 10))
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 10))
    reason: Mapped[str] = mapped_column(Text)
    raw_response: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    event_type: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(64))
    payload_redacted: Mapped[str] = mapped_column(Text)
    result_redacted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def user_and_risk(session, telegram_user):
    user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
    if user is None:
        user = User(telegram_user_id=telegram_user.id, username=telegram_user.username)
        session.add(user)
        await session.flush()
    risk = await session.scalar(select(RiskConfig).where(RiskConfig.user_id == user.id))
    if risk is None:
        risk = RiskConfig(user_id=user.id)
        session.add(risk)
        await session.flush()
    return user, risk
