import asyncio
import hashlib
import hmac
import time
from decimal import Decimal
from urllib.parse import urlencode

import httpx

from app.config import Settings


class BrokerError(Exception):
    pass


class UnknownSubmission(BrokerError):
    pass


def sign(body: str, secret: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha512).hexdigest()


class IndodaxClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.settings = settings
        self.http = http
        self.lock = asyncio.Lock()
        self.last_request = 0.0

    async def public(self, path: str):
        response = await self.http.get(self.settings.indodax_base_url + path)
        response.raise_for_status()
        return response.json()

    async def pairs(self):
        return await self.public('/api/pairs')

    async def pair_info(self, pair: str):
        return next((p for p in await self.pairs() if p['ticker_id'] == pair), None)

    async def ticker(self, pair: str):
        info = await self.pair_info(pair)
        if not info:
            raise BrokerError('Pair tidak ditemukan')
        return (await self.public('/api/ticker/' + info['id']))['ticker']

    async def order_book(self, pair: str):
        info = await self.pair_info(pair)
        if not info:
            raise BrokerError('Pair tidak ditemukan')
        return await self.public('/api/depth/' + info['id'])

    async def private(self, method: str, **params):
        if not self.settings.indodax_api_key or not self.settings.indodax_secret_key:
            raise BrokerError('Kredensial Indodax belum diatur')
        async with self.lock:
            delay = 0.12 - (time.monotonic() - self.last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            payload = {'method': method, 'timestamp': int(time.time() * 1000),
                       'recvWindow': self.settings.indodax_recv_window, **params}
            body = urlencode(payload)
            self.last_request = time.monotonic()
            try:
                response = await self.http.post(
                    self.settings.indodax_base_url + '/tapi', content=body,
                    headers={'Key': self.settings.indodax_api_key,
                             'Sign': sign(body, self.settings.indodax_secret_key),
                             'Content-Type': 'application/x-www-form-urlencoded'},
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if method == 'trade':
                    raise UnknownSubmission('Status order tidak diketahui; periksa client_order_id') from exc
                raise BrokerError('Koneksi Indodax gagal') from exc
            if response.status_code == 429:
                raise BrokerError('Rate limit Indodax; tunggu sebelum mencoba lagi')
            response.raise_for_status()
            data = response.json()
            if data.get('success') != 1:
                raise BrokerError(str(data.get('error', 'Indodax menolak permintaan')))
            return data['return']

    async def get_info(self):
        return await self.private('getInfo')

    async def open_orders(self, pair: str):
        return await self.private('openOrders', pair=pair)

    async def get_order(self, pair: str, order_id: int):
        return await self.private('getOrder', pair=pair, order_id=order_id)

    async def get_by_client_id(self, client_order_id: str):
        return await self.private('getOrderByClientOrderId', client_order_id=client_order_id)

    async def trade_limit(self, pair: str, side: str, price: Decimal,
                          amount: Decimal, client_order_id: str):
        coin = pair.split('_')[0]
        return await self.private('trade', pair=pair, type=side.lower(),
                                  price=str(price), **{coin: str(amount)},
                                  order_type='limit', client_order_id=client_order_id)

    async def cancel(self, pair: str, order_id: int, side: str):
        return await self.private('cancelOrder', pair=pair, order_id=order_id,
                                  type=side.lower(), order_type='limit')
