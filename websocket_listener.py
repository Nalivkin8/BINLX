import websocket
import json
import asyncio

# Подключение к WebSocket Binance Futures
async def start_futures_websocket(bot, chat_id):
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws/btcusdt@trade",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(bot, chat_id, msg)),
        on_open=on_open
    )

    await asyncio.to_thread(ws.run_forever)

async def process_futures_message(bot, chat_id, message):
    data = json.loads(message)
    price = float(data['p'])
    await bot.send_message(chat_id, f"🔥 Текущая цена BTC/USDT (Futures): {price}")

def on_open(ws):
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["btcusdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
