import os
import asyncio
from aiogram import Bot, Dispatcher
from indicators import get_historical_data, compute_indicators, generate_signal
from websocket_listener import start_websocket
from binance.client import Client

# Загружаем ключи Binance из Railway Variables
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# Загружаем ключи Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Подключение к Binance API
client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Отправка сигналов в Telegram
async def send_signal(signal, price):
    message = f"📌 **Сигнал на {signal} BTC/USDT**\n🔹 **Цена**: {price} USDT"
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

# Получение баланса USDT
def get_balance():
    balance = client.get_asset_balance(asset='USDT')
    return float(balance['free']) if balance else 0.0

# Размещение ордера на покупку/продажу
def place_order(symbol, side, quantity):
    order = client.create_order(
        symbol=symbol,
        side=side,
        type='MARKET',
        quantity=quantity
    )
    return order

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

                # Пример авто-торговли (можно выключить)
                balance = get_balance()
                if balance > 10:  # Если баланс > $10, пробуем войти в сделку
                    qty = round(10 / price, 6)  # Количество BTC на $10
                    order = place_order("BTCUSDT", "BUY" if signal == "BUY" else "SELL", qty)
                    print(f"🚀 Сделка выполнена: {order}")

        await asyncio.sleep(60)  # Проверка рынка каждую минуту

async def main():
    asyncio.create_task(start_websocket(bot, CHAT_ID))  # Запускаем WebSocket
    asyncio.create_task(check_market())  # Запускаем анализ рынка
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
