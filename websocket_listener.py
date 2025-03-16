import websocket
import json
import asyncio

# Подключение к WebSocket Binance (ASYNC)
async def start_websocket(bot, chat_id):
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://stream.binance.com:9443/ws/btcusdt@trade",
        on_message=lambda ws, msg: loop.create_task(process_message(bot, chat_id, msg)),
        on_open=on_open
    )

    # Запускаем WebSocket в отдельном потоке
    await asyncio.to_thread(ws.run_forever)

async def process_message(bot, chat_id, message):
    data = json.loads(message)
    price = float(data['p'])
    await bot.send_message(chat_id, f"🔥 Текущая цена BTC/USDT: {price}")

def on_open(ws):
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["btcusdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
