import asyncio
import threading
import websocket
import json
import numpy as np
import os
import schedule
import time
from telegram import Bot
import ccxt  

# 🔹 Загружаем API-ключи из Railway Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# 🔹 Проверка API-ключей
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ Ошибка: TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы!")
    exit()
if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
    print("❌ Ошибка: BINANCE API-ключи не заданы!")
    exit()

# 🔹 Подключение к Binance
try:
    exchange = ccxt.binance({
        'apiKey': BINANCE_API_KEY,
        'secret': BINANCE_SECRET_KEY,
        'options': {'defaultType': 'future'}
    })
    print("✅ Успешное подключение к Binance API!")
except Exception as e:
    print(f"❌ Ошибка подключения к Binance: {e}")
    exit()

# 🔹 Telegram-бот
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# 🔹 Функция отправки сообщения в Telegram (асинхронно)
async def send_telegram_message(text):
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

# 🔹 Запуск бота (отправляем сообщение в Telegram)
asyncio.run(send_telegram_message("🚀 Бот запущен и работает!"))

# 🔹 Торговые пары
TRADE_PAIRS = ["btcusdt", "ethusdt", "solusdt", "xrpusdt", "adausdt", "dotusdt", "maticusdt", "bnbusdt", "linkusdt", "ipusdt", "tstusdt"]

# 🔹 Данные для анализа
candle_data = {pair: [] for pair in TRADE_PAIRS}

# 🔹 Объединённое WebSocket-соединение для всех пар
STREAMS = "/".join([f"{pair}@kline_15m" for pair in TRADE_PAIRS])
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams={STREAMS}"

# 🔹 Логирование сделок
daily_trades = 0
total_profit_loss = 0

# 🔹 WebSocket обработчики
def on_open(ws):
    print("✅ WebSocket подключён!")

def on_close(ws, close_status_code, close_msg):
    print("❌ WebSocket закрыт! Переподключение...")
    time.sleep(5)
    ws.run_forever()

def on_error(ws, error):
    print(f"⚠️ Ошибка WebSocket: {error}")

# 🔹 Обработка входящих данных WebSocket
def on_message(ws, message):
    global daily_trades, total_profit_loss
    data = json.loads(message)
    
    if "stream" in data and "data" in data:
        stream = data["stream"]
        pair = stream.split("@")[0].upper()
        kline = data["data"]["k"]
        price = float(kline["c"])
        is_closed = kline["x"]

        print(f"📊 Данные получены для {pair} | Цена: {price}")

        if is_closed:
            candle_data[pair].append(price)

            if len(candle_data[pair]) > 50:
                candle_data[pair].pop(0)

            # 📈 RSI
            rsi = calculate_rsi(candle_data[pair])
            
            if rsi is None:
                return

            print(f"📊 {pair} RSI: {rsi}")

            # 🔹 Отправка сообщений в Telegram при нужных условиях
            if rsi < 30:
                message = f"🚀 Лонг {pair}!\nЦена: {price}\nRSI: {rsi}"
                asyncio.run(send_telegram_message(message))
            elif rsi > 70:
                message = f"⚠️ Шорт {pair}!\nЦена: {price}\nRSI: {rsi}"
                asyncio.run(send_telegram_message(message))

# 🔹 Функция расчёта RSI
def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return None
    delta = np.diff(prices)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])
    rs = avg_gain / avg_loss if avg_loss != 0 else 0
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

# 🔹 Получение баланса аккаунта
def get_balance():
    try:
        balance_info = exchange.fetch_balance()
        balance = balance_info['total']['USDT'] if 'USDT' in balance_info['total'] else 0
        return round(balance, 2)
    except Exception as e:
        print(f"❌ Ошибка получения баланса: {e}")
        return 0

# 🔹 Дневной отчёт в Telegram
def daily_report():
    balance = get_balance()
    report = f"📊 Дневной отчёт\n🔹 Баланс: {balance} USDT\n🔹 Сделок за сутки: {daily_trades}\n🔹 Общий P/L: {round(total_profit_loss, 2)} USDT"
    asyncio.run(send_telegram_message(report))
    print("✅ Дневной отчёт отправлен!")

schedule.every().day.at("00:00").do(daily_report)

# 🔹 Запуск WebSocket
def start_websocket():
    ws = websocket.WebSocketApp(
        BINANCE_WS_URL,
        on_open=on_open,
        on_close=on_close,
        on_error=on_error,
        on_message=on_message
    )
    ws.run_forever()

# Запуск WebSocket в отдельном потоке
threading.Thread(target=start_websocket).start()
