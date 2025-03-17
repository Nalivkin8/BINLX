import websocket
import json
import asyncio
import pandas as pd
import time
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from balance_checker import get_balance, get_open_positions

# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Создаём бота и диспетчер
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Храним активные сделки
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}

# Команда /balance
@dp.message()
async def balance_command(message: Message):
    if message.text == "/balance":
        balance = get_balance()
        positions = get_open_positions()
        await message.answer(f"{balance}\n\n{positions}")

# Подключение к WebSocket Binance Futures
async def start_futures_websocket():
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(msg)),
        on_open=on_open  
    )
    await asyncio.to_thread(ws.run_forever)

# Функция обработки событий при подключении к WebSocket
def on_open(ws):
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["tstusdt@trade", "ipusdt@trade", "adausdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
    print("✅ Подключено к WebSocket Binance Futures")

# Запуск бота и WebSocket в Aiogram 3.x
async def main():
    asyncio.create_task(start_futures_websocket())  # Запуск WebSocket
    await dp.start_polling(bot)  # Запуск Telegram-бота

if __name__ == "__main__":
    asyncio.run(main())
