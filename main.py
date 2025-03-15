import asyncio
import json
import os
import requests
import websocket
import hmac
import hashlib
from urllib.parse import urlencode
from telegram import Bot, Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# 🔹 API-ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# 🔹 Binance Futures API URL
BINANCE_FUTURES_URL = "https://fapi.binance.com"
LISTEN_KEY_URL = f"{BINANCE_FUTURES_URL}/fapi/v1/listenKey"
ACCOUNT_WS_URL = None  # WebSocket URL после получения listenKey

bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def send_telegram_message(text):
    """🔹 Отправка сообщений в Telegram"""
    print(f"📨 Telegram: {text}")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

def get_listen_key():
    """🔹 Получение listenKey для Binance Futures WebSocket"""
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    response = requests.post(LISTEN_KEY_URL, headers=headers)

    if response.status_code == 200:
        listen_key = response.json()["listenKey"]
        global ACCOUNT_WS_URL
        ACCOUNT_WS_URL = f"wss://fstream.binance.com/ws/{listen_key}"
        print(f"✅ Получен listenKey: {listen_key}")
        return listen_key
    else:
        print(f"❌ Ошибка получения listenKey: {response.json()}")
        return None

def keep_alive_listen_key():
    """🔹 Обновление listenKey каждые 30 минут"""
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    while True:
        try:
            requests.put(LISTEN_KEY_URL, headers=headers)
            print("🔄 ListenKey обновлен!")
            asyncio.run(send_telegram_message("🔄 ListenKey обновлен!"))
        except Exception as e:
            print(f"❌ Ошибка обновления listenKey: {e}")
        asyncio.sleep(1800)  # 30 минут

def on_message(ws, message):
    """🔹 Обработка входящих данных из WebSocket"""
    data = json.loads(message)

    if "e" in data:
        event_type = data["e"]

        if event_type == "ACCOUNT_UPDATE":
            # 📊 Обновление баланса и позиций
            balances = data["a"]["B"]
            positions = data["a"]["P"]

            message = "📊 **Обновление аккаунта Binance Futures**\n\n"
            message += "💰 **Баланс:**\n"
            for balance in balances:
                asset = balance["a"]
                wallet_balance = balance["wb"]
                message += f"💎 {asset}: {wallet_balance}\n"

            message += "\n📈 **Открытые позиции:**\n"
            for position in positions:
                symbol = position["s"]
                position_amount = position["pa"]
                unrealized_pnl = position["up"]
                message += f"📊 {symbol} | Кол-во: {position_amount} | PnL: {unrealized_pnl}\n"

            asyncio.run(send_telegram_message(message))

        elif event_type == "ORDER_TRADE_UPDATE":
            # 📌 Обновление ордеров
            order = data["o"]
            symbol = order["s"]
            order_id = order["i"]
            status = order["X"]
            side = "🟢 Лонг" if order["S"] == "BUY" else "🔴 Шорт"
            price = order["p"]
            amount = order["q"]

            message = f"📌 **Обновление ордера**\n\n"
            message += f"📊 {symbol} | {side}\n"
            message += f"💰 Цена: {price} | Кол-во: {amount}\n"
            message += f"📋 Статус: {status}\n"

            asyncio.run(send_telegram_message(message))

        elif event_type == "MARGIN_CALL":
            # ⚠️ Уведомление о маржинальном звонке
            message = f"⚠️ **Маржинальный звонок!**\n"
            message += f"Внимание! Баланс по марже падает, возможна ликвидация!"

            asyncio.run(send_telegram_message(message))

def start_account_websocket():
    """🔹 Запуск WebSocket Binance Futures Account"""
    global ACCOUNT_WS_URL
    listen_key = get_listen_key()
    if listen_key:
        ws = websocket.WebSocketApp(ACCOUNT_WS_URL, on_message=on_message)
        ws.run_forever()
    else:
        print("❌ Ошибка запуска WebSocket Account!")

async def start(update: Update, context):
    keyboard = [
        [KeyboardButton("📊 Баланс"), KeyboardButton("📋 Ордеры")],
        [KeyboardButton("📈 Позиции"), KeyboardButton("⚠️ Маржа")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("✅ Бот запущен! Выберите действие:", reply_markup=reply_markup)

async def handle_message(update: Update, context):
    text = update.message.text

    if text == "📊 Баланс":
        get_listen_key()
        await update.message.reply_text("✅ Баланс обновляется в реальном времени через WebSocket!")

    elif text == "📋 Ордеры":
        get_listen_key()
        await update.message.reply_text("✅ Открытые ордера обновляются в реальном времени!")

    elif text == "📈 Позиции":
        get_listen_key()
        await update.message.reply_text("✅ Позиции обновляются через WebSocket!")

    elif text == "⚠️ Маржа":
        get_listen_key()
        await update.message.reply_text("✅ Система следит за маржой!")

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
    """🔹 Запуск WebSocket и Telegram-бота"""
    loop = asyncio.get_running_loop()
    telegram_task = asyncio.create_task(run_telegram_bot())
    websocket_task = loop.run_in_executor(None, start_account_websocket)
    keep_alive_task = loop.run_in_executor(None, keep_alive_listen_key)
    await asyncio.gather(telegram_task, websocket_task, keep_alive_task)

if __name__ == "__main__":
    asyncio.run(main(), debug=True)
