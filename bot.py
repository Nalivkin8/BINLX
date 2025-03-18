import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter
from websocket_listener import start_futures_websocket
from indicators import compute_rsi, compute_macd, compute_atr

# 🔹 Загружаем переменные среды из Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Ошибка: TELEGRAM_CHAT_ID не задан в Railway Variables!")

# 🔹 Создаём бота и диспетчер
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# 🔹 Запуск WebSocket и бота
async def main():
    print("🚀 Бот стартует...")
    asyncio.create_task(start_futures_websocket(bot, TELEGRAM_CHAT_ID))  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
