import websocket
import json
import asyncio
import pandas as pd
import time
from aiogram.exceptions import TelegramRetryAfter

# Храним активные сделки и историю цен
active_trades = {}  # {"TSTUSDT": {"signal": "LONG", "entry": 5.50, "tp": 6.05, "sl": 5.23}}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}
last_signal_time = {}  # Последнее время сигнала для каждой пары

# Подключение к WebSocket Binance Futures
async def start_futures_websocket(bot, chat_id):
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(bot, chat_id, msg)),
        on_open=on_open
    )
    await asyncio.to_thread(ws.run_forever)

# Подписка на пары
def on_open(ws):
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["tstusdt@trade", "ipusdt@trade", "adausdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
    print("✅ Подключено к WebSocket Binance Futures")

# Обрабатываем входящие данные с Binance WebSocket
async def process_futures_message(bot, chat_id, message):
    global active_trades, price_history, last_signal_time
    try:
        data = json.loads(message)

        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            # Проверяем активные сделки
            if symbol in active_trades:
                trade = active_trades[symbol]

                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    await send_message_safe(bot, chat_id, f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT, +{trade['tp_percent']}%)**")
                    del active_trades[symbol]

                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    await send_message_safe(bot, chat_id, f"⛔ **{symbol} достиг Stop Loss ({trade['sl']} USDT, -{trade['sl_percent']}%)**")
                    del active_trades[symbol]

                return  # Если есть активная сделка, дальше не анализируем

            # Сохраняем историю цен
            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 200:
                    price_history[symbol].pop(0)

                    df = pd.DataFrame(price_history[symbol], columns=['close'])
                    atr = compute_atr(df)
                    last_price = df['close'].iloc[-1]

                    # Гибкие TP и SL в зависимости от ATR и тренда
                    tp_percent = round(10 + atr * 2, 1)  # Минимум 10%, но растёт с волатильностью
                    sl_percent = round(5 + atr, 1)  # Минимум 5%, но зависит от ATR

                    signal = None
                    if last_price > df['close'].mean() and atr > 0.05:
                        signal = "LONG"
                    elif last_price < df['close'].mean() and atr > 0.05:
                        signal = "SHORT"

                    # Проверяем время последнего сигнала, чтобы избежать спама
                    if signal and (symbol not in last_signal_time or time.time() - last_signal_time[symbol] > 60):
                        entry_price = last_price
                        tp = round(entry_price * (1 + tp_percent / 100), 5) if signal == "LONG" else round(entry_price * (1 - tp_percent / 100), 5)
                        sl = round(entry_price * (1 - sl_percent / 100), 5) if signal == "LONG" else round(entry_price * (1 + sl_percent / 100), 5)

                        active_trades[symbol] = {
                            "signal": signal, "entry": entry_price, "tp": tp, "sl": sl,
                            "tp_percent": tp_percent, "sl_percent": sl_percent
                        }
                        last_signal_time[symbol] = time.time()

                        message = (
                            f"📌 **Сигнал на {signal} {symbol} (Futures)**\n"
                            f"🔹 **Вход**: {entry_price} USDT\n"
                            f"🎯 **TP**: {tp} USDT | +{tp_percent}%\n"
                            f"⛔ **SL**: {sl} USDT | -{sl_percent}%"
                        )
                        await send_message_safe(bot, chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# Безопасная отправка сообщений в Telegram
async def send_message_safe(bot, chat_id, message):
    try:
        await bot.send_message(chat_id, message)
    except TelegramRetryAfter as e:
        print(f"⏳ Telegram ограничил отправку, ждем {e.retry_after} сек...")
        await asyncio.sleep(e.retry_after)
        await send_message_safe(bot, chat_id, message)
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")

# Функция расчёта ATR (гибкий Stop Loss)
def compute_atr(df, period=14):
    high = df['close'].shift(1)
    low = df['close'].shift(-1)
    tr = abs(high - low)
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1] if not atr.empty else 0.05  # Минимальное значение ATR

