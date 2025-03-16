import websocket
import json
import asyncio
import pandas as pd
import time
from aiogram.exceptions import TelegramRetryAfter

# Храним активные сделки
active_trades = {}  # {"TSTUSDT": {"signal": "LONG", "entry": 5.50, "tp": 6.05, "sl": 5.23, "trailing_sl": 5.40}}
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

# Обрабатываем сообщения WebSocket
async def process_futures_message(bot, chat_id, message):
    global active_trades, price_history
    try:
        data = json.loads(message)

        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            # Проверяем активные сделки
            if symbol in active_trades:
                trade = active_trades[symbol]

                # Если цена достигла TP → фиксация прибыли
                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    await bot.send_message(chat_id, f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]

                # Если цена достигла SL → фиксация убытка
                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    await bot.send_message(chat_id, f"⛔ **{symbol} достиг Stop Loss ({trade['sl']} USDT)**")
                    del active_trades[symbol]

                # **Скользящий Stop Loss (Trailing SL), учитывая ATR**
                atr = compute_atr(price_history[symbol])

                if trade["signal"] == "LONG" and price > trade["entry"] * (1 + atr / 100):
                    new_sl = round(price - atr * 0.5, 2)  # Подтягиваем SL на половину ATR
                    if new_sl > trade["sl"]:  
                        trade["sl"] = new_sl
                        await bot.send_message(chat_id, f"🔄 **Trailing Stop Loss обновлен для {symbol}: {new_sl} USDT**")

                elif trade["signal"] == "SHORT" and price < trade["entry"] * (1 - atr / 100):
                    new_sl = round(price + atr * 0.5, 2)  
                    if new_sl < trade["sl"]:  
                        trade["sl"] = new_sl
                        await bot.send_message(chat_id, f"🔄 **Trailing Stop Loss обновлен для {symbol}: {new_sl} USDT**")

                return  

            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 200:
                    price_history[symbol].pop(0)

                    df = pd.DataFrame(price_history[symbol], columns=['close'])
                    df['ATR'] = compute_atr(df)
                    df['Support'], df['Resistance'] = compute_support_resistance(df)

                    last_atr = df['ATR'].iloc[-1]
                    last_support = df['Support'].iloc[-1]
                    last_resistance = df['Resistance'].iloc[-1]

                    signal = None
                    if price < last_support and last_atr > 0.5:
                        signal = "LONG"
                    elif price > last_resistance and last_atr > 0.5:
                        signal = "SHORT"

                    if signal:
                        tp = round(last_resistance, 2) if signal == "LONG" else round(last_support, 2)
                        sl = round(price - last_atr, 2) if signal == "LONG" else round(price + last_atr, 2)

                        active_trades[symbol] = {"signal": signal, "entry": price, "tp": tp, "sl": sl}

                        message = (
                            f"📌 **Сигнал на {signal} {symbol} (Futures)**\n"
                            f"🔹 **Цена входа**: {price} USDT\n"
                            f"🎯 **Take Profit**: {tp} USDT (уровень сопротивления)\n"
                            f"⛔ **Stop Loss**: {sl} USDT (адаптивный ATR)\n"
                            f"📊 **ATR**: {round(last_atr, 2)}"
                        )
                        await bot.send_message(chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# Функция расчета ATR
def compute_atr(df, period=14):
    high = df['close'].shift(1)
    low = df['close'].shift(-1)
    tr = abs(high - low)
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1]  

# Функция определения уровней поддержки и сопротивления
def compute_support_resistance(df, period=50):
    support = df['close'].rolling(window=period).min()
    resistance = df['close'].rolling(window=period).max()
    return support, resistance
