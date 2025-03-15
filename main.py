import asyncio
import json
import os
import websocket
import requests
import pandas as pd
from statistics import mean
from telegram import Bot, Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# 🔹 API-ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 🔹 Список торговых пар
TRADE_PAIRS = ["adausdt", "ipusdt", "tstusdt"]

def check_binance_pairs():
    """🔍 Проверяем, какие пары торгуются на Binance Futures"""
    print("🔍 Проверяем доступные пары на Binance Futures...")
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            valid_pairs = [
                pair for pair in TRADE_PAIRS 
                if any(symbol["symbol"].lower() == pair for symbol in data["symbols"])
            ]
            if not valid_pairs:
                print("❌ Нет доступных пар. Проверь Binance Futures.")
                exit()
            return valid_pairs
        else:
            print(f"⚠️ Ошибка Binance: {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка подключения: {e}")
        return []

# 🔹 Обновляем список пар (убираем несуществующие)
TRADE_PAIRS = check_binance_pairs()
if not TRADE_PAIRS:
    print("❌ Нет доступных пар. Проверь Binance Futures.")
    exit()

# 🔹 WebSocket Binance Futures
STREAMS = [f"{pair}@kline_5m" for pair in TRADE_PAIRS]
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams=" + "/".join(STREAMS)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
candle_data = {pair: pd.DataFrame(columns=["timestamp", "close"]) for pair in TRADE_PAIRS}
last_signal = {pair: None for pair in TRADE_PAIRS}  # Запоминаем последний сигнал

async def send_telegram_message(text):
    """🔹 Отправка сообщений в Telegram"""
    print(f"📨 Telegram: {text}")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

def calculate_rsi(df, period=14):
    """🔹 Рассчет RSI"""
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else None

def calculate_sma(df, period=50):
    """🔹 Рассчет SMA"""
    return df["close"].rolling(window=period).mean().iloc[-1] if not df.empty else None

def calculate_volatility(df, period=20):
    """🔹 Рассчет волатильности (Средний размах свечей)"""
    if len(df) < period:
        return None
    return mean(df["close"].diff().abs().tail(period))

def on_message(ws, message):
    """🔹 Обработка входящих данных из WebSocket"""
    data = json.loads(message)

    if "stream" in data and "data" in data:
        stream = data["stream"]
        pair = stream.split("@")[0].upper()
        event_type = stream.split("@")[1]

        if event_type.startswith("kline"):
            price = float(data["data"]["k"]["c"])
            timestamp = data["data"]["k"]["t"]
            is_closed = data["data"]["k"]["x"]

            if is_closed:
                df = candle_data[pair]
                new_row = pd.DataFrame({"timestamp": [timestamp], "close": [price]})
                candle_data[pair] = pd.concat([df, new_row], ignore_index=True)

                if len(candle_data[pair]) > 100:
                    candle_data[pair] = candle_data[pair].iloc[-100:]

                # Рассчитываем индикаторы
                rsi = calculate_rsi(candle_data[pair])
                sma_50 = calculate_sma(candle_data[pair], period=50)
                sma_200 = calculate_sma(candle_data[pair], period=200)
                volatility = calculate_volatility(candle_data[pair])

                # Условия для Лонга/Шорта
                signal = ""
                take_profit = None
                stop_loss = None

                if rsi and sma_50 and sma_200 and volatility:
                    risk_factor = round(volatility * 3, 6)  # Динамический Тейк-Профит (3x волатильности)

                    if rsi < 30 and sma_50 > sma_200:
                        take_profit = round(price + risk_factor, 6)
                        stop_loss = round(price - (risk_factor / 2), 6)
                        signal = f"🚀 **Лонг {pair}**\n💰 Цена: {price}\n🎯 TP: {take_profit}\n🛑 SL: {stop_loss}\n📊 RSI: {rsi:.2f} | SMA-50 > SMA-200"

                    elif rsi > 70 and sma_50 < sma_200:
                        take_profit = round(price - risk_factor, 6)
                        stop_loss = round(price + (risk_factor / 2), 6)
                        signal = f"⚠️ **Шорт {pair}**\n💰 Цена: {price}\n🎯 TP: {take_profit}\n🛑 SL: {stop_loss}\n📊 RSI: {rsi:.2f} | SMA-50 < SMA-200"

                if signal and last_signal[pair] != signal:
                    last_signal[pair] = signal  # Запоминаем последний сигнал
                    asyncio.run(send_telegram_message(signal))

def start_websocket():
    """🔹 Запуск WebSocket"""
    ws = websocket.WebSocketApp(BINANCE_WS_URL, on_message=on_message)
    ws.run_forever()

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
