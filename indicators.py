import websocket
import json
import asyncio
import time

last_sent_price = None
last_sent_time = 0

# Подключение к WebSocket Binance Futures
async def start_futures_websocket(bot, chat_id):
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws/btcusdt@trade",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(bot, chat_id, msg)),
        on_open=on_open
    )

    await asyncio.to_thread(ws.run_forever)

# Фильтруем сообщения, чтобы Telegram не блокировал бота
async def process_futures_message(bot, chat_id, message):
    global last_sent_price, last_sent_time
    try:
        data = json.loads(message)
        price = float(data.get('p', 0))  # Проверяем, что 'p' есть в данных

        # Проверяем, изменился ли курс с момента последнего сообщения
        if price > 0 and (last_sent_price is None or abs(price - last_sent_price) > 5):
            current_time = time.time()
            if current_time - last_sent_time >= 10:  # Минимальный интервал 10 сек
                last_sent_price = price
                last_sent_time = current_time
                await bot.send_message(chat_id, f"🔥 Текущая цена BTC/USDT (Futures): {price}")

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# Отправляем подписку на Binance WebSocket
def on_open(ws):
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["btcusdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
