import os
import asyncio
from aiogram import Bot, Dispatcher, types
from indicators import get_historical_data, compute_indicators, generate_signal

# Загружаем ключи из Railway Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)

async def send_signal(signal, price):
    message = f"📌 **Сигнал на {signal} BTC/USDT**\n🔹 **Цена**: {price} USDT"
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

async def check_market():
    while True:
        df = get_historical_data("BTCUSDT")
        df = compute_indicators(df)
        signal, price = generate_signal(df)

        if signal:
            await send_signal(signal, price)

        await asyncio.sleep(60)  # Запуск анализа каждую минуту

async def main():
    await asyncio.gather(dp.start_polling(), check_market())

if __name__ == "__main__":
    asyncio.run(main())
