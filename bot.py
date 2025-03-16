import os
import asyncio
from aiogram import Bot, Dispatcher
from websocket_listener import start_futures_websocket  # WebSocket с новыми парами

# Загружаем переменные окружения (Railway Variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

async def main():
    asyncio.create_task(start_futures_websocket(bot, CHAT_ID))  # Запускаем WebSocket
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
