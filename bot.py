import websocket
import json
import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter
import pandas as pd

# 🔹 Загружаем переменные среды из Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Ошибка: TELEGRAM_CHAT_ID не задан в Railway Variables!")

# 🔹 Создаём бота и диспетчер
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# 🔹 Храним активные сделки и историю цен
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}

# 🔹 Запуск WebSocket
async def start_futures_websocket():
    print("🔄 Запуск WebSocket Binance Futures...")
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(msg)),
        on_open=on_open
    )
    print("⏳ Ожидание подключения к WebSocket...")
    await asyncio.to_thread(ws.run_forever)

# 🔹 Подписка на свечи Binance Futures
def on_open(ws):
    print("✅ Успешное подключение к WebSocket!")
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": [
            "tstusdt@kline_1m",
            "ipusdt@kline_1m",
            "adausdt@kline_1m"
        ],
        "id": 1
    })
    ws.send(subscribe_message)
    print("📩 Подписка на свечи Binance Futures")

# 🔹 Обрабатываем входящие данные WebSocket (свечи)
async def process_futures_message(message):
    global active_trades, price_history
    try:
        data = json.loads(message)

        if "k" in data:
            candle = data["k"]
            symbol = data["s"]
            close_price = float(candle["c"])  # Цена закрытия

            print(f"📊 {symbol} (1m): Закрытие {close_price} USDT")

            # Добавляем цену в историю
            if symbol not in price_history:
                price_history[symbol] = []
            price_history[symbol].append(close_price)

            # Если данных достаточно, анализируем тренд
            if len(price_history[symbol]) > 50:
                trend = analyze_trend(symbol, price_history[symbol])
                if trend:
                    await send_trade_signal(symbol, close_price, trend)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Анализ тренда на основе последних 50 свечей
def analyze_trend(symbol, prices):
    df = pd.DataFrame(prices, columns=["close"])
    df["ATR"] = compute_atr(df)
    df["RSI"] = compute_rsi(df["close"])
    df["MACD"], df["Signal_Line"] = compute_macd(df["close"])

    last_rsi = df["RSI"].iloc[-1]
    last_macd = df["MACD"].iloc[-1]
    last_signal_line = df["Signal_Line"].iloc[-1]

    if last_macd > last_signal_line and last_rsi < 70:
        return "LONG"
    elif last_macd < last_signal_line and last_rsi > 30:
        return "SHORT"
    return None

# 🔹 Отправка сигнала
async def send_trade_signal(symbol, price, trend):
    tp = round(price * 1.05, 6) if trend == "LONG" else round(price * 0.95, 6)
    sl = round(price * 0.98, 6) if trend == "LONG" else round(price * 1.02, 6)

    active_trades[symbol] = {"signal": trend, "entry": price, "tp": tp, "sl": sl}

    signal_emoji = "🟢" if trend == "LONG" else "🔴"

    message = (
        f"{signal_emoji} **{trend} {symbol} (Futures)**\n"
        f"🔹 **Вход**: {price} USDT\n"
        f"🎯 **TP**: {tp} USDT\n"
        f"⛔ **SL**: {sl} USDT"
    )
    await send_message_safe(message)

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
    df["tr"] = df["close"].diff().abs()
    atr = df["tr"].rolling(window=period).mean()
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
    print("🚀 Бот стартует... Railway работает!")
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
