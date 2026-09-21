from decimal import Decimal

import pytest

from app.ai.advisor import Advice
from app.config import Settings
from app.indodax.client import sign
from app.trading.risk import RiskRejected, validate


class Risk:
    is_paused = False
    emergency_stop = False
    max_order_idr = 1_000_000
    max_daily_loss_idr = 100_000
    max_open_orders = 5
    max_position_idr = 2_000_000


def test_signature():
    assert len(sign('method=getInfo&timestamp=123', 'secret')) == 128
    assert sign('a=1', 'secret') != sign('a=2', 'secret')


def test_risk_accepts_and_rejects():
    args = (Settings(), Risk(), 'btc_idr', 'BUY', Decimal('100000000'),
            Decimal('0.001'), {'ticker_id': 'btc_idr', 'trade_min_base_currency': 50000,
                               'quantity_increment': '0.00000001', 'price_precision': 1000},
            {'last': '100000000'}, {'idr': '1000000'}, 0)
    validate(*args)
    with pytest.raises(RiskRejected):
        validate(*args[:5], Decimal('0.02'), *args[6:])
    Risk.is_paused = True
    with pytest.raises(RiskRejected):
        validate(*args)
    Risk.is_paused = False


def test_ai_schema_rejects_bad_stop():
    with pytest.raises(ValueError):
        Advice(action='BUY', confidence=.7, entry_price=100,
               take_profit_price=110, stop_loss_price=105, suggested_amount=1,
               risk_level='LOW', reason='test', invalidating_conditions=[])
