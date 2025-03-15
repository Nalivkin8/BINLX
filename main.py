import asyncio
import websocket
import json
import numpy as np
import os
import ccxt  
from telegram import Bot, Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# 🔹 API-ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# 🔹 Проверка API
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
    print("✅ Подключение к Binance API успешно!")
except Exception as e:
    print(f"❌ Ошибка подключения к Binance: {e}")
    exit()

# 🔹 Telegram-бот
bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def send_telegram_message(text):
    """Функция отправки сообщений в Telegram"""
    print(f"📨 Отправка в Telegram: {text}")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

# 🔹 Отправляем сообщение 1 раз (без спама)
async def startup_message():
    await send_telegram_message("🚀 Бот запущен и отслеживает рынок!")

async def get_balance():
    """Запрос баланса"""
    try:
        balance_info = exchange.fetch_balance()
        balance = balance_info['total'].get('USDT', 0)
        return round(balance, 2)
    except Exception as e:
        print(f"❌ Ошибка получения баланса: {e}")
        return 0

async def show_balance(update: Update, context):
    """Обработчик кнопки Баланс"""
    balance = await get_balance()
    await update.message.reply_text(f"💰 Баланс: {balance} USDT")

async def get_open_positions():
    """Запрос активных позиций"""
    try:
        positions = exchange.fetch_positions()
        open_positions = [p for p in positions if float(p['contracts']) > 0]
        if not open_positions:
            return "📌 Нет открытых позиций"

        report = "📊 Открытые сделки:\n"
        for pos in open_positions:
            report += f"🔹 {pos['symbol']}: {pos['side']} {pos['contracts']} контрактов\nPnL: {round(float(pos['unrealizedPnl']), 2)} USDT\n\n"
        return report
    except Exception as e:
        print(f"❌ Ошибка получения позиций: {e}")
        return "❌ Ошибка при получении позиций"

async def show_positions(update: Update, context):
    """Обработчик кнопки Открытые сделки"""
    positions = await get_open_positions()
    await update.message.reply_text(positions)

async def start(update: Update, context):
    """Команда /start - Показывает меню внизу"""
    keyboard = [
        [KeyboardButton("📊 Баланс"), KeyboardButton("📈 Открытые сделки")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

async def handle_message(update: Update, context):
    """Обработчик сообщений"""
    text = update.message.text

    if text == "📊 Баланс":
        await show_balance(update, context)
    elif text == "📈 Открытые сделки":
        await show_positions(update, context)
    else:
        await update.message.reply_text("❌ Команда не распознана")

async def run_telegram_bot():
    """Запуск Telegram-бота"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Telegram-бот запущен!")
    await application.run_polling()

# 🔹 Торговые пары (Только ADAUSDT, IPUSDT, TSTUSDT)
TRADE_PAIRS = ["adausdt", "ipusdt", "tstusdt"]

# 🔹 WebSocket URL
STREAMS = "/".join([f"{pair}@kline_15m" for pair in TRADE_PAIRS])
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams={STREAMS}"

# 🔹 Данные для анализа
candle_data = {pair: [] for pair in TRADE_PAIRS}

def on_open(ws):
    print("✅ WebSocket подключён!")

def on_close(ws, close_status_code, close_msg):
    print("❌ WebSocket закрыт! Переподключение...")
    asyncio.run(asyncio.sleep(5))
    ws.run_forever()

def on_error(ws, error):
    print(f"⚠️ Ошибка WebSocket: {error}")

def calculate_rsi(prices, period=14):
    """Расчёт RSI"""
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

def on_message(ws, message):
    """Обработчик данных WebSocket"""
    data = json.loads(message)
    
    if "stream" in data and "data" in data:
        stream = data["stream"]
        pair = stream.split("@")[0].upper()
        kline = data["data"]["k"]
        price = float(kline["c"])
        is_closed = kline["x"]

        print(f"📊 {pair} | Цена: {price}")

        if is_closed:
            candle_data[pair].append(price)

            if len(candle_data[pair]) > 50:
                candle_data[pair].pop(0)

            rsi = calculate_rsi(candle_data[pair])

            if rsi is not None:
                print(f"📊 {pair} RSI: {rsi}")

                if rsi < 30:
                    signal = f"🚀 Лонг {pair}!\nЦена: {price}\nRSI: {rsi}"
                    asyncio.run(send_telegram_message(signal))
                elif rsi > 70:
                    signal = f"⚠️ Шорт {pair}!\nЦена: {price}\nRSI: {rsi}"
                    asyncio.run(send_telegram_message(signal))

async def start_websocket():
    """Запуск WebSocket"""
    ws = websocket.WebSocketApp(
        BINANCE_WS_URL,
        on_open=on_open,
        on_close=on_close,
        on_error=on_error,
        on_message=on_message
    )
    ws.run_forever()

async def main():
    """Основной запуск"""
    await startup_message()
    asyncio.create_task(start_websocket())
    await run_telegram_bot()

if __name__ == "__main__":
    asyncio.run(main())
