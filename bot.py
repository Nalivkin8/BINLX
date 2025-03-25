import websocket
import json
import asyncio
import os
import pandas as pd
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramRetryAfter

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
router = Router()

PAIR = "ETHUSDT"
MIN_TP_SL_PERCENT = 0.005
TP_MULTIPLIER = 5
SL_MULTIPLIER = 3
ATR_MIN = 0.002
ATR_MAX = 0.05

price_history = {PAIR: []}
active_trades = {}

total_trades = 0
tp_count = 0
sl_count = 0

def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))

def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window, adjust=False).mean()
    long_ema = prices.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

def compute_atr(prices, period=14):
    tr = prices.diff().abs()
    atr = tr.rolling(window=period).mean()
    return atr

def compute_tp_sl(price, atr, signal, decimal_places):
    if pd.isna(atr) or atr == 0:
        atr = price * 0.002
    min_tp_sl = price * MIN_TP_SL_PERCENT
    tp = price + max(TP_MULTIPLIER * atr, min_tp_sl) if signal == "LONG" else price - max(TP_MULTIPLIER * atr, min_tp_sl)
    sl = price - max(SL_MULTIPLIER * atr, min_tp_sl) if signal == "LONG" else price + max(SL_MULTIPLIER * atr, min_tp_sl)
    return round(tp, decimal_places), round(sl, decimal_places)

def get_decimal_places_from_string(price_str):
    if '.' in price_str:
        return len(price_str.split('.')[1])
    return 0

def format_symbol(symbol):
    return symbol.replace("USDT", "/USDT")

def get_trade_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Вышел по TP", callback_data="manual_tp"),
         InlineKeyboardButton(text="❌ Вышел по SL", callback_data="manual_sl")]
    ])

async def send_message_safe(message, reply_markup=None):
    try:
        sent = await bot.send_message(TELEGRAM_CHAT_ID, message, reply_markup=reply_markup)
        return sent.message_id
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        return await send_message_safe(message, reply_markup)
    except Exception as e:
        print(f"❌ Ошибка Telegram: {e}")

@router.message(Command(commands=["отчет", "report"]))
async def report_handler(message: types.Message):
    if total_trades == 0:
        await message.answer("📊 Пока нет завершённых сделок.")
        return
    tp_percent = round((tp_count / total_trades) * 100, 1)
    sl_percent = round((sl_count / total_trades) * 100, 1)
    report = (
        f"📊 Отчет по {format_symbol(PAIR)}
"
        f"Всего сделок: {total_trades}
"
        f"🎯 TP: {tp_count} ({tp_percent}%)
"
        f"⛔ SL: {sl_count} ({sl_percent}%)"
    )
    await message.answer(report)

@router.callback_query(F.data.in_({"manual_tp", "manual_sl"}))
async def manual_exit_handler(callback: types.CallbackQuery):
    global total_trades, tp_count, sl_count
    trade = active_trades.get(PAIR)
    if trade:
        if callback.data == "manual_tp":
            tp_count += 1
            text = f"✅ Сделка по {format_symbol(PAIR)} вручную закрыта как TP"
        else:
            sl_count += 1
            text = f"❌ Сделка по {format_symbol(PAIR)} вручную закрыта как SL"
        total_trades += 1
        del active_trades[PAIR]
        await bot.edit_message_reply_markup(callback.message.chat.id, callback.message.message_id, reply_markup=None)
        await callback.message.answer(text)
    await callback.answer()

async def start_futures_websocket():
    while True:
        try:
            loop = asyncio.get_event_loop()
            ws = websocket.WebSocketApp(
                "wss://fstream.binance.com/ws",
                on_message=lambda ws, msg: loop.create_task(process_futures_message(msg)),
                on_open=lambda ws: ws.send(json.dumps({
                    "method": "SUBSCRIBE",
                    "params": [f"{PAIR.lower()}@trade"],
                    "id": 1
                }))
            )
            await asyncio.to_thread(ws.run_forever)
        except Exception as e:
            print(f"❌ WebSocket ошибка: {e}")
            await asyncio.sleep(5)

async def process_futures_message(message):
    global total_trades, tp_count, sl_count

    try:
        data = json.loads(message)
        if 's' in data and 'p' in data:
            symbol = data['s']
            price_str = data['p']
            price = float(price_str)
            decimal_places = get_decimal_places_from_string(price_str)
            if price <= 0:
                return
            price_history[symbol].append(price)
            if len(price_history[symbol]) > 50:
                price_history[symbol].pop(0)

            df = pd.DataFrame(price_history[symbol], columns=['close'])
            if len(df) < 14:
                return
            df['RSI'] = compute_rsi(df['close'])
            df['MACD'], df['Signal_Line'] = compute_macd(df['close'])
            df['ATR'] = compute_atr(df['close'])

            last_rsi = df['RSI'].iloc[-1]
            last_macd = df['MACD'].iloc[-1]
            last_signal = df['Signal_Line'].iloc[-1]
            last_atr = df['ATR'].iloc[-1]

            if pd.isna(last_rsi) or pd.isna(last_macd) or pd.isna(last_signal) or pd.isna(last_atr):
                return

            if symbol in active_trades:
                trade = active_trades[symbol]
                if (trade["signal"] == "LONG" and price >= trade["tp"]) or                    (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    del active_trades[symbol]
                    total_trades += 1
                    tp_count += 1
                    await send_message_safe(f"✅ {format_symbol(symbol)} достиг TP ({trade['tp']:.{decimal_places}f} USDT)")
                    return
                if (trade["signal"] == "LONG" and price <= trade["sl"]) or                    (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    del active_trades[symbol]
                    total_trades += 1
                    sl_count += 1
                    await send_message_safe(f"❌ {format_symbol(symbol)} достиг SL ({trade['sl']:.{decimal_places}f} USDT)")
                    return
                if not trade.get("trend_warning_sent"):
                    if trade["signal"] == "LONG" and last_macd < last_signal and (last_signal - last_macd) > 0.002 and last_rsi > 55:
                        await send_message_safe(f"⚠️ Возможна смена тренда на SHORT для {format_symbol(symbol)}")
                        trade["trend_warning_sent"] = True
                    elif trade["signal"] == "SHORT" and last_macd > last_signal and (last_macd - last_signal) > 0.002 and last_rsi < 45:
                        await send_message_safe(f"⚠️ Возможна смена тренда на LONG для {format_symbol(symbol)}")
                        trade["trend_warning_sent"] = True
                return

            if last_atr < ATR_MIN or last_atr > ATR_MAX or abs(last_macd - last_signal) < 0.002:
                return

            signal = None
            if last_macd > last_signal and last_rsi < 60:
                signal = "LONG"
            elif last_macd < last_signal and last_rsi > 40:
                signal = "SHORT"
            if not signal:
                return

            tp, sl = compute_tp_sl(price, last_atr, signal, decimal_places)
            emoji = "🟢" if signal == "LONG" else "🔴"
            msg_text = (
                f"{emoji} **{signal} {format_symbol(symbol)}**
"
                f"🔹 Вход: {price:.{decimal_places}f} USDT
"
                f"🎯 TP: {tp:.{decimal_places}f} USDT
"
                f"⛔ SL: {sl:.{decimal_places}f} USDT"
            )
            message_id = await send_message_safe(msg_text, reply_markup=get_trade_keyboard())
            active_trades[symbol] = {
                "signal": signal,
                "entry": price,
                "tp": tp,
                "sl": sl,
                "trend_warning_sent": False,
                "message_id": message_id
            }

    except Exception as e:
        print(f"❌ Ошибка: {e}")

async def main():
    dp.include_router(router)
    asyncio.create_task(start_futures_websocket())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
