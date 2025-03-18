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
price_history = {
    "TSTUSDT": {"1m": [], "15m": [], "30m": [], "1h": []},
    "IPUSDT": {"1m": [], "15m": [], "30m": [], "1h": []},
    "ADAUSDT": {"1m": [], "15m": [], "30m": [], "1h": []}
}

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

# 🔹 Подписка на свечи Binance Futures (1m, 15m, 30m, 1h)
def on_open(ws):
    print("✅ Успешное подключение к WebSocket!")
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": [
            "tstusdt@kline_1m", "tstusdt@kline_15m", "tstusdt@kline_30m", "tstusdt@kline_1h",
            "ipusdt@kline_1m", "ipusdt@kline_15m", "ipusdt@kline_30m", "ipusdt@kline_1h",
            "adausdt@kline_1m", "adausdt@kline_15m", "adausdt@kline_30m", "adausdt@kline_1h"
        ],
        "id": 1
    })
    ws.send(subscribe_message)
    print("📩 Подписка на свечи Binance Futures (1m, 15m, 30m, 1h)")

# 🔹 Обрабатываем входящие данные WebSocket (свечи)
async def process_futures_message(message):
    global active_trades, price_history
    try:
        data = json.loads(message)

        if "k" in data:
            candle = data["k"]
            symbol = data["s"]
            interval = candle["i"]
            close_price = float(candle["c"])  # Цена закрытия

            print(f"📊 {symbol} ({interval}): Закрытие {close_price} USDT")

            # Сохраняем цену в истории
            if symbol in price_history and interval in price_history[symbol]:
                price_history[symbol][interval].append(close_price)
                if len(price_history[symbol][interval]) > 50:
                    price_history[symbol][interval].pop(0)

            # Если есть данные по всем таймфреймам – анализируем тренд
            if all(len(price_history[symbol][tf]) >= 50 for tf in ["1m", "15m", "30m", "1h"]):
                trend = analyze_combined_trend(symbol)
                if trend:
                    await send_trade_signal(symbol, close_price, trend)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Анализ тренда на основе 4 таймфреймов (с ослабленным RSI)
def analyze_combined_trend(symbol):
    trends = []
    for tf in ["1m", "15m", "30m", "1h"]:
        prices = price_history[symbol][tf]
        df = pd.DataFrame(prices, columns=["close"])
        df["ATR"] = compute_atr(df)
        df["RSI"] = compute_rsi(df["close"])
        df["MACD"], df["Signal_Line"] = compute_macd(df["close"])

        last_rsi = df["RSI"].iloc[-1]
        last_macd = df["MACD"].iloc[-1]
        last_signal_line = df["Signal_Line"].iloc[-1]

        print(f"📊 {symbol} ({tf}) | RSI: {round(last_rsi, 2)}, MACD: {round(last_macd, 6)}, Signal: {round(last_signal_line, 6)}")

        if last_macd > last_signal_line and last_rsi < 50:
            trends.append("LONG")
        elif last_macd < last_signal_line and last_rsi > 50:
            trends.append("SHORT")
        else:
            trends.append(None)

    print(f"📊 Анализ тренда {symbol}: {trends}")  

    if trends.count("LONG") >= 3:
        return "LONG"
    elif trends.count("SHORT") >= 3:
        return "SHORT"
    return None

# 🔹 Вычисление ATR (Средний Истинный Диапазон)
def compute_atr(df, period=14):
    df["high"] = df["close"].shift(1)
    df["low"] = df["close"].shift(-1)
    df["tr"] = abs(df["high"] - df["low"])
    df["ATR"] = df["tr"].rolling(window=period).mean()
    return df["ATR"]

# 🔹 Отправка сигнала
async def send_trade_signal(symbol, price, trend):
    tp_multiplier = 1.05 if trend == "LONG" else 0.95
    sl_multiplier = 0.98 if trend == "LONG" else 1.02

    tp = round(price * tp_multiplier, 6)
    sl = round(price * sl_multiplier, 6)

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

# 🔹 Запуск WebSocket и бота
async def main():
    print("🚀 Бот стартует... Railway работает!")
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
