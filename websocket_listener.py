import websocket
import json
import asyncio
import pandas as pd
import time

# Переменные для контроля частоты сигналов
last_sent_time = 0
last_signal = None
price_history = []

# Подключение к WebSocket Binance Futures
async def start_futures_websocket(bot, chat_id):
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws/btcusdt@trade",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(bot, chat_id, msg)),
        on_open=on_open
    )

    await asyncio.to_thread(ws.run_forever)

# Обрабатываем сообщения WebSocket
async def process_futures_message(bot, chat_id, message):
    global last_sent_time, last_signal, price_history
    try:
        data = json.loads(message)
        price = float(data.get('p', 0))  # Получаем текущую цену

        if price > 0:
            price_history.append(price)

            # Храним только 50 последних цен
            if len(price_history) > 50:
                price_history.pop(0)

                df = pd.DataFrame(price_history, columns=['close'])
                df['SMA_50'] = df['close'].rolling(window=50).mean()
                df['RSI'] = compute_rsi(df['close'])
                df['MACD'], df['Signal_Line'] = compute_macd(df['close'])

                last_rsi = df['RSI'].iloc[-1]
                last_macd = df['MACD'].iloc[-1]
                last_signal_line = df['Signal_Line'].iloc[-1]

                # Генерация прогноза
                signal = None
                if last_rsi < 30 and last_macd > last_signal_line:
                    signal = "LONG"
                elif last_rsi > 70 and last_macd < last_signal_line:
                    signal = "SHORT"

                # Отправляем сигнал только если он новый и прошло >3 минут
                current_time = time.time()
                if signal and (last_signal != signal or current_time - last_sent_time > 180):
                    last_signal = signal
                    last_sent_time = current_time
                    take_profit = round(price * 1.02, 2)  # +2% от цены
                    stop_loss = round(price * 0.98, 2)   # -2% от цены
                    message = (
                        f"📌 **Сигнал на {signal} BTC/USDT (Futures)**\n"
                        f"🔹 **Цена входа**: {price} USDT\n"
                        f"🎯 **Take Profit**: {take_profit} USDT\n"
                        f"⛔ **Stop Loss**: {stop_loss} USDT\n"
                        f"📊 **RSI**: {round(last_rsi, 2)}\n"
                        f"📊 **MACD**: {round(last_macd, 2)} / {round(last_signal_line, 2)}"
                    )
                    await bot.send_message(chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# Функция расчета RSI
def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Функция расчета MACD
def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window, adjust=False).mean()
    long_ema = prices.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

# Подписываемся на WebSocket Binance Futures
def on_open(ws):
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["btcusdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
