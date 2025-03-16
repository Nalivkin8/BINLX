import websocket
import json
import asyncio
import pandas as pd
import time
from aiogram.exceptions import TelegramRetryAfter

# Переменные для контроля частоты сигналов
last_sent_time = 0
last_signal = {}
price_history = {"TSTUSDT": [], "IPUSDT": []}  # Храним данные для каждой пары отдельно

# Подключение к WebSocket Binance Futures
async def start_futures_websocket(bot, chat_id):
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(bot, chat_id, msg)),
        on_open=on_open
    )
    await asyncio.to_thread(ws.run_forever)

# Обрабатываем сообщения WebSocket
async def process_futures_message(bot, chat_id, message):
    global last_sent_time, last_signal, price_history
    try:
        data = json.loads(message)

        # Проверяем, что это трейд-сообщение
        if 's' in data and 'p' in data:
            symbol = data['s']  # TSTUSDT или IPUSDT
            price = float(data['p'])

            if symbol in price_history:
                price_history[symbol].append(price)

                # Храним только 50 последних цен
                if len(price_history[symbol]) > 50:
                    price_history[symbol].pop(0)

                    df = pd.DataFrame(price_history[symbol], columns=['close'])
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
                    if signal and (last_signal.get(symbol) != signal or current_time - last_sent_time > 180):
                        last_signal[symbol] = signal
                        last_sent_time = current_time
                        take_profit = round(price * 1.02, 2)  # +2% от цены
                        stop_loss = round(price * 0.98, 2)   # -2% от цены
                        message = (
                            f"📌 **Сигнал на {signal} {symbol} (Futures)**\n"
                            f"🔹 **Цена входа**: {price} USDT\n"
                            f"🎯 **Take Profit**: {take_profit} USDT\n"
                            f"⛔ **Stop Loss**: {stop_loss} USDT\n"
                            f"📊 **RSI**: {round(last_rsi, 2)}\n"
                            f"📊 **MACD**: {round(last_macd, 2)} / {round(last_signal_line, 2)}"
                        )
                        await send_message_safe(bot, chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# Безопасная отправка сообщений (избегает блокировки Telegram)
async def send_message_safe(bot, chat_id, message):
    try:
        await bot.send_message(chat_id, message)
    except TelegramRetryAfter as e:
        print(f"⚠️ Telegram просит подождать {e.retry_after} секунд. Ожидаем...")
        await asyncio.sleep(e.retry_after)
        await bot.send_message(chat_id, message)
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения: {e}")

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
        "params": ["tstusdt@trade", "ipusdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
