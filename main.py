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
import numpy as np

# 🔹 API-ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# 🔹 Binance API URL
BINANCE_FUTURES_URL = "https://fapi.binance.com"

# 🔹 Проверка API-ключей
if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BINANCE_API_KEY, BINANCE_SECRET_KEY]):
    print("❌ Ошибка: Не все API-ключи заданы. Проверь переменные окружения!")
    exit()

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

# 🔹 WebSocket Binance Futures
TRADE_PAIRS = ["adausdt", "ipusdt", "tstusdt"]
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams=" + "/".join([f"{pair}@kline_5m" for pair in TRADE_PAIRS])
candle_data = {pair: [] for pair in TRADE_PAIRS}

def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return None
    delta = np.diff(prices)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])
    
    if avg_loss == 0:
        return 100
    if avg_gain == 0:
        return 0
    
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def on_message(ws, message):
    data = json.loads(message)
    if "stream" in data and "data" in data:
        stream = data["stream"]
        pair = stream.split("@")[0].upper()
        price = float(data["data"]["k"]["c"])
        is_closed = data["data"]["k"]["x"]

        print(f"📊 {pair} | Цена: {price}")

        if is_closed:
            candle_data[pair].append(price)

            if len(candle_data[pair]) > 50:
                candle_data[pair].pop(0)

            rsi = calculate_rsi(candle_data[pair])
            if rsi is not None:
                print(f"📊 {pair} RSI: {rsi}")
                if rsi < 30:
                    asyncio.run(send_telegram_message(f"🚀 Лонг {pair}!\nЦена: {price}\nRSI: {rsi}"))
                elif rsi > 70:
                    asyncio.run(send_telegram_message(f"⚠️ Шорт {pair}!\nЦена: {price}\nRSI: {rsi}"))

async def start_websocket():
    ws = websocket.WebSocketApp(BINANCE_WS_URL, on_message=on_message)
    ws.run_forever()

async def main():
    asyncio.create_task(run_telegram_bot())
    await start_websocket()

if __name__ == "__main__":
    asyncio.run(main())
