import asyncio
import requests
import json
import os
import websocket
import pandas as pd
import numpy as np
from telegram import Bot, Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# 🔹 API-ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 🔹 Binance WebSocket URL
TRADE_PAIRS = ["adausdt", "ipusdt", "tstusdt"]
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams=" + "/".join([f"{pair}@kline_5m" for pair in TRADE_PAIRS])

# 🔹 Binance REST API URL
BINANCE_FUTURES_URL = "https://fapi.binance.com"

bot = Bot(token=TELEGRAM_BOT_TOKEN)
candle_data = {pair: pd.DataFrame(columns=["timestamp", "close"]) for pair in TRADE_PAIRS}

def calculate_rsi(df, period=14):
    """🔹 Рассчет RSI (Relative Strength Index)"""
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else None

def calculate_sma(df, period=50):
    """🔹 Рассчет SMA (Simple Moving Average)"""
    return df["close"].rolling(window=period).mean().iloc[-1] if not df.empty else None

async def get_order_book(symbol):
    """🔹 Запрос стакана ордеров"""
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/depth"
    params = {"symbol": symbol.upper(), "limit": 5}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        bids = data["bids"]
        asks = data["asks"]

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

async def send_telegram_message(text):
    """🔹 Отправка сообщений в Telegram"""
    print(f"📨 Telegram: {text}")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

def on_message(ws, message):
    """🔹 Обработка входящих данных из WebSocket"""
    data = json.loads(message)
    if "stream" in data and "data" in data:
        stream = data["stream"]
        pair = stream.split("@")[0].upper()
        price = float(data["data"]["k"]["c"])
        timestamp = data["data"]["k"]["t"]
        is_closed = data["data"]["k"]["x"]

        print(f"📊 {pair} | Цена: {price}")

        if is_closed:
            global candle_data
            df = candle_data[pair]
            new_row = pd.DataFrame({"timestamp": [timestamp], "close": [price]})
            candle_data[pair] = pd.concat([df, new_row], ignore_index=True)

            # Сохраняем последние 100 свечей
            if len(candle_data[pair]) > 100:
                candle_data[pair] = candle_data[pair].iloc[-100:]

            # Рассчитываем индикаторы
            rsi = calculate_rsi(candle_data[pair])
            sma_50 = calculate_sma(candle_data[pair], period=50)
            sma_200 = calculate_sma(candle_data[pair], period=200)

            # Проверка сигналов на Лонг/Шорт
            signal = ""
            if rsi and sma_50 and sma_200:
                if rsi < 30 and sma_50 > sma_200:
                    signal = f"🚀 **Лонг** {pair} | Цена: {price} | RSI: {rsi:.2f}"
                elif rsi > 70 and sma_50 < sma_200:
                    signal = f"⚠️ **Шорт** {pair} | Цена: {price} | RSI: {rsi:.2f}"

            if signal:
                asyncio.run(send_telegram_message(signal))

def start_websocket():
    """🔹 Запуск WebSocket"""
    ws = websocket.WebSocketApp(BINANCE_WS_URL, on_message=on_message)
    ws.run_forever()

async def start(update: Update, context):
    keyboard = [
        [KeyboardButton("📈 Order Book ADA"), KeyboardButton("📈 Order Book IP")],
        [KeyboardButton("📈 Order Book TST")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("✅ Бот запущен! Выберите действие:", reply_markup=reply_markup)

async def handle_message(update: Update, context):
    text = update.message.text
    if text == "📈 Order Book ADA":
        result = await get_order_book("ADAUSDT")
        await update.message.reply_text(result)
    elif text == "📈 Order Book IP":
        result = await get_order_book("IPUSDT")
        await update.message.reply_text(result)
    elif text == "📈 Order Book TST":
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
    """🔹 Запуск WebSocket и Telegram-бота"""
    loop = asyncio.get_running_loop()
    telegram_task = asyncio.create_task(run_telegram_bot())
    websocket_task = loop.run_in_executor(None, start_websocket)
    await asyncio.gather(telegram_task, websocket_task)

if __name__ == "__main__":
    asyncio.run(main(), debug=True)
