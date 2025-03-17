import websocket
import json
import asyncio
import pandas as pd
import time
import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.exceptions import TelegramRetryAfter
from balance_checker import get_balance, get_open_positions  # Импортируем баланс

# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Запуск бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# Храним активные сделки
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}

# Команда /balance
@dp.message_handler(commands=["balance"])
async def balance_command(message: types.Message):
    balance = get_balance()
    positions = get_open_positions()
    await message.answer(f"{balance}\n\n{positions}")

# Подключение к WebSocket Binance Futures
async def start_futures_websocket():
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(msg)),
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
async def process_futures_message(message):
    global active_trades, price_history
    try:
        data = json.loads(message)
        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            # Проверяем TP/SL
            if symbol in active_trades:
                trade = active_trades[symbol]

                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    print(f"🎯 {symbol} достиг Take Profit ({trade['tp']} USDT)")
                    await bot.send_message(chat_id, f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]

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
                    df['RSI'] = compute_rsi(df['close'])
                    df['MACD'], df['Signal_Line'] = compute_macd(df['close'])
                    df['ADX'] = compute_adx(df)

                    last_atr = df['ATR'].iloc[-1]
                    last_rsi = df['RSI'].iloc[-1]
                    last_macd = df['MACD'].iloc[-1]
                    last_signal_line = df['Signal_Line'].iloc[-1]
                    last_adx = df['ADX'].iloc[-1]

                    signal = None
                    if last_macd > last_signal_line and last_atr > 0.05 and (last_rsi < 50 or last_adx < 15):
                        signal = "LONG"
                    elif last_macd < last_signal_line and last_atr > 0.05 and (last_rsi > 55 or last_adx < 15):
                        signal = "SHORT"

                    if signal:
                        tp_percent = max(3, min(15, last_atr * 100)) / 100
                        sl_percent = max(1, min(7, last_atr * 50)) / 100

                        tp = round(price * (1 + tp_percent) if signal == "LONG" else price * (1 - tp_percent), 6)
                        sl = round(price * (1 - sl_percent) if signal == "LONG" else price * (1 + sl_percent), 6)

                        active_trades[symbol] = {"signal": signal, "entry": price, "tp": tp, "sl": sl}

                        print(f"📢 Генерация сигнала: {signal} {symbol}, Цена входа: {price}")
                        
                        message = (
                            f"{'🟢' if signal == 'LONG' else '🔴'} **{signal} {symbol} (Futures)**\n"
                            f"🔹 **Вход**: {price} USDT\n"
                            f"🎯 **TP**: {tp} USDT | {round(tp_percent * 100, 1)}%\n"
                            f"⛔ **SL**: {sl} USDT | {round(sl_percent * 100, 1)}%"
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

# Запускаем бота и WebSocket
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_futures_websocket())
    executor.start_polling(dp, skip_updates=True)
