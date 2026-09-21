import json
from decimal import Decimal
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import Settings


class Advice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['BUY', 'SELL', 'HOLD']
    confidence: float = Field(ge=0, le=1)
    entry_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    suggested_amount: Decimal | None = None
    risk_level: Literal['LOW', 'MEDIUM', 'HIGH']
    reason: str
    invalidating_conditions: list[str]

    @model_validator(mode='after')
    def valid_prices(self):
        if self.action != 'HOLD':
            if not all(x is not None and x > 0 for x in (
                self.entry_price, self.take_profit_price, self.stop_loss_price,
                self.suggested_amount,
            )):
                raise ValueError('Harga dan jumlah harus positif')
            if self.action == 'BUY' and not (self.stop_loss_price < self.entry_price < self.take_profit_price):
                raise ValueError('Harga BUY tidak konsisten')
            if self.action == 'SELL' and not (self.take_profit_price < self.entry_price < self.stop_loss_price):
                raise ValueError('Harga SELL tidak konsisten')
        return self


def hold(reason: str) -> Advice:
    return Advice(action='HOLD', confidence=0, risk_level='HIGH', reason=reason,
                  invalidating_conditions=[])


async def recommend(settings: Settings, market: dict) -> tuple[Advice, str]:
    if not settings.openai_api_key:
        return hold('OpenAI API belum dikonfigurasi'), '{}'
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model, response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': 'Berikan hanya JSON rekomendasi BUY/SELL/HOLD dengan action, confidence, entry_price, take_profit_price, stop_loss_price, suggested_amount, risk_level, reason, invalidating_conditions. Tidak ada jaminan profit. Pertimbangkan volatilitas, likuiditas, slippage dan risiko koneksi/API. Anda tidak dapat mengeksekusi order.'},
                {'role': 'user', 'content': json.dumps(market)},
            ],
        )
        raw = response.choices[0].message.content or '{}'
        advice = Advice.model_validate_json(raw)
        if advice.confidence < settings.min_confidence:
            return hold('Confidence di bawah batas: ' + advice.reason), raw
        return advice, raw
    except Exception:
        return hold('Rekomendasi AI tidak tersedia atau tidak valid'), '{}'
