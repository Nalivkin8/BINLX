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

# 🔹 Поддерживаемые пары
TRADE_PAIRS = ["ADAUSDT", "IPUSDT", "TSTUSDT"]

bot = Bot(token=TELEGRAM_BOT_TOKEN)

def get_binance_time():
    """🔹 Получение серверного времени Binance"""
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

async def get_exchange_info():
    """🔹 Получение информации о бирже (список пар, лимиты)"""
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/exchangeInfo"
    
    try:
        response = requests.get(url)
        data = response.json()

        available_pairs = {s["symbol"]: s for s in data["symbols"]}

        report = "📊 **Информация о доступных торговых парах**:\n"
        for pair in TRADE_PAIRS:
            if pair in available_pairs:
                symbol_info = available_pairs[pair]
                min_qty = symbol_info["filters"][1]["minQty"]
                tick_size = symbol_info["filters"][0]["tickSize"]
                max_leverage = symbol_info["filters"][6]["maxLeverage"]

                report += f"\n🔹 **{pair}**:\n"
                report += f"📏 Минимальный ордер: {min_qty}\n"
                report += f"💰 Шаг цены: {tick_size}\n"
                report += f"⚡ Максимальное плечо: {max_leverage}x\n"
            else:
                report += f"\n❌ {pair} **недоступна на Binance Futures**\n"

        return report
    except Exception as e:
        return f"❌ Ошибка получения информации о бирже: {e}"

async def start(update: Update, context):
    keyboard = [
        [KeyboardButton("📊 Инфо о парах"), KeyboardButton("📈 Баланс")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("✅ Бот запущен! Выберите действие:", reply_markup=reply_markup)

async def handle_message(update: Update, context):
    text = update.message.text
    if text == "📊 Инфо о парах":
        result = await get_exchange_info()
        await update.message.reply_text(result)
    elif text == "📈 Баланс":
        result = "⚠️ Функция баланса временно недоступна"
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
    """🔹 Запуск Telegram-бота и проверка информации о бирже"""
    get_binance_time()  # Синхронизация времени Binance
    await run_telegram_bot()

if __name__ == "__main__":
    asyncio.run(main(), debug=True)
