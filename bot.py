import os
import asyncio
from aiogram import Bot, Dispatcher
from indicators import get_historical_data, compute_indicators, generate_signal
from websocket_listener import start_websocket

# Загружаем переменные окружения (Railway Variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Отправка сигналов в Telegram
async def send_signal(signal, price):
    message = f"📌 **Сигнал на {signal} BTC/USDT**\n🔹 **Цена**: {price} USDT"
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

# Анализ рынка и отправка сигналов
async def check_market():
    while True:
        df = get_historical_data("BTCUSDT")
        if df.empty:
            print("⚠️ Binance API вернул пустые данные!")
        else:
            df = compute_indicators(df)
            signal, price = generate_signal(df)
            if signal:
                await send_signal(signal, price)

        await asyncio.sleep(60)  # Проверка рынка каждую минуту

async def main():
    asyncio.create_task(start_websocket(bot, CHAT_ID))  # Запускаем WebSocket
    asyncio.create_task(check_market())  # Запускаем анализ рынка
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
