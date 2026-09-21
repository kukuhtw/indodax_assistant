import json
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.config import Settings
from app.database import AuditLog, Order, Session, user_and_risk
from app.indodax.client import IndodaxClient
from app.trading.risk import RiskRejected, validate


def audit(session, user_id, event, payload, result=''):
    session.add(AuditLog(user_id=user_id, event_type=event, request_id=uuid.uuid4().hex,
                         payload_redacted=json.dumps(payload, default=str),
                         result_redacted=str(result)))


async def prepare(tg_user, pair: str, side: str, price: Decimal, amount: Decimal):
    async with Session.begin() as session:
        user, risk = await user_and_risk(session, tg_user)
        order = Order(user_id=user.id, client_order_id=uuid.uuid4().hex,
                      pair=pair, side=side, price=price, amount=amount,
                      status='PENDING_CONFIRMATION', mode='DRY_RUN')
        session.add(order)
        await session.flush()
        audit(session, user.id, 'order_requested', {'order_id': order.id, 'pair': pair,
                                                    'side': side, 'price': price, 'amount': amount})
        return order.id


async def confirm(tg_user, order_id: int, settings: Settings, broker: IndodaxClient, redis):
    lock = redis.lock(f'order:{order_id}', timeout=60, blocking_timeout=2)
    if not await lock.acquire():
        raise RiskRejected('Order sedang diproses')
    try:
        async with Session.begin() as session:
            user, risk = await user_and_risk(session, tg_user)
            order = await session.get(Order, order_id, with_for_update=True)
            if not order or order.user_id != user.id or order.status != 'PENDING_CONFIRMATION':
                raise RiskRejected('Konfirmasi tidak valid atau sudah diproses')
            order.status = 'VALIDATING'
            info = await broker.pair_info(order.pair)
            ticker = await broker.ticker(order.pair)
            if settings.dry_run:
                balance = {'idr': '999999999999', order.pair.split('_')[0]: '999999999999'}
                open_count = 0
            else:
                if not settings.live:
                    raise RiskRejected('Live trading tidak diaktifkan secara lengkap')
                raise RiskRejected('Live trading dikunci: pengukuran daily loss dan posisi riil belum tersedia')
            local_open = await session.scalar(select(func.count(Order.id)).where(
                Order.user_id == user.id, Order.status.in_(['OPEN', 'SUBMITTING', 'UNKNOWN'])))
            validate(settings, risk, order.pair, order.side, order.price, order.amount,
                     info, ticker, balance, max(open_count, local_open or 0))
            order.status = 'OPEN'
            order.mode = 'DRY_RUN'
            audit(session, user.id, 'order_dry_run', {'order_id': order.id}, 'OPEN')
            return 'DRY-RUN order tercatat. Tidak ada order nyata yang dikirim.'
    finally:
        await lock.release()
