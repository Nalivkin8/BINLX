import asyncio
import threading
import websocket
import json
import numpy as np
import os
import schedule
import time
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
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

# 🔹 Telegram-обработчик команд
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("📊 Баланс", callback_data="balance")],
        [InlineKeyboardButton("📈 Открытые сделки", callback_data="positions")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

# 🔹 Запрос баланса
def get_balance():
    try:
        balance_info = exchange.fetch_balance()
        balance = balance_info['total']['USDT'] if 'USDT' in balance_info['total'] else 0
        return round(balance, 2)
    except Exception as e:
        print(f"❌ Ошибка получения баланса: {e}")
        return 0

def show_balance(update: Update, context: CallbackContext):
    balance = get_balance()
    update.callback_query.answer()
    update.callback_query.message.reply_text(f"💰 Ваш баланс: {balance} USDT")

# 🔹 Запрос активных позиций
def get_open_positions():
    try:
        positions = exchange.fetch_positions()
        open_positions = [p for p in positions if float(p['contracts']) > 0]

        if not open_positions:
            return "📌 Нет открытых позиций"

        report = "📊 Открытые позиции:\n"
        for pos in open_positions:
            report += f"🔹 {pos['symbol']}: {pos['side']} {pos['contracts']} контрактов\nPnL: {round(float(pos['unrealizedPnl']), 2)} USDT\n\n"

        return report
    except Exception as e:
        print(f"❌ Ошибка получения позиций: {e}")
        return "❌ Ошибка при получении позиций"

def show_positions(update: Update, context: CallbackContext):
    positions = get_open_positions()
    update.callback_query.answer()
    update.callback_query.message.reply_text(positions)

# 🔹 Обработчик кнопок
def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.data == "balance":
        show_balance(update, context)
    elif query.data == "positions":
        show_positions(update, context)

# 🔹 Настройка Telegram-хендлеров
updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CallbackQueryHandler(button_click))

# 🔹 Запуск Telegram-бота в потоке
def run_telegram_bot():
    print("✅ Запуск Telegram-бота...")
    updater.start_polling()
    updater.idle()

threading.Thread(target=run_telegram_bot, daemon=True).start()

# 🔹 Торговые пары
TRADE_PAIRS = ["btcusdt", "ethusdt", "solusdt", "xrpusdt", "adausdt", "dotusdt", "maticusdt", "bnbusdt", "linkusdt", "ipusdt", "tstusdt"]

# 🔹 Объединённое WebSocket-соединение для всех пар
STREAMS = "/".join([f"{pair}@kline_15m" for pair in TRADE_PAIRS])
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams={STREAMS}"

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
    data = json.loads(message)
    
    if "stream" in data and "data" in data:
        stream = data["stream"]
        pair = stream.split("@")[0].upper()
        kline = data["data"]["k"]
        price = float(kline["c"])
        is_closed = kline["x"]

        print(f"📊 Данные получены для {pair} | Цена: {price}")

# 🔹 Запуск WebSocket в отдельном потоке
def start_websocket():
    ws = websocket.WebSocketApp(
        BINANCE_WS_URL,
        on_open=on_open,
        on_close=on_close,
        on_error=on_error,
        on_message=on_message
    )
    ws.run_forever()

threading.Thread(target=start_websocket, daemon=True).start()
