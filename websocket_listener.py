import time
import json
import websocket
import asyncio
import pandas as pd
from aiogram.exceptions import TelegramRetryAfter

# Храним активные сделки и Stop Loss
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}  
reached_sl = {}  
latest_prices = {}

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

async def process_futures_message(bot, chat_id, message):
    global active_trades, price_history, reached_sl, latest_prices
    try:
        data = json.loads(message)
        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            if price <= 0:
                return  

            latest_prices[symbol] = price  

            # Проверяем активные сделки
            if symbol in active_trades:
                trade = active_trades[symbol]

                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    await bot.send_message(chat_id, f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT | +{trade['tp_percent']}%)**")
                    del active_trades[symbol]
                    reached_sl[symbol] = False  

                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    if not reached_sl.get(symbol, False):  
                        await bot.send_message(chat_id, f"⛔ **{symbol} достиг Stop Loss ({trade['sl']} USDT | -{trade['sl_percent']}%)**")
                        reached_sl[symbol] = True  
                    del active_trades[symbol]

                return  

            # Обновляем историю цены
            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 200:
                    price_history[symbol].pop(0)

                df = pd.DataFrame(price_history[symbol], columns=['close'])
                df['ATR'] = compute_atr(df)

                last_atr = compute_atr(df)  

                # Определение сигнала
                signal = None
                if price > df['close'].rolling(10).mean().iloc[-1]:
                    signal = "LONG"
                elif price < df['close'].rolling(10).mean().iloc[-1]:
                    signal = "SHORT"

                if signal:
                    # **Динамический % TP и SL по ATR**
                    tp_percentage = round(10 + (last_atr * 20), 1)  # Может быть 10-20%
                    sl_percentage = round(5 + (last_atr * 10), 1)  # Может быть 5-10%

                    tp = round(price * (1 + tp_percentage / 100), 6) if signal == "LONG" else round(price * (1 - tp_percentage / 100), 6)
                    sl = round(price * (1 - sl_percentage / 100), 6) if signal == "LONG" else round(price * (1 + sl_percentage / 100), 6)

                    if tp <= 0 or sl <= 0:
                        return

                    active_trades[symbol] = {
                        "signal": signal, "entry": price, 
                        "tp": tp, "sl": sl, 
                        "tp_percent": tp_percentage, 
                        "sl_percent": sl_percentage
                    }
                    reached_sl[symbol] = False  

                    message = (
                        f"📌 **Сигнал на {signal} {symbol} (Futures)**\n"
                        f"🔹 **Вход**: {price} USDT\n"
                        f"🎯 **TP**: {tp} USDT | +{tp_percentage}%\n"
                        f"⛔ **SL**: {sl} USDT | -{sl_percentage}%"
                    )
                    await bot.send_message(chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# Функция расчёта ATR
def compute_atr(df, period=14):
    df['high'] = df['close'].shift(1)
    df['low'] = df['close'].shift(-1)
    df['tr'] = abs(df['high'] - df['low'])
    df['ATR'] = df['tr'].rolling(window=period).mean()
    return df['ATR'].iloc[-1] if not df['ATR'].empty else 0.2  
