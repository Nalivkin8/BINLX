import json
import asyncio
import requests
import os
import websockets  # Убедимся, что websockets установлен
from python_binance.client import Client
from python_binance.enums import *
from telegram import Bot
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Проверяем, загружены ли переменные окружения
if not all([API_KEY, API_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("Не все переменные окружения загружены! Проверьте .env файл.")

# Подключаем клиента Binance
client = Client(API_KEY, API_SECRET)
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Подключение к WebSocket Binance
async def binance_websocket(symbol):
    url = f"wss://stream.binance.com:9443/ws/{symbol}@kline_1m"
    async with websockets.connect(url) as websocket:
        while True:
            try:
                data = await websocket.recv()
                process_message(json.loads(data))
            except Exception as e:
                print(f"Ошибка WebSocket: {e}")
                await asyncio.sleep(5)  # Переподключение через 5 сек

# Обработка полученных данных
def process_message(message):
    kline = message.get("k", {})
    close_price = float(kline.get("c", 0))
    volume = float(kline.get("v", 0))
    
    signal = analyze_market(close_price, volume)
    if signal:
        send_telegram_message(signal)

# Анализ рынка (простая логика для примера)
def analyze_market(price, volume):
    if volume > 100:  # Пример: если объём больше 100, даём сигнал
        return f"Сигнал: {'ЛОНГ' if price % 2 == 0 else 'ШОРТ'}\nЦена: {price}\nОбъём: {volume}"
    return None

# Отправка сигнала в Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    response = requests.post(url, data=data)
    if response.status_code != 200:
        print(f"Ошибка отправки в Telegram: {response.text}")

# Запуск WebSocket
if __name__ == "__main__":
    symbol = "btcusdt"  # Пара для торговли
    try:
        asyncio.run(binance_websocket(symbol))
    except KeyboardInterrupt:
        print("Программа остановлена пользователем.")

# Файл .env.example
with open(".env.example", "w") as f:
    f.write("""
BINANCE_API_KEY=
BINANCE_API_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
""")

# Файл Procfile
with open("Procfile", "w") as f:
    f.write("worker: python main.py")

# Файл requirements.txt
with open("requirements.txt", "w") as f:
    f.write("""
python-binance
python-telegram-bot
websockets
python-dotenv
requests
""")
