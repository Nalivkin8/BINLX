import os
import asyncio
from aiogram import Bot, Dispatcher
from indicators import get_futures_data, compute_indicators, generate_signal
from websocket_listener import start_futures_websocket

# Загружаем переменные окружения (Railway Variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Отправка сигналов в Telegram
async def send_signal(signal, price, take_profit, stop_loss):
    message = (
        f"📌 **Сигнал на {signal} (Futures) BTC/USDT**\n"
        f"🔹 **Цена входа**: {price} USDT\n"
        f"🎯 **Take Profit**: {take_profit} USDT\n"
        f"⛔ **Stop Loss**: {stop_loss} USDT\n"
    )
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

# Анализ рынка и отправка сигналов
async def check_futures_market():
    while True:
        df = get_futures_data("BTCUSDT")
        if df.empty:
            print("⚠️ Binance Futures API вернул пустые данные!")
        else:
            df = compute_indicators(df)
            signal, price, take_profit, stop_loss = generate_signal(df)
            if signal:
                await send_signal(signal, price, take_profit, stop_loss)

        await asyncio.sleep(60)  # Проверка рынка каждую минуту

async def main():
    asyncio.create_task(start_futures_websocket(bot, CHAT_ID))  # Запускаем WebSocket
    asyncio.create_task(check_futures_market())  # Запускаем анализ рынка
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
