import websocket
import json
import asyncio
import time

last_sent_price = None
last_sent_time = 0

async def process_futures_message(bot, chat_id, message):
    global last_sent_price, last_sent_time
    try:
        data = json.loads(message)
        price = float(data.get('p', 0))  # Используем get() для безопасности

        # Проверяем, изменился ли курс с момента последнего сообщения
        if price > 0 and (last_sent_price is None or abs(price - last_sent_price) > 5):  
            current_time = time.time()
            if current_time - last_sent_time >= 10:  # Минимальный интервал в 10 секунд
                last_sent_price = price
                last_sent_time = current_time
                await bot.send_message(chat_id, f"🔥 Текущая цена BTC/USDT (Futures): {price}")
    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")
