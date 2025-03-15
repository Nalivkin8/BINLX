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

# 🔹 Подключение к Binance API
bot = Bot(token=TELEGRAM_BOT_TOKEN)

def sign_request(params):
    """Создаёт подпись для Binance API"""
    query_string = urlencode(params)
    signature = hmac.new(BINANCE_SECRET_KEY.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

async def send_telegram_message(text):
    """Отправка сообщений в Telegram"""
    print(f"📨 Telegram: {text}")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

async def get_balance():
    """Запрос баланса и PnL"""
    url = f"{BINANCE_FUTURES_URL}/fapi/v2/account"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    params = sign_request({"timestamp": int(time.time() * 1000)})

    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        balance = float(data["totalWalletBalance"])
        unrealized_pnl = float(data["totalUnrealizedProfit"])
        return balance, unrealized_pnl
    except Exception as e:
        print(f"❌ Ошибка получения баланса: {e}")
        return 0, 0

async def show_balance(update: Update, context):
    balance, pnl = await get_balance()
    await update.message.reply_text(f"💰 Баланс: {balance} USDT\n📈 PnL: {pnl} USDT")

async def get_open_positions():
    """Запрос активных позиций"""
    url = f"{BINANCE_FUTURES_URL}/fapi/v2/positionRisk"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    params = sign_request({"timestamp": int(time.time() * 1000)})

    try:
        response = requests.get(url, headers=headers, params=params)
        positions = response.json()
        open_positions = [p for p in positions if float(p['positionAmt']) != 0]

        if not open_positions:
            return "📌 Нет открытых позиций"

        report = "📊 Открытые сделки:\n"
        for pos in open_positions:
            report += f"🔹 {pos['symbol']}: {pos['positionAmt']} контрактов\nPnL: {round(float(pos['unRealizedProfit']), 2)} USDT\n\n"
        return report
    except Exception as e:
        print(f"❌ Ошибка получения позиций: {e}")
        return "❌ Ошибка при получении позиций"

async def show_positions(update: Update, context):
    positions = await get_open_positions()
    await update.message.reply_text(positions)

async def start(update: Update, context):
    keyboard = [[KeyboardButton("📊 Баланс"), KeyboardButton("📈 Открытые сделки")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("✅ Бот запущен! Выберите действие:", reply_markup=reply_markup)

async def handle_message(update: Update, context):
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

async def main():
    await run_telegram_bot()

if __name__ == "__main__":
    asyncio.run(main())
