import asyncio
import threading
import websocket
import json
import numpy as np
import os
import ccxt  
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

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
    print(f"📨 Отправка сообщения в Telegram: {text}")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

# 🔹 Запуск бота (отправляем сообщение в Telegram)
asyncio.run(send_telegram_message("🚀 Бот запущен и работает!"))

# 🔹 Запрос баланса
def get_balance():
    try:
        balance_info = exchange.fetch_balance()
        balance = balance_info['total']['USDT'] if 'USDT' in balance_info['total'] else 0
        return round(balance, 2)
    except Exception as e:
        print(f"❌ Ошибка получения баланса: {e}")
        return 0

async def show_balance(update: Update, context):
    balance = get_balance()
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(f"💰 Ваш баланс: {balance} USDT")

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

async def show_positions(update: Update, context):
    positions = get_open_positions()
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(positions)

# 🔹 Обработчик кнопок
async def button_click(update: Update, context):
    query = update.callback_query
    if query.data == "balance":
        await show_balance(update, context)
    elif query.data == "positions":
        await show_positions(update, context)

# 🔹 Обработчик команды /start
async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("📊 Баланс", callback_data="balance")],
        [InlineKeyboardButton("📈 Открытые сделки", callback_data="positions")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

# 🔹 Обработчик текстовых сообщений (логирование)
async def handle_message(update: Update, context):
    user_message = update.message.text
    print(f"📩 Сообщение от пользователя: {user_message}")
    await update.message.reply_text(f"Вы сказали: {user_message}")

# 🔹 Запуск Telegram-бота в асинхронном режиме
async def run_telegram_bot():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Telegram-бот запущен!")
    await application.run_polling()

# 🔹 Торговые пары
TRADE_PAIRS = ["adausdt", "ipusdt", "tstusdt"]

# 🔹 WebSocket URL
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
        print(f"📊 Данные получены для {pair} | Цена: {price}")

# 🔹 Запуск WebSocket в асинхронном потоке
async def start_websocket():
    ws = websocket.WebSocketApp(
        BINANCE_WS_URL,
        on_open=on_open,
        on_close=on_close,
        on_error=on_error,
        on_message=on_message
    )
    ws.run_forever()

# 🔹 Запуск всего кода в асинхронном режиме
async def main():
    # Запускаем WebSocket и Telegram-бот в параллельных задачах
    asyncio.create_task(start_websocket())
    await run_telegram_bot()

# 🔹 Запуск бота
if __name__ == "__main__":
    asyncio.run(main())
