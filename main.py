import asyncio
import json
import os
import websocket
import requests
import pandas as pd
from telegram import Bot
from datetime import datetime
from statistics import mean

# 🔹 API-ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 🔹 Список торговых пар (нижний регистр)
TRADE_PAIRS = ["adausdt", "ipusdt", "tstusdt"]

def check_binance_pairs():
    """🔹 Проверяем, торгуются ли пары на Binance Futures"""
    print("🔎 Проверяем доступные пары на Binance Futures...")
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
                print("❌ Ни одна из пар не найдена на Binance Futures.")
                exit()
            return valid_pairs
        else:
            print(f"⚠️ Ошибка получения данных: {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка подключения к Binance: {e}")
        return []

# 🔹 Обновляем список пар (убираем несуществующие)
TRADE_PAIRS = check_binance_pairs()

if not TRADE_PAIRS:
    print("❌ Нет доступных пар для работы. Проверь Binance Futures.")
    exit()

# 🔹 WebSocket Binance Futures
STREAMS = [f"{pair}@kline_1m" for pair in TRADE_PAIRS]
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams=" + "/".join(STREAMS)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
candle_data = {pair: pd.DataFrame(columns=["timestamp", "close", "volume"]) for pair in TRADE_PAIRS}

def on_message(ws, message):
    """🔹 Обработка входящих данных из WebSocket"""
    data = json.loads(message)

    if "stream" in data and "data" in data:
        stream = data["stream"]
        pair = stream.split("@")[0].upper()

        if pair not in TRADE_PAIRS:
            print(f"⚠️ Получены данные для неизвестной пары: {pair}")
            return

        price = float(data["data"]["k"]["c"])
        timestamp = data["data"]["k"]["t"]
        volume = float(data["data"]["k"]["v"])

        print(f"✅ {pair}: Цена {price} | Объем {volume}")

def on_error(ws, error):
    """🔹 Лог ошибок WebSocket"""
    print(f"❌ Ошибка WebSocket: {error}")

def start_websocket():
    """🔹 Запуск WebSocket"""
    print("🔄 Подключение к Binance WebSocket...")
    ws = websocket.WebSocketApp(
        BINANCE_WS_URL,
        on_message=on_message,
        on_error=on_error
    )
    ws.run_forever()

async def main():
    """🔹 Запуск WebSocket-бота"""
    loop = asyncio.get_running_loop()
    websocket_task = loop.run_in_executor(None, start_websocket)
    await asyncio.gather(websocket_task)

if __name__ == "__main__":
    print("🚀 Запуск бота...")
    asyncio.run(main(), debug=True)
