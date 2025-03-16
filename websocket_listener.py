import websocket
import json
import asyncio
import pandas as pd
import time
from aiogram.exceptions import TelegramRetryAfter

# Храним активные сделки
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": []}

# Подключение к WebSocket Binance Futures
async def start_futures_websocket(bot, chat_id):
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(bot, chat_id, msg)),
        on_open=on_open  
    )
    await asyncio.to_thread(ws.run_forever)

# Функция обработки событий при подключении к WebSocket
def on_open(ws):
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["tstusdt@trade", "ipusdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
    print("✅ Подключено к WebSocket Binance Futures")
    print("📩 Подписка на пары отправлена: TSTUSDT, IPUSDT")

# Обрабатываем сообщения WebSocket
async def process_futures_message(bot, chat_id, message):
    global active_trades, price_history
    try:
        print(f"🔄 Получены данные от Binance: {message}")

        data = json.loads(message)
        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            # Проверяем активные сделки
            if symbol in active_trades:
                trade = active_trades[symbol]

                # TP достигнут → закрытие сделки
                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    print(f"🎯 {symbol} достиг Take Profit ({trade['tp']} USDT)")
                    await bot.send_message(chat_id, f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]

                # SL достигнут → закрытие сделки
                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    print(f"⛔ {symbol} достиг Stop Loss ({trade['sl']} USDT)")
                    await bot.send_message(chat_id, f"⛔ **{symbol} достиг Stop Loss ({trade['sl']} USDT)**")
                    del active_trades[symbol]

                return  

            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 200:
                    price_history[symbol].pop(0)

                df = pd.DataFrame(price_history[symbol], columns=['close'])
                df['ATR'] = compute_atr(df)
                df['Support'], df['Resistance'] = compute_support_resistance(df)
                df['RSI'] = compute_rsi(df['close'])
                df['MACD'], df['Signal_Line'] = compute_macd(df['close'])
                df['ADX'] = compute_adx(df)

                # Рассчитываем скользящие средние
                df['SMA_20'] = df['close'].rolling(window=20).mean()
                df['SMA_50'] = df['close'].rolling(window=50).mean()
                df['EMA_9'] = df['close'].ewm(span=9, adjust=False).mean()
                df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()
                df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
                df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()

                # Определяем тренд по EMA 50 / 200
                trend = "Neutral"
                if df['EMA_50'].iloc[-1] > df['EMA_200'].iloc[-1]:
                    trend = "Bullish"
                elif df['EMA_50'].iloc[-1] < df['EMA_200'].iloc[-1]:
                    trend = "Bearish"

                last_atr = df['ATR'].iloc[-1]
                last_support = df['Support'].iloc[-1]
                last_resistance = df['Resistance'].iloc[-1]
                last_rsi = df['RSI'].iloc[-1]
                last_macd = df['MACD'].iloc[-1]
                last_signal_line = df['Signal_Line'].iloc[-1]
                last_adx = df['ADX'].iloc[-1]

                signal = None
                if (
                    last_macd > last_signal_line
                    and last_adx > 10
                    and (last_rsi < 40 or (last_rsi < 50 and last_adx < 20))
                    and trend == "Bullish"  
                    and (df['EMA_9'].iloc[-1] > df['EMA_21'].iloc[-1])  
                    and (price > df['SMA_20'].iloc[-1])  
                ):  
                    signal = "LONG"

                elif (
                    last_macd < last_signal_line
                    and last_adx > 10
                    and (last_rsi > 60 or (last_rsi > 75 and last_adx < 20))
                    and trend == "Bearish"
                    and (df['EMA_9'].iloc[-1] < df['EMA_21'].iloc[-1])  
                    and (price < df['SMA_20'].iloc[-1])  
                ):  
                    signal = "SHORT"

                if signal:
                    tp = round(last_resistance, 2) if signal == "LONG" else round(last_support, 2)
                    sl = round(price - last_atr, 2) if signal == "LONG" else round(price + last_atr, 2)

                    active_trades[symbol] = {"signal": signal, "entry": price, "tp": tp, "sl": sl}

                    print(f"📢 Генерация сигнала: {signal} {symbol}, Цена входа: {price}")

                    message = (
                        f"📌 **Сигнал на {signal} {symbol} (Futures)**\n"
                        f"🔹 **Цена входа**: {price} USDT\n"
                        f"🎯 **Take Profit**: {tp} USDT (уровень сопротивления)\n"
                        f"⛔ **Stop Loss**: {sl} USDT (адаптивный ATR)\n"
                        f"📊 **ATR**: {round(last_atr, 2)}\n"
                        f"📊 **RSI**: {round(last_rsi, 2)}\n"
                        f"📊 **MACD**: {round(last_macd, 2)} / {round(last_signal_line, 2)}\n"
                        f"📊 **ADX**: {round(last_adx, 2)}"
                    )
                    await send_message_safe(bot, chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")
