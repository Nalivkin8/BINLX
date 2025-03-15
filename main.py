import asyncio
import requests
import json
import os
import hmac
import hashlib
import time
import websocket
from urllib.parse import urlencode
from telegram import Bot, Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# 🔹 API-ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# 🔹 Binance API URL
BINANCE_FUTURES_URL = "https://fapi.binance.com"

# 🔹 Временной сдвиг (будет обновляться при запуске)
SERVER_TIME_OFFSET = 0

# 🔹 WebSocket URL
TRADE_PAIRS = ["adausdt", "ipusdt", "tstusdt"]
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams=" + "/".join([f"{pair}@kline_5m" for pair in TRADE_PAIRS])

bot = Bot(token=TELEGRAM_BOT_TOKEN)

def get_binance_time():
    """🔹 Получение серверного времени Binance и расчёт смещения"""
    global SERVER_TIME_OFFSET
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/time"
    
    try:
        response = requests.get(url)
        server_time = response.json()["serverTime"]
        local_time = int(time.time() * 1000)
        SERVER_TIME_OFFSET = server_time - local_time
        print(f"✅ Время синхронизировано! Смещение: {SERVER_TIME_OFFSET} мс")
    except Exception as e:
        print(f"❌ Ошибка получения времени Binance: {e}")

def sign_request(params):
    """🔹 Создаёт подпись для Binance API"""
    params["timestamp"] = int(time.time() * 1000) + SERVER_TIME_OFFSET
    query_string = urlencode(params)
    signature = hmac.new(BINANCE_SECRET_KEY.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

async def send_telegram_message(text):
    """🔹 Отправка сообщений в Telegram"""
    print(f"📨 Telegram: {text}")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

async def get_order_book(symbol):
    """🔹 Запрос стакана ордеров"""
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/depth"
    params = {"symbol": symbol.upper(), "limit": 10}

    try:
        response = requests.get(url, params=params)
        data = response.json()
        bids = data["bids"][:5]
        asks = data["asks"][:5]

        order_book = f"📊 Order Book {symbol.upper()}:\n\n"
        order_book += "🔹 **Покупатели (Bids):**\n"
        for bid in bids:
            order_book += f"Цена: {bid[0]} | Кол-во: {bid[1]}\n"
        
        order_book += "\n🔻 **Продавцы (Asks):**\n"
        for ask in asks:
            order_book += f"Цена: {ask[0]} | Кол-во: {ask[1]}\n"

        return order_book
    except Exception as e:
        return f"❌ Ошибка запроса стакана ордеров: {e}"

async def start(update: Update, context):
    keyboard = [
        [KeyboardButton("📊 Order Book ADA"), KeyboardButton("📈 Сделки ADA")],
        [KeyboardButton("📊 Order Book IP"), KeyboardButton("📈 Сделки IP")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("✅ Бот запущен! Выберите действие:", reply_markup=reply_markup)

async def handle_message(update: Update, context):
    text = update.message.text
    if text == "📊 Order Book ADA":
        result = await get_order_book("ADAUSDT")
        await update.message.reply_text(result)
    elif text == "📊 Order Book IP":
        result = await get_order_book("IPUSDT")
        await update.message.reply_text(result)
    else:
        await update.message.reply_text("❌ Команда не распознана")

async def run_telegram_bot():
    """🔹 Запуск Telegram-бота"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Telegram-бот запущен!")
    await application.run_polling()

def start_websocket():
    """🔹 Запуск WebSocket"""
    ws = websocket.WebSocketApp(BINANCE_WS_URL)
    ws.run_forever()

async def main():
    """🔹 Запуск бота и WebSocket в одном event loop"""
    loop = asyncio.get_running_loop()

    # Синхронизируем время с Binance перед стартом
    get_binance_time()
    
    # Telegram-бот и WebSocket работают параллельно
    telegram_task = asyncio.create_task(run_telegram_bot())
    websocket_task = loop.run_in_executor(None, start_websocket)

    await asyncio.gather(telegram_task, websocket_task)

if __name__ == "__main__":
    asyncio.run(main(), debug=True)
