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

                # TP достигнут → закрытие сделки
                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    await bot.send_message(chat_id, f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]

                # SL достигнут → закрытие сделки
                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
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

                    last_atr = df['ATR'].iloc[-1]
                    last_support = df['Support'].iloc[-1]
                    last_resistance = df['Resistance'].iloc[-1]
                    last_rsi = df['RSI'].iloc[-1]
                    last_macd = df['MACD'].iloc[-1]
                    last_signal_line = df['Signal_Line'].iloc[-1]
                    last_adx = df['ADX'].iloc[-1]

                    signal = None
                    if (last_rsi < 35 
                        and last_macd > last_signal_line 
                        and last_adx > 20 
                        and last_atr > 0.2):
                        signal = "LONG"

                    elif (last_rsi > 65 
                          and last_macd < last_signal_line 
                          and last_adx > 20 
                          and last_atr > 0.2):
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
                            f"📊 **ATR**: {round(last_atr, 2)}\n"
                            f"📊 **RSI**: {round(last_rsi, 2)}\n"
                            f"📊 **MACD**: {round(last_macd, 2)} / {round(last_signal_line, 2)}\n"
                            f"📊 **ADX**: {round(last_adx, 2)}"
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

# Функция расчета ADX
def compute_adx(df, period=14):
    high = df['close'].shift(1)
    low = df['close'].shift(-1)
    tr = abs(high - low)
    atr = tr.rolling(window=period).mean()
    adx = (atr / atr.max()) * 100
    return adx
