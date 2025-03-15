import asyncio
import websocket
import json
import numpy as np
import matplotlib.pyplot as plt
import io
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
candle_volumes = {pair: [] for pair in TRADE_PAIRS}

# 🔹 WebSocket URL (правильный формат)
SOCKETS = {pair: f"wss://fstream.binance.com/ws/{pair}@kline_15m" for pair in TRADE_PAIRS}

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
def on_message(ws, message, pair):
    global daily_trades, total_profit_loss
    data = json.loads(message)
    candle = data['k']
    price = float(candle['c'])  
    volume = float(candle['v'])
    is_closed = candle['x']

    print(f"📊 Данные получены для {pair.upper()} | Цена: {price} | Объём: {volume}")

    if is_closed:
        candle_data[pair].append(price)
        candle_volumes[pair].append(volume)

        if len(candle_data[pair]) > 50:
            candle_data[pair].pop(0)
            candle_volumes[pair].pop(0)

        # 📈 RSI
        rsi = calculate_rsi(candle_data[pair])
        
        # 🔹 Фильтр ложных сигналов (если RSI нет - выходим)
        if rsi is None:
            return

        # 🔹 Логирование
        print(f"📊 {pair.upper()} RSI: {rsi}")

        # 🔹 Отправка сообщений в Telegram при нужных условиях
        if rsi < 30:
            message = f"🚀 Лонг {pair.upper()}!\nЦена: {price}\nRSI: {rsi}"
            asyncio.run(send_telegram_message(message))
        elif rsi > 70:
            message = f"⚠️ Шорт {pair.upper()}!\nЦена: {price}\nRSI: {rsi}"
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

# 🔹 Запуск WebSocket с логированием
for pair in TRADE_PAIRS:
    print(f"✅ Запуск WebSocket для {pair.upper()}...")
    ws = websocket.WebSocketApp(
        SOCKETS[pair],
        on_open=on_open,
        on_close=on_close,
        on_error=on_error,
        on_message=lambda ws, msg: on_message(ws, msg, pair)
    )
    ws.run_forever()
