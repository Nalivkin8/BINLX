import websocket
import json
import asyncio
import pandas as pd
import time
from aiogram.exceptions import TelegramRetryAfter

# Храним активные сделки и последние тренды
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

                    last_atr = df['ATR'].iloc[-1]
                    last_support = df['Support'].iloc[-1]
                    last_resistance = df['Resistance'].iloc[-1]
                    last_rsi = df['RSI'].iloc[-1]
                    last_macd = df['MACD'].iloc[-1]
                    last_signal_line = df['Signal_Line'].iloc[-1]

                    signal = None

                    # Логика для открытия позиций
                    if last_macd > last_signal_line and last_rsi < 50:
                        signal = "LONG"
                    elif last_macd < last_signal_line and last_rsi > 50:
                        signal = "SHORT"

                    if signal:
                        tp_multiplier = 2 + last_atr * 5  # TP без ограничения
                        sl_multiplier = 1 + last_atr * 2  # SL более гибкий

                        tp = round(price * (1 + tp_multiplier / 100), 6) if signal == "LONG" else round(price * (1 - tp_multiplier / 100), 6)
                        sl = round(price * (1 - sl_multiplier / 100), 6) if signal == "LONG" else round(price * (1 + sl_multiplier / 100), 6)

                        active_trades[symbol] = {"signal": signal, "entry": price, "tp": tp, "sl": sl}

                        message = (
                            f"📌 **Сигнал на {signal} {symbol} (Futures)**\n"
                            f"🔹 **Вход**: {price} USDT\n"
                            f"🎯 **TP**: {tp} USDT | {tp_multiplier:.1f}%\n"
                            f"⛔ **SL**: {sl} USDT | {sl_multiplier:.1f}%"
                        )
                        await send_message_safe(bot, chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# Безопасная отправка сообщений в Telegram
async def send_message_safe(bot, chat_id, message):
    try:
        await bot.send_message(chat_id, message)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await send_message_safe(bot, chat_id, message)
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")

# Функции индикаторов
def compute_atr(df, period=14):
    df['high'] = df['close'].rolling(window=period).max()
    df['low'] = df['close'].rolling(window=period).min()
    df['tr'] = df['high'] - df['low']
    df['ATR'] = df['tr'].rolling(window=period).mean()
    return df['ATR'].iloc[-1]

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
