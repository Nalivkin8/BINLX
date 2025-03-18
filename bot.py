import asyncio
import json
import os
import pandas as pd
import websockets
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter

# 🔹 Загружаем переменные среды из Railway Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ Ошибка: TELEGRAM_BOT_TOKEN не задан в Railway Variables!")
if not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Ошибка: TELEGRAM_CHAT_ID не задан в Railway Variables!")

# 🔹 Создаём бота и диспетчер
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# 🔹 Храним активные сделки
active_trades = {}  
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": [], "ETHUSDT": []}

# 🔹 Подключение к WebSocket Binance Futures
async def start_futures_websocket():
    url = "wss://fstream.binance.com/ws"
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": [
            "tstusdt@kline_1m", "tstusdt@kline_15m", "tstusdt@kline_30m", "tstusdt@kline_1h",
            "ipusdt@kline_1m", "ipusdt@kline_15m", "ipusdt@kline_30m", "ipusdt@kline_1h",
            "adausdt@kline_1m", "adausdt@kline_15m", "adausdt@kline_30m", "adausdt@kline_1h",
            "ethusdt@kline_1m", "ethusdt@kline_15m", "ethusdt@kline_30m", "ethusdt@kline_1h"
        ],
        "id": 1
    })

    async with websockets.connect(url) as ws:
        await ws.send(subscribe_message)
        print("📩 Подписка на Binance Futures (свечи)")

        async for message in ws:
            await process_futures_message(message)

# 🔹 Обрабатываем входящие данные WebSocket
async def process_futures_message(message):
    global active_trades, price_history
    try:
        data = json.loads(message)

        if 'k' in data:
            candle = data['k']
            symbol = data['s']
            close_price = float(candle['c'])  # Цена закрытия

            print(f"📊 {symbol}: Закрытие свечи {close_price} USDT")

            if symbol in price_history:
                price_history[symbol].append(close_price)

                if len(price_history[symbol]) > 50:
                    price_history[symbol].pop(0)

                df = pd.DataFrame(price_history[symbol], columns=['close'])
                df['ATR'] = compute_atr(df)
                df['RSI'] = compute_rsi(df['close'])
                df['MACD'], df['Signal_Line'] = compute_macd(df['close'])

                last_rsi = df['RSI'].iloc[-1]
                last_macd = df['MACD'].iloc[-1]
                last_signal_line = df['Signal_Line'].iloc[-1]
                last_atr = df['ATR'].iloc[-1]

                # Проверяем, если сделка уже есть
                if symbol in active_trades:
                    trade = active_trades[symbol]
                    if (trade['signal'] == "LONG" and close_price >= trade['tp']) or \
                       (trade['signal'] == "SHORT" and close_price <= trade['tp']):
                        await send_message_safe(f"✅ TP достигнут: {symbol}\nЦена: {close_price} USDT")
                        del active_trades[symbol]

                    elif (trade['signal'] == "LONG" and close_price <= trade['sl']) or \
                         (trade['signal'] == "SHORT" and close_price >= trade['sl']):
                        await send_message_safe(f"❌ SL достигнут: {symbol}\nЦена: {close_price} USDT")
                        del active_trades[symbol]

                    return  

                # Генерация нового сигнала
                signal = None
                if last_macd > last_signal_line and last_rsi < 50:
                    signal = "LONG"
                elif last_macd < last_signal_line and last_rsi > 50:
                    signal = "SHORT"

                if signal:
                    tp = round(close_price * (1 + last_atr), 6) if signal == "LONG" else round(close_price * (1 - last_atr), 6)
                    sl = round(close_price * (1 - last_atr * 0.5), 6) if signal == "LONG" else round(close_price * (1 + last_atr * 0.5), 6)

                    active_trades[symbol] = {"signal": signal, "entry": close_price, "tp": tp, "sl": sl}

                    message = (
                        f"🔹 **{signal} {symbol} (Futures)**\n"
                        f"🔹 **Вход**: {close_price} USDT\n"
                        f"🎯 **TP**: {tp} USDT\n"
                        f"⛔ **SL**: {sl} USDT"
                    )
                    await send_message_safe(message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Безопасная отправка сообщений в Telegram
async def send_message_safe(message):
    try:
        print(f"📤 Отправка сообщения в Telegram: {message}")
        await bot.send_message(TELEGRAM_CHAT_ID, message)
    except TelegramRetryAfter as e:
        print(f"⏳ Telegram ограничил отправку, ждем {e.retry_after} сек...")
        await asyncio.sleep(e.retry_after)
        await send_message_safe(message)
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")

# 🔹 Функции индикаторов
def compute_atr(df, period=14):
    high_low = df['close'].diff().abs()
    atr = high_low.rolling(window=period).mean()
    return atr

def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window).mean()
    long_ema = prices.ewm(span=long_window).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window).mean()
    return macd, signal_line

# 🔹 Запуск WebSocket и бота
async def main():
    print("🚀 Бот стартует...")
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
