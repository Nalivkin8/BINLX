import websocket
import json
import asyncio
import pandas as pd
from indicators import compute_rsi, compute_macd, compute_atr
from aiogram.exceptions import TelegramRetryAfter

# 🔹 Храним активные сделки
active_trades = {}  
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": [], "ETHUSDT": []}

# 🔹 Подключение к WebSocket Binance Futures
async def start_futures_websocket(bot, chat_id):
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(bot, chat_id, msg)),
        on_open=on_open
    )
    await asyncio.to_thread(ws.run_forever)

# 🔹 Подписка на свечи Binance Futures
def on_open(ws):
    print("✅ Успешное подключение к WebSocket!")
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": [
            "tstusdt@kline_1m", "tstusdt@kline_15m", "tstusdt@kline_30m", "tstusdt@kline_1h",
            "ipusdt@kline_1m", "ipusdt@kline_15m", "ipusdt@kline_30m", "ipusdt@kline_1h",
            "adausdt@kline_1m", "adausdt@kline_15m", "adausdt@kline_30m", "adausdt@kline_1h",
            "ethusdt@kline_1m", "ethusdt@kline_15m", "ethusdt@kline_30m", "ethusdt@kline_1h"
        ],
        "id": 1
    })
    ws.send(subscribe_message)
    print("📩 Подписка на Binance Futures (свечи)")

# 🔹 Обрабатываем входящие данные WebSocket
async def process_futures_message(bot, chat_id, message):
    global active_trades, price_history
    try:
        data = json.loads(message)

        if 'k' in data:
            candle = data['k']
            symbol = data['s']
            close_price = float(candle['c'])  # Цена закрытия

            print(f"📊 {symbol}: Закрытие свечи {close_price} USDT")

            if symbol in price_history:
                price_history[symbol].append(close_price)

                if len(price_history[symbol]) > 50:
                    price_history[symbol].pop(0)

                df = pd.DataFrame(price_history[symbol], columns=['close'])
                df['ATR'] = compute_atr(df)
                df['RSI'] = compute_rsi(df['close'])
                df['MACD'], df['Signal_Line'] = compute_macd(df['close'])

                last_rsi = df['RSI'].iloc[-1]
                last_macd = df['MACD'].iloc[-1]
                last_signal_line = df['Signal_Line'].iloc[-1]
                last_atr = df['ATR'].iloc[-1]

                signal = None
                if last_macd > last_signal_line and last_rsi < 50:
                    signal = "LONG"
                elif last_macd < last_signal_line and last_rsi > 50:
                    signal = "SHORT"

                if symbol in active_trades:
                    return  

                if signal:
                    tp = round(close_price * (1 + last_atr), 6) if signal == "LONG" else round(close_price * (1 - last_atr), 6)
                    sl = round(close_price * (1 - last_atr * 0.5), 6) if signal == "LONG" else round(close_price * (1 + last_atr * 0.5), 6)

                    active_trades[symbol] = {"signal": signal, "entry": close_price, "tp": tp, "sl": sl}

                    message = (
                        f"🔹 **{signal} {symbol} (Futures)**\n"
                        f"🔹 **Вход**: {close_price} USDT\n"
                        f"🎯 **TP**: {tp} USDT\n"
                        f"⛔ **SL**: {sl} USDT"
                    )
                    await send_message_safe(bot, chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Безопасная отправка сообщений в Telegram
async def send_message_safe(bot, chat_id, message):
    try:
        print(f"📤 Отправка сообщения в Telegram: {message}")
        await bot.send_message(chat_id, message)
    except TelegramRetryAfter as e:
        print(f"⏳ Telegram ограничил отправку, ждем {e.retry_after} сек...")
        await asyncio.sleep(e.retry_after)
        await send_message_safe(bot, chat_id, message)
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")
