import websocket
import json
import asyncio

# Подключение к WebSocket Binance
def start_websocket(bot, chat_id):
    def on_message(ws, message):
        data = json.loads(message)
        price = float(data['p'])
        asyncio.run(send_price(bot, chat_id, price))

    def on_open(ws):
        subscribe_message = json.dumps({
            "method": "SUBSCRIBE",
            "params": ["btcusdt@trade"],
            "id": 1
        })
        ws.send(subscribe_message)

    ws = websocket.WebSocketApp(
        "wss://stream.binance.com:9443/ws/btcusdt@trade",
        on_message=on_message,
        on_open=on_open
    )
    ws.run_forever()

async def send_price(bot, chat_id, price):
    await bot.send_message(chat_id, f"🔥 Текущая цена BTC/USDT: {price}")
