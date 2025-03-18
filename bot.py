import websocket
import json
import asyncio
import pandas as pd
import time
import os
import requests
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter

# 🔹 Загружаем переменные среды из Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_URL = "https://fapi.binance.com/fapi/v1/klines"

if not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Ошибка: TELEGRAM_CHAT_ID не задан в Railway Variables!")

# 🔹 Создаём бота и диспетчер
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# 🔹 Храним активные сделки и цены
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}

# 🔹 Запуск WebSocket
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

# 🔹 Запрос свечей с Binance API
def get_candles(symbol, interval, limit=100):
    url = f"{BINANCE_API_URL}?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Ошибка Binance API: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Binance API не отвечает: {e}")
        return None

# 🔹 Анализ тренда на нескольких таймфреймах
def analyze_trend(symbol):
    timeframes = ["1m", "15m", "30m", "1h"]
    trend_scores = {"LONG": 0, "SHORT": 0}

    for tf in timeframes:
        print(f"📩 Запрос свечей для {symbol} на таймфрейме {tf}")
        candles = get_candles(symbol, tf)
        if not candles:
            continue

        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'trades', 'taker_base', 'taker_quote', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['ATR'] = compute_atr(df)
        df['RSI'] = compute_rsi(df['close'])
        df['MACD'], df['Signal_Line'] = compute_macd(df['close'])

        last_rsi = df['RSI'].iloc[-1]
        last_macd = df['MACD'].iloc[-1]
        last_signal_line = df['Signal_Line'].iloc[-1]

        if last_macd > last_signal_line and last_rsi < 70:
            trend_scores["LONG"] += 1
        elif last_macd < last_signal_line and last_rsi > 30:
            trend_scores["SHORT"] += 1

    if trend_scores["LONG"] >= 3:
        return "LONG"
    elif trend_scores["SHORT"] >= 3:
        return "SHORT"
    else:
        return None  

# 🔹 Обрабатываем входящие данные WebSocket
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

            trend = analyze_trend(symbol)
            if not trend:
                print(f"⚠️ Сигнал отклонён: нет подтверждённого тренда для {symbol}")
                return  

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

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Отправка сообщений в Telegram
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
