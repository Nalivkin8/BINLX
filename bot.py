import websocket
import json
import asyncio
import pandas as pd
import time
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.exceptions import TelegramRetryAfter

# Загружаем переменные среды из Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Обязательно добавь в Railway
if not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Ошибка: TELEGRAM_CHAT_ID не задан в Railway Variables!")

# Создаём бота и диспетчер
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Храним активные сделки
active_trades = {}  
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}

# 🔹 Логируем запуск WebSocket
async def start_futures_websocket():
    print("🔄 Запуск WebSocket...")
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(msg)),
        on_open=on_open  
    )
    print("⏳ Ожидание подключения к WebSocket...")
    await asyncio.to_thread(ws.run_forever)

# 🔹 Подписка на пары Binance
def on_open(ws):
    print("✅ Успешное подключение к WebSocket!")
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["tstusdt@trade", "ipusdt@trade", "adausdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
    print("📩 Отправлен запрос на подписку к Binance Futures")

# 🔹 Обрабатываем входящие сообщения WebSocket
async def process_futures_message(message):
    global active_trades, price_history
    try:
        data = json.loads(message)

        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])
            print(f"📊 Получено обновление цены {symbol}: {price} USDT")

            # Проверяем TP/SL
            if symbol in active_trades:
                trade = active_trades[symbol]

                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    print(f"🎯 {symbol} достиг Take Profit ({trade['tp']} USDT)")
                    await send_message_safe(f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]

                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    print(f"⛔ {symbol} достиг Stop Loss ({trade['sl']} USDT)")
                    await send_message_safe(f"⛔ **{symbol} достиг Stop Loss ({trade['sl']} USDT)**")
                    del active_trades[symbol]

                return  

            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 200:
                    price_history[symbol].pop(0)

                    df = pd.DataFrame(price_history[symbol], columns=['close'])
                    df['ATR'] = compute_atr(df)
                    df['RSI'] = compute_rsi(df['close'])
                    df['MACD'], df['Signal_Line'] = compute_macd(df['close'])

                    last_atr = df['ATR'].iloc[-1]
                    last_rsi = df['RSI'].iloc[-1]
                    last_macd = df['MACD'].iloc[-1]
                    last_signal_line = df['Signal_Line'].iloc[-1]

                    signal = None
                    if last_macd > last_signal_line and last_atr > 0.03 and last_rsi < 65:
                        signal = "LONG"
                    elif last_macd < last_signal_line and last_atr > 0.03 and last_rsi > 35:
                        signal = "SHORT"

                    if signal:
                        tp_percent = min(10 + last_atr * 2.5, 30) / 100  
                        sl_percent = min(5 + last_atr * 1.8, 15) / 100  

                        tp = round(price * (1 + tp_percent) if signal == "LONG" else price * (1 - tp_percent), 6)
                        sl = round(price * (1 - sl_percent) if signal == "LONG" else price * (1 + sl_percent), 6)

                        active_trades[symbol] = {"signal": signal, "entry": price, "tp": tp, "sl": sl}

                        signal_emoji = "🟢" if signal == "LONG" else "🔴"

                        message = (
                            f"{signal_emoji} **{signal} {symbol} (Futures)**\n"
                            f"🔹 **Вход**: {price} USDT\n"
                            f"🎯 **TP**: {tp} USDT | {round(tp_percent * 100, 1)}%\n"
                            f"⛔ **SL**: {sl} USDT | {round(sl_percent * 100, 1)}%"
                        )
                        await send_message_safe(message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Отправка сообщений в Telegram
async def send_message_safe(message):
    try:
        print(f"📤 Отправка сообщения: {message}")
        await bot.send_message(TELEGRAM_CHAT_ID, message)
    except TelegramRetryAfter as e:
        print(f"⏳ Telegram ограничил отправку, ждем {e.retry_after} сек...")
        await asyncio.sleep(e.retry_after)
        await send_message_safe(message)
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")

# 🔹 Функции индикаторов
def compute_atr(df, period=14):
    high = df['close'].rolling(window=period).max()
    low = df['close'].rolling(window=period).min()
    tr = high - low
    atr = tr.rolling(window=period).mean()
    return atr

def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window, adjust=False).mean()
    long_ema = prices.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

# 🔹 Запуск WebSocket и бота
async def main():
    print("🚀 Запуск бота и WebSocket...")
    asyncio.create_task(start_futures_websocket())  # Запуск WebSocket
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
