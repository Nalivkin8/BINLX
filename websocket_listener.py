import websocket
import json

def on_message(ws, message):
    data = json.loads(message)
    price = float(data['p'])
    print(f"🔥 Текущая цена BTC/USDT: {price}")

def on_open(ws):
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["btcusdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)

def start_websocket():
    ws = websocket.WebSocketApp(
        "wss://stream.binance.com:9443/ws/btcusdt@trade",
        on_message=on_message,
        on_open=on_open
    )
    ws.run_forever()
