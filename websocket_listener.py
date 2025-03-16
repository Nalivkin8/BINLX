import websocket
import json
import asyncio
import pandas as pd
import time
from aiogram.exceptions import TelegramRetryAfter

# Храним активные сделки
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}  # Добавлена ADA

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
        "params": ["tstusdt@trade", "ipusdt@trade", "adausdt@trade"],  # Добавлена ADAUSDT
        "id": 1
    })
    ws.send(subscribe_message)
    print("✅ Подключено к WebSocket Binance Futures")
    print("📩 Подписка на пары отправлена: TSTUSDT, IPUSDT, ADAUSDT")

# Обрабатываем сообщения WebSocket
async def process_futures_message(bot, chat_id, message):
    global active_trades, price_history
    try:
        data = json.loads(message)
        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            if symbol in active_trades:
                trade = active_trades[symbol]

                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    await bot.send_message(chat_id, f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]

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

                df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
                df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()

                trend = "Neutral"
                if df['EMA_50'].iloc[-1] > df['EMA_200'].iloc[-1]:
                    trend = "Bullish"
                elif df['EMA_50'].iloc[-1] < df['EMA_200'].iloc[-1]:
                    trend = "Bearish"

                last_atr = max(min(compute_atr(df), 0.5), 0.1)  # Ограничение ATR (0.1 - 0.5)
                last_support = df['Support'].iloc[-1]
                last_resistance = df['Resistance'].iloc[-1]
                last_rsi = df['RSI'].iloc[-1]
                last_macd = df['MACD'].iloc[-1]
                last_signal_line = df['Signal_Line'].iloc[-1]
                last_adx = df['ADX'].iloc[-1]

                signal = None
                if (
                    last_macd > last_signal_line
                    and last_macd - last_signal_line > 0.002  # Ослабили MACD фильтр
                    and last_adx > 6  # Ослабили ADX фильтр
                    and last_rsi >= 50  # Ослабили RSI фильтр
                    and trend == "Bullish"  
                    and price > df['EMA_50'].iloc[-1]  
                ):  
                    signal = "LONG"

                elif (
                    last_macd < last_signal_line
                    and last_signal_line - last_macd > 0.002  
                    and last_adx > 6  
                    and last_rsi <= 50  
                    and trend == "Bearish"
                    and price < df['EMA_50'].iloc[-1]  
                ):  
                    signal = "SHORT"

                if signal:
                    tp_multiplier = 2.0 if last_atr > 0.3 else 1.3  
                    sl_multiplier = 1.5 if last_atr > 0.3 else 1.0  

                    tp = round(price + (last_atr * tp_multiplier), 4) if signal == "LONG" else round(price - (last_atr * tp_multiplier), 4)
                    sl = round(price - (last_atr * sl_multiplier), 4) if signal == "LONG" else round(price + (last_atr * sl_multiplier), 4)

                    active_trades[symbol] = {"signal": signal, "entry": price, "tp": tp, "sl": sl}

                    message = (
                        f"📌 **Скальпинг-сигнал на {signal} {symbol} (Futures)**\n"
                        f"🔹 **Цена входа**: {price} USDT\n"
                        f"🎯 **Take Profit**: {tp} USDT (ATR x {tp_multiplier})\n"
                        f"⛔ **Stop Loss**: {sl} USDT (ATR x {sl_multiplier})\n"
                        f"📊 **ATR**: {round(last_atr, 4)}\n"
                        f"📊 **ADX**: {round(last_adx, 2)}\n"
                        f"📊 **RSI**: {round(last_rsi, 2)}\n"
                        f"📊 **MACD**: {round(last_macd, 4)} / {round(last_signal_line, 4)}"
                    )
                    await bot.send_message(chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# **Функции индикаторов**
def compute_atr(df, period=14):
    tr = abs(df['close'].diff())
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1]

def compute_support_resistance(df, period=50):
    support = df['close'].rolling(window=period).min()
    resistance = df['close'].rolling(window=period).max()
    return support, resistance

def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    macd = prices.ewm(span=short_window).mean() - prices.ewm(span=long_window).mean()
    signal_line = macd.ewm(span=signal_window).mean()
    return macd.iloc[-1], signal_line.iloc[-1]

def compute_adx(df, period=14):
    return (df['ATR'] / df['ATR'].max()) * 100
