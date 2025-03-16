import websocket
import json
import asyncio
import pandas as pd
import time
from aiogram.exceptions import TelegramRetryAfter

# Храним активные сделки
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}

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
        "params": ["tstusdt@trade", "ipusdt@trade", "adausdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
    print("✅ Подключено к WebSocket Binance Futures")

# Рассчитываем динамический SL
def calculate_dynamic_sl(entry_price, df, signal):
    last_atr = df["ATR"].iloc[-1]
    last_support = df["Support"].iloc[-1]
    last_resistance = df["Resistance"].iloc[-1]

    # ATR SL
    atr_sl = entry_price - last_atr * 1.5 if signal == "LONG" else entry_price + last_atr * 1.5

    # Проверяем уровни поддержки/сопротивления
    if signal == "LONG":
        sl = max(atr_sl, last_support)  # Используем ближайшую поддержку, если она выше ATR
    else:
        sl = min(atr_sl, last_resistance)  # Используем ближайшее сопротивление, если оно ниже ATR

    return round(sl, 6)

# Обрабатываем сообщения WebSocket
async def process_futures_message(bot, chat_id, message):
    global active_trades, price_history
    try:
        data = json.loads(message)
        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            # Проверяем TP/SL
            if symbol in active_trades:
                trade = active_trades[symbol]

                # TP достигнут
                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    print(f"🎯 {symbol} достиг Take Profit ({trade['tp']} USDT)")
                    await bot.send_message(chat_id, f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]

                # SL достигнут
                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    print(f"⛔ {symbol} достиг Stop Loss ({trade['sl']} USDT)")
                    await bot.send_message(chat_id, f"⛔ **{symbol} достиг Stop Loss ({trade['sl']} USDT)**")
                    del active_trades[symbol]

                return  

            # Обновление истории цен
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
                    if last_macd > last_signal_line and last_adx > 15 and last_atr > 0.1 and (last_rsi < 40 or (last_rsi < 50 and last_adx < 20)):
                        signal = "LONG"
                    elif last_macd < last_signal_line and last_adx > 15 and last_atr > 0.1 and (last_rsi > 60 or (last_rsi > 75 and last_adx < 20)):
                        signal = "SHORT"
    
                    if signal:
                        tp = round(last_resistance, 2) if signal == "LONG" else round(last_support, 2)
                        sl = calculate_dynamic_sl(price, df, signal)  # Теперь SL рассчитывается динамически

                        active_trades[symbol] = {"signal": signal, "entry": price, "tp": tp, "sl": sl}
                        
                        print(f"📢 Генерация сигнала: {signal} {symbol}, Цена входа: {price}")
                        
                        message = (
                            f"{'🟢' if signal == 'LONG' else '🔴'} **{signal} {symbol} (Futures)**\n"
                            f"🔹 **Вход**: {price} USDT\n"
                            f"🎯 **TP**: {tp} USDT | {round((tp/price - 1) * 100, 1)}%\n"
                            f"⛔ **SL**: {sl} USDT | {round((1 - sl/price) * 100, 1)}%"
                        )
                        await send_message_safe(bot, chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# Безопасная отправка сообщений в Telegram
async def send_message_safe(bot, chat_id, message):
    try:
        print(f"📤 Отправка сообщения: {message}")
        await bot.send_message(chat_id, message)
    except TelegramRetryAfter as e:
        print(f"⏳ Telegram ограничил отправку, ждем {e.retry_after} сек...")
        await asyncio.sleep(e.retry_after)
        await send_message_safe(bot, chat_id, message)
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")

# Функции индикаторов
def compute_atr(df, period=14):
    high = df['close'].shift(1)
    low = df['close'].shift(-1)
    tr = abs(high - low)
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1]  

def compute_support_resistance(df, period=50):
    support = df['close'].rolling(window=period).min()
    resistance = df['close'].rolling(window=period).max()
    return support, resistance

def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window, adjust=False).mean()
    long_ema = prices.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

def compute_adx(df, period=14):
    return df['close'].rolling(window=period).mean()
