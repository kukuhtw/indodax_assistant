from decimal import Decimal, InvalidOperation

from app.config import Settings


class RiskRejected(Exception):
    pass


def positive_decimal(value) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RiskRejected('Angka tidak valid') from exc
    if not number.is_finite() or number <= 0:
        raise RiskRejected('Harga dan jumlah harus positif')
    return number


def validate(settings: Settings, risk, pair: str, side: str, price: Decimal,
             amount: Decimal, pair_info: dict, ticker: dict, balance: dict,
             open_count: int, daily_loss: Decimal = Decimal(0),
             position_value: Decimal = Decimal(0)) -> None:
    if pair not in settings.pairs or not pair_info or pair_info.get('ticker_id') != pair:
        raise RiskRejected('Pair tidak diizinkan')
    if pair_info.get('is_maintenance') or pair_info.get('is_market_suspended'):
        raise RiskRejected('Pasar sedang tidak tersedia')
    if side not in ('BUY', 'SELL'):
        raise RiskRejected('Side tidak valid')
    price, amount = positive_decimal(price), positive_decimal(amount)
    if risk.is_paused or risk.emergency_stop:
        raise RiskRejected('Trading sedang dihentikan')
    value = price * amount
    if value > risk.max_order_idr:
        raise RiskRejected('Nilai order melebihi batas')
    if value < Decimal(str(pair_info.get('trade_min_base_currency', 0))):
        raise RiskRejected('Nilai order di bawah minimum pasar')
    if amount < Decimal(str(pair_info.get('trade_min_traded_currency', 0))):
        raise RiskRejected('Jumlah koin di bawah minimum pasar')
    increment = positive_decimal(pair_info.get('quantity_increment', '0.00000001'))
    tick = positive_decimal(pair_info.get('price_precision', '1'))
    if amount % increment or price % tick:
        raise RiskRejected('Harga atau jumlah tidak sesuai increment pasar')
    last = positive_decimal(ticker['last'])
    if abs(price - last) / last > Decimal('0.20'):
        raise RiskRejected('Harga menyimpang lebih dari 20% dari harga terakhir')
    if open_count >= risk.max_open_orders:
        raise RiskRejected('Batas open order tercapai')
    if daily_loss >= risk.max_daily_loss_idr:
        raise RiskRejected('Batas kerugian harian tercapai')
    coin, base = pair.split('_')
    if side == 'BUY':
        if value > Decimal(str(balance.get(base, 0))):
            raise RiskRejected('Saldo IDR tidak cukup')
        if position_value + value > risk.max_position_idr:
            raise RiskRejected('Batas posisi tercapai')
    elif amount > Decimal(str(balance.get(coin, 0))):
        raise RiskRejected('Saldo koin tidak cukup')
