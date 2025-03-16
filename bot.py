import os
import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message

from indicators import get_historical_data, compute_indicators, generate_signal

# Загружаем ключи из Railway Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()  # Создаем router

# Функция для отправки сигналов
async def send_signal(signal, price):
    message = f"📌 **Сигнал на {signal} BTC/USDT**\n🔹 **Цена**: {price} USDT"
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

# Проверяем рынок каждую минуту
async def check_market():
    while True:
        df = get_historical_data("BTCUSDT")
        df = compute_indicators(df)
        signal, price = generate_signal(df)

        if signal:
            await send_signal(signal, price)

        await asyncio.sleep(60)  # Запуск анализа каждую минуту

# Команда /start
@router.message()
async def start_handler(message: Message):
    await message.answer("🚀 Бот запущен и мониторит рынок!")

async def main():
    dp.include_router(router)  # Добавляем router
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(check_market())  # Запускаем анализ рынка
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
