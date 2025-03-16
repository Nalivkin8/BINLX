from aiogram import Bot, Dispatcher
import asyncio

# Загружаем ключи из Railway Variables
import os
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()  # Исправлено!

async def send_signal(signal, price):
    message = f"📌 **Сигнал на {signal} BTC/USDT**\n🔹 **Цена**: {price} USDT"
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

async def main():
    dp.include_router(send_signal)  # Aiogram 3 требует router
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
