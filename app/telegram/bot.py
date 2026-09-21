from decimal import ROUND_DOWN, Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, TypeHandler

from app.ai.advisor import recommend
from app.config import settings
from app.database import Order, Recommendation, Session, user_and_risk
from app.indodax.client import BrokerError, IndodaxClient
from app.trading.risk import RiskRejected, positive_decimal
from app.trading.service import audit, confirm, prepare


START = (
    '🤖 <b>Indodax AI Trading Assistant</b>\n'
    'Mode default: <b>DRY-RUN</b> (simulasi, tidak ada dana nyata terpakai).\n\n'
    'Bot ini <b>bukan nasihat keuangan</b> dan tidak menjanjikan keuntungan. '
    'Rekomendasi AI dapat salah; trading memiliki risiko volatilitas, likuiditas, slippage, dan gangguan API.\n\n'
    'Ketik /help untuk panduan lengkap perintah.'
)

HELP = (
    '📖 <b>Panduan Perintah</b>\n\n'

    '📊 <b>Data Pasar</b>\n'
    '/price [pair] — harga terakhir\n'
    '   <i>contoh:</i> /price btc_idr\n'
    '/orderbook [pair] — 3 bid &amp; ask teratas\n'
    '   <i>contoh:</i> /orderbook btc_idr\n'
    '/recommend [pair] — rekomendasi AI (BUY/SELL/HOLD)\n'
    '   <i>contoh:</i> /recommend btc_idr\n\n'

    '💰 <b>Akun</b>\n'
    '/balance atau /portfolio — saldo akun Indodax\n'
    '/orders — 10 order terakhir Anda\n'
    '/order [pair] [id] — detail satu order\n'
    '   <i>contoh:</i> /order btc_idr 42\n\n'

    '🛒 <b>Order</b> (wajib konfirmasi lewat tombol)\n'
    '/buy [pair] [harga] [jumlah]\n'
    '/sell [pair] [harga] [jumlah]\n'
    '   <i>contoh:</i> /buy btc_idr 950000000 0.0005\n'
    'Atau tentukan nominal Rupiah, jumlah koin dihitung otomatis:\n'
    '/buy [pair] [harga] idr [nominal]\n'
    '   <i>contoh:</i> /buy btc_idr 950000000 idr 500000\n'
    '/cancel [pair] [id] — batalkan order dry-run\n\n'

    '⚠️ <b>Manajemen Risiko</b>\n'
    '/risk — lihat batas risiko Anda saat ini\n'
    '/setrisk [nilai_idr] — ubah batas nilai order maksimum\n'
    '   <i>contoh:</i> /setrisk 500000\n\n'

    '🛑 <b>Kontrol</b>\n'
    '/pause — jeda order baru sementara\n'
    '/resume — lanjutkan setelah /pause\n'
    '/stop — EMERGENCY STOP (tidak bisa di-resume lewat bot)\n'
    '/status — mode &amp; status saat ini\n\n'

    'ℹ️ Order selalu <b>DRY-RUN</b> (simulasi) sampai fitur live trading selesai diuji. '
    'Bukan nasihat keuangan; segala keputusan trading adalah risiko Anda sendiri.'
)

COMMAND_LIST = [
    ('start', 'Mulai & info bot'),
    ('help', 'Panduan lengkap perintah'),
    ('status', 'Mode & status saat ini'),
    ('price', 'Harga pair, mis: /price btc_idr'),
    ('orderbook', 'Order book, mis: /orderbook btc_idr'),
    ('balance', 'Saldo akun Indodax'),
    ('portfolio', 'Sama seperti /balance'),
    ('recommend', 'Rekomendasi AI, mis: /recommend btc_idr'),
    ('buy', 'Order beli: /buy [pair] [harga] [jumlah] atau idr [nominal]'),
    ('sell', 'Order jual: /sell [pair] [harga] [jumlah] atau idr [nominal]'),
    ('orders', '10 order terakhir Anda'),
    ('order', 'Detail order: /order [pair] [id]'),
    ('cancel', 'Batalkan order dry-run: /cancel [pair] [id]'),
    ('risk', 'Lihat batas risiko Anda'),
    ('setrisk', 'Ubah batas order: /setrisk [nilai_idr]'),
    ('pause', 'Jeda order baru sementara'),
    ('resume', 'Lanjutkan setelah /pause'),
    ('stop', 'EMERGENCY STOP (tidak bisa di-resume)'),
]


def dependencies(context):
    return context.application.bot_data['broker'], context.application.bot_data['redis']


async def authorize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None or user.id not in settings.allowed_ids:
        if update.callback_query:
            await update.callback_query.answer('Akses ditolak.', show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text('Akses ditolak.')
        raise PermissionError('unauthorized')


def protected(fn):
    async def wrapper(update, context):
        try:
            await authorize(update, context)
            await fn(update, context)
        except PermissionError:
            pass
        except (RiskRejected, BrokerError, ValueError, IndexError) as exc:
            await update.effective_message.reply_text(str(exc))
    return wrapper


@protected
async def start(update, context):
    await update.effective_message.reply_text(START, parse_mode='HTML')


@protected
async def help_command(update, context):
    await update.effective_message.reply_text(HELP, parse_mode='HTML')


@protected
async def status(update, context):
    async with Session.begin() as session:
        _, risk = await user_and_risk(session, update.effective_user)
        await update.effective_message.reply_text(
            f'Mode: {"LIVE" if settings.live else "DRY-RUN"}; pause={risk.is_paused}; stop={risk.emergency_stop}')


def pair_arg(context):
    pair = context.args[0].lower()
    if pair not in settings.pairs:
        raise RiskRejected('Pair tidak diizinkan')
    return pair


@protected
async def price(update, context):
    broker, _ = dependencies(context)
    pair = pair_arg(context)
    ticker = await broker.ticker(pair)
    await update.effective_message.reply_text(f'{pair.upper()}: Rp{ticker["last"]}')


@protected
async def orderbook(update, context):
    broker, _ = dependencies(context)
    book = await broker.order_book(pair_arg(context))
    await update.effective_message.reply_text(f'Bids: {book.get("buy", [])[:3]}\nAsks: {book.get("sell", [])[:3]}')


@protected
async def balance(update, context):
    broker, _ = dependencies(context)
    data = await broker.get_info()
    await update.effective_message.reply_text('Saldo tersedia: ' + str(data.get('balance', {})))


@protected
async def recommend_command(update, context):
    broker, _ = dependencies(context)
    pair = pair_arg(context)
    ticker = await broker.ticker(pair)
    advice, raw = await recommend(settings, {'pair': pair, 'last_price': ticker['last'],
                                             'buy_price': ticker['buy'], 'sell_price': ticker['sell'],
                                             'high_24h': ticker['high'], 'low_24h': ticker['low'],
                                             'volume_24h': ticker.get('vol_idr')})
    async with Session.begin() as session:
        user, _ = await user_and_risk(session, update.effective_user)
        session.add(Recommendation(user_id=user.id, pair=pair, action=advice.action,
                                   confidence=Decimal(str(advice.confidence)),
                                   entry_price=advice.entry_price,
                                   take_profit_price=advice.take_profit_price,
                                   stop_loss_price=advice.stop_loss_price,
                                   reason=advice.reason, raw_response=raw))
    await update.effective_message.reply_text(
        f'{pair.upper()} {advice.action} ({advice.confidence:.2f})\n{advice.reason}\n'
        'Bukan jaminan profit; rekomendasi dapat salah. Risiko volatilitas, likuiditas, slippage, dan API/koneksi.')


async def order_command(update, context, side):
    args = context.args
    if len(args) not in (3, 4) or (len(args) == 4 and args[2].lower() != 'idr'):
        raise RiskRejected(
            f'Format: /{side.lower()} <pair> <harga> <jumlah>\n'
            f'atau: /{side.lower()} <pair> <harga> idr <nominal>')
    pair = pair_arg(context)
    auto_note = ''
    if len(args) == 3:
        price_value = positive_decimal(args[1])
        amount_value = positive_decimal(args[2])
    else:
        broker, _ = dependencies(context)
        price_value = positive_decimal(args[1])
        nominal_value = positive_decimal(args[3])
        info = await broker.pair_info(pair)
        if not info:
            raise RiskRejected('Pair tidak ditemukan')
        increment = positive_decimal(info.get('quantity_increment', '0.00000001'))
        steps = (nominal_value / price_value / increment).to_integral_value(rounding=ROUND_DOWN)
        amount_value = steps * increment
        if amount_value <= 0:
            raise RiskRejected('Nominal terlalu kecil untuk menghasilkan jumlah minimum pair ini')
        auto_note = f'\n(Jumlah dihitung otomatis dari nominal Rp{nominal_value})'
    order_id = await prepare(update.effective_user, pair, side, price_value, amount_value)
    mode = 'LIVE' if settings.live else 'DRY-RUN'
    warning = '\nPERINGATAN: LIVE ORDER menggunakan dana nyata.' if settings.live else ''
    await update.effective_message.reply_text(
        f'Konfirmasi Order #{order_id}\n{side} {pair.upper()}\nHarga: Rp{price_value}\n'
        f'Jumlah: {amount_value}{auto_note}\nNilai: Rp{price_value * amount_value}\nMode: {mode}{warning}',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton('CONFIRM', callback_data=f'confirm:{order_id}'),
            InlineKeyboardButton('CANCEL', callback_data=f'cancel:{order_id}'),
        ]]))


@protected
async def buy(update, context):
    await order_command(update, context, 'BUY')


@protected
async def sell(update, context):
    await order_command(update, context, 'SELL')


@protected
async def callback(update, context):
    query = update.callback_query
    await query.answer()
    action, raw_id = query.data.split(':')
    order_id = int(raw_id)
    if action == 'confirm':
        broker, redis = dependencies(context)
        result = await confirm(update.effective_user, order_id, settings, broker, redis)
    else:
        async with Session.begin() as session:
            user, _ = await user_and_risk(session, update.effective_user)
            order = await session.get(Order, order_id, with_for_update=True)
            if not order or order.user_id != user.id or order.status != 'PENDING_CONFIRMATION':
                raise RiskRejected('Order tidak dapat dibatalkan')
            order.status = 'CANCELLED'
            audit(session, user.id, 'order_cancelled', {'order_id': order_id}, 'CANCELLED')
        result = 'Konfirmasi dibatalkan.'
    await query.edit_message_text(result)


@protected
async def orders(update, context):
    async with Session.begin() as session:
        user, _ = await user_and_risk(session, update.effective_user)
        rows = (await session.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).limit(10))).all()
    lines = [f'#{o.id} {o.side} {o.pair} {o.status} {o.mode}' for o in rows]
    await update.effective_message.reply_text('\n'.join(lines) or 'Belum ada order.')


@protected
async def order_detail(update, context):
    pair = pair_arg(context)
    order_id = int(context.args[1])
    async with Session.begin() as session:
        user, _ = await user_and_risk(session, update.effective_user)
        order = await session.get(Order, order_id)
        if not order or order.user_id != user.id or order.pair != pair:
            raise RiskRejected('Order tidak ditemukan')
    await update.effective_message.reply_text(
        f'#{order.id} {order.side} {order.pair} {order.status} {order.mode}\n'
        f'Harga {order.price}; jumlah {order.amount}; broker ID {order.indodax_order_id or "-"}')


@protected
async def cancel_order(update, context):
    pair = pair_arg(context)
    order_id = int(context.args[1])
    async with Session.begin() as session:
        user, _ = await user_and_risk(session, update.effective_user)
        order = await session.get(Order, order_id, with_for_update=True)
        if not order or order.user_id != user.id or order.pair != pair:
            raise RiskRejected('Order tidak ditemukan')
        if order.mode == 'LIVE':
            raise RiskRejected('Pembatalan live belum tersedia; gunakan antarmuka Indodax')
        if order.status not in ('OPEN', 'PENDING_CONFIRMATION'):
            raise RiskRejected('Order tidak dapat dibatalkan')
        order.status = 'CANCELLED'
        audit(session, user.id, 'order_cancelled', {'order_id': order_id}, 'CANCELLED')
    await update.effective_message.reply_text('Order dry-run dibatalkan.')


@protected
async def risk_command(update, context):
    async with Session.begin() as session:
        _, risk = await user_and_risk(session, update.effective_user)
        await update.effective_message.reply_text(f'Max order Rp{risk.max_order_idr}; max loss Rp{risk.max_daily_loss_idr}; max open {risk.max_open_orders}; max position Rp{risk.max_position_idr}')


@protected
async def setrisk(update, context):
    value = int(context.args[0])
    if value <= 0 or value > settings.max_order_idr:
        raise RiskRejected('Batas harus positif dan tidak melebihi batas sistem')
    async with Session.begin() as session:
        user, risk = await user_and_risk(session, update.effective_user)
        risk.max_order_idr = value
        audit(session, user.id, 'risk_changed', {'max_order_idr': value})
    await update.effective_message.reply_text('Batas order diperbarui.')


async def change_pause(update, paused=False, stopped=False):
    async with Session.begin() as session:
        user, risk = await user_and_risk(session, update.effective_user)
        risk.is_paused = paused
        if stopped:
            risk.emergency_stop = True
        audit(session, user.id, 'emergency_stop' if stopped else 'pause_changed',
              {'paused': paused, 'emergency_stop': risk.emergency_stop})
    await update.effective_message.reply_text('EMERGENCY STOP AKTIF. Open order tidak otomatis dibatalkan. Gunakan /orders.' if stopped else f'Pause: {paused}')


@protected
async def pause(update, context):
    await change_pause(update, paused=True)


@protected
async def resume(update, context):
    async with Session.begin() as session:
        _, risk = await user_and_risk(session, update.effective_user)
        if risk.emergency_stop:
            raise RiskRejected('Emergency stop aktif; restart administrasi diperlukan')
    await change_pause(update)


@protected
async def stop(update, context):
    await change_pause(update, paused=True, stopped=True)


def build_bot(broker: IndodaxClient, redis: Redis):
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data.update(broker=broker, redis=redis)
    for name, handler in {'start': start, 'help': help_command, 'status': status,
                          'price': price, 'orderbook': orderbook, 'balance': balance,
                          'portfolio': balance, 'recommend': recommend_command,
                          'buy': buy, 'sell': sell, 'orders': orders,
                          'order': order_detail, 'cancel': cancel_order,
                          'risk': risk_command, 'setrisk': setrisk, 'pause': pause,
                          'resume': resume, 'stop': stop}.items():
        app.add_handler(CommandHandler(name, handler))
    app.add_handler(CallbackQueryHandler(callback, pattern=r'^(confirm|cancel):\d+$'))
    return app
