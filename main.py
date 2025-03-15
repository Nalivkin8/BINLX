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

# 🔹 Поддерживаемые пары
TRADE_PAIRS = ["ADAUSDT", "IPUSDT", "TSTUSDT"]

bot = Bot(token=TELEGRAM_BOT_TOKEN)

def sign_request(params):
    """🔹 Создаёт подпись для Binance API"""
    params["timestamp"] = int(time.time() * 1000)
    query_string = urlencode(params)
    signature = hmac.new(BINANCE_SECRET_KEY.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

async def get_order_book(symbol):
    """🔹 Запрос стакана ордеров"""
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/depth"
    params = {"symbol": symbol.upper(), "limit": 10}  # Получаем 10 лучших заявок

    try:
        response = requests.get(url, params=params)
        data = response.json()
        bids = data["bids"][:5]  # 5 лучших заявок на покупку
        asks = data["asks"][:5]  # 5 лучших заявок на продажу

        order_book = f"📊 **Order Book {symbol.upper()}**\n\n"
        order_book += "🔹 **Покупатели (BIDS):**\n"
        for bid in bids:
            order_book += f"💚 {bid[0]} | Кол-во: {bid[1]}\n"
        
        order_book += "\n🔻 **Продавцы (ASKS):**\n"
        for ask in asks:
            order_book += f"❤️ {ask[0]} | Кол-во: {ask[1]}\n"

        return order_book
    except Exception as e:
        return f"❌ Ошибка запроса стакана ордеров: {e}"

async def start(update: Update, context):
    keyboard = [
        [KeyboardButton("📊 Order Book ADA"), KeyboardButton("📊 Order Book IP")],
        [KeyboardButton("📊 Order Book TST")],
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
    elif text == "📊 Order Book TST":
        result = await get_order_book("TSTUSDT")
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

async def main():
    """🔹 Запуск Telegram-бота и Order Book"""
    await run_telegram_bot()

if __name__ == "__main__":
    asyncio.run(main(), debug=True)
