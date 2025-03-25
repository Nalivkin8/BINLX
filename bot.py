import websocket
import json
import asyncio
import os
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramRetryAfter

# 🔹 Переменные среды
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_CHAT_ID:
    raise ValueError("❌ TELEGRAM_CHAT_ID не задан!")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# 🔹 Настройки
PAIR = "IPUSDT"
MIN_TP_SL_PERCENT = 0.005
TP_MULTIPLIER = 5
SL_MULTIPLIER = 3
price_history = {PAIR: []}
active_trades = {}

# 🔹 Статистика
total_trades = 0
tp_count = 0
sl_count = 0

# 🔹 Индикаторы
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

def get_decimal_places(price):
    price_str = f"{price:.10f}".rstrip('0')
    return len(price_str.split('.')[1]) if '.' in price_str else 0

def format_symbol(symbol):
    return symbol.replace("USDT", "/USDT")

# 🔹 Telegram
async def send_message_safe(message):
    try:
        print(f"📤 Telegram: {message}")
        await bot.send_message(TELEGRAM_CHAT_ID, message)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await send_message_safe(message)
    except Exception as e:
        print(f"❌ Ошибка Telegram: {e}")

# 🔹 Обработка команды /отчет
@dp.message(commands=["отчет", "report"])
async def report_handler(message: types.Message):
    global total_trades, tp_count, sl_count
    if total_trades == 0:
        await message.answer("📊 Пока нет завершённых сделок.")
        return

    tp_percent = round((tp_count / total_trades) * 100, 1)
    sl_percent = round((sl_count / total_trades) * 100, 1)

    report = (
        f"📊 Отчет по {format_symbol(PAIR)}\n"
        f"Всего сделок: {total_trades}\n"
        f"🎯 TP: {tp_count} ({tp_percent}%)\n"
        f"⛔ SL: {sl_count} ({sl_percent}%)"
    )
    await message.answer(report)

# 🔹 WebSocket
async def start_futures_websocket():
    while True:
        try:
            print("🔄 Подключение к WebSocket Binance Futures...")
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

# 🔹 Обработка WebSocket сообщений
async def process_futures_message(message):
    global total_trades, tp_count, sl_count

    try:
        data = json.loads(message)
        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            if price <= 0:
                return

            print(f"📊 {symbol}: {price} USDT")

            # TP / SL
            if symbol in active_trades:
                trade = active_trades[symbol]

                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    del active_trades[symbol]
                    total_trades += 1
                    tp_count += 1
                    await send_message_safe(f"✅ **{format_symbol(symbol)} достиг Take Profit ({trade['tp']} USDT)** 🎯")
                    return

                if (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    del active_trades[symbol]
                    total_trades += 1
                    sl_count += 1
                    await send_message_safe(f"❌ **{format_symbol(symbol)} достиг Stop Loss ({trade['sl']} USDT)** ⛔")
                    return

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
            if last_atr < price * 0.001:
                return
            if 48 <= last_rsi <= 52:
                return
            if abs(last_macd - last_signal) < 0.005:
                return

            signal = None
            if last_macd > last_signal and last_rsi < 55:
                signal = "LONG"
            elif last_macd < last_signal and last_rsi > 45:
                signal = "SHORT"

            if signal:
                decimal_places = get_decimal_places(price)
                tp, sl = compute_tp_sl(price, last_atr, signal, decimal_places)

                active_trades[symbol] = {
                    "signal": signal,
                    "entry": price,
                    "tp": tp,
                    "sl": sl
                }

                emoji = "🟢" if signal == "LONG" else "🔴"
                await send_message_safe(
                    f"{emoji} **{signal} {format_symbol(symbol)}**\n"
                    f"🔹 **Вход**: {price:.{decimal_places}f} USDT\n"
                    f"🎯 **TP**: {tp:.{decimal_places}f} USDT\n"
                    f"⛔ **SL**: {sl:.{decimal_places}f} USDT"
                )

    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")

# 🔹 Запуск
async def main():
    print("🚀 Бот запущен (IPUSDT + статистика TP/SL)")
    asyncio.create_task(start_futures_websocket())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
