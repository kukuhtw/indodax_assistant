from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import settings
from app.database import Session
from app.indodax.client import IndodaxClient
from app.telegram.bot import build_bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=8) as http:
        redis = Redis.from_url(settings.redis_url)
        broker = IndodaxClient(settings, http)
        bot = None
        if settings.telegram_bot_token and settings.allowed_ids:
            bot = build_bot(broker, redis)
            await bot.initialize()
            await bot.start()
            await bot.updater.start_polling()
        app.state.broker = broker
        app.state.redis = redis
        try:
            yield
        finally:
            if bot:
                await bot.updater.stop()
                await bot.stop()
                await bot.shutdown()
            await redis.aclose()


app = FastAPI(lifespan=lifespan)


@app.get('/health')
async def health():
    return {'status': 'ok', 'trading_enabled': settings.live}


@app.get('/ready')
async def ready():
    result = {'database': 'unreachable', 'redis': 'unreachable', 'indodax': 'unreachable',
              'trading_enabled': settings.live}
    try:
        async with Session() as session:
            await session.execute(text('SELECT 1'))
            result['database'] = 'reachable'
    except Exception:
        pass
    try:
        await app.state.redis.ping()
        result['redis'] = 'reachable'
    except Exception:
        pass
    try:
        await app.state.broker.public('/api/server_time')
        result['indodax'] = 'reachable'
    except Exception:
        pass
    result['status'] = 'ok' if all(result[k] == 'reachable' for k in ('database', 'redis', 'indodax')) else 'degraded'
    return result
