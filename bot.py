import websocket
import json
import asyncio
import os
import pandas as pd
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter

# 🔹 Загружаем переменные среды из Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Ошибка: TELEGRAM_CHAT_ID не задан в Railway Variables!")

# 🔹 Создаём бота и диспетчер
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# 🔹 Храним активные сделки и историю тренда
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": [], "ETHUSDT": []}
trend_history = {}  # Хранение последнего тренда {"TSTUSDT": "LONG"}

# 🔹 Запуск WebSocket
async def start_futures_websocket():
    print("🔄 Запуск WebSocket Binance Futures...")
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(msg)),
        on_open=on_open
    )
    print("⏳ Ожидание подключения к WebSocket...")
    await asyncio.to_thread(ws.run_forever)

# 🔹 Подписка на Binance Futures
def on_open(ws):
    print("✅ Успешное подключение к WebSocket!")
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["tstusdt@trade", "ipusdt@trade", "adausdt@trade", "ethusdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
    print("📩 Подписка на Binance Futures")

# 🔹 Обрабатываем WebSocket-сообщения
async def process_futures_message(message):
    global active_trades, price_history, trend_history
    try:
        data = json.loads(message)

        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            # 🔹 Фильтр ошибочных значений
            if price <= 0.0:
                print(f"⚠️ Ошибка данных: {symbol} получил некорректную цену ({price} USDT), пропуск...")
                return

            print(f"📊 {symbol}: Текущая цена {price} USDT")

            # Проверяем TP/SL
            if symbol in active_trades:
                trade = active_trades[symbol]

                if price >= trade["tp"] or price <= trade["sl"]:
                    status = "🎯 Take Profit" if price >= trade["tp"] else "⛔ Stop Loss"
                    print(f"{status} {symbol} ({price} USDT)")
                    await send_message_safe(f"{status} **{symbol} ({price} USDT)**")
                    del active_trades[symbol]
                    return

            # Обновление истории цен
            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 50:
                    price_history[symbol].pop(0)

                df = pd.DataFrame(price_history[symbol], columns=['close'])
                df['ATR'] = compute_atr(df)
                df['RSI'] = compute_rsi(df['close'])
                df['MACD'], df['Signal_Line'] = compute_macd(df['close'])
                df['ADX'] = compute_adx(df)

                last_rsi = df['RSI'].iloc[-1]
                last_macd = df['MACD'].iloc[-1]
                last_signal_line = df['Signal_Line'].iloc[-1]
                last_adx = df['ADX'].iloc[-1]

                # Фильтр тренда
                signal = None
                if last_macd > last_signal_line and last_rsi < 55 and last_adx > 20:
                    signal = "LONG"
                elif last_macd < last_signal_line and last_rsi > 45 and last_adx > 20:
                    signal = "SHORT"

                # Если произошла смена тренда, закрываем старую сделку и открываем новую
                if symbol in trend_history and trend_history[symbol] != signal:
                    if symbol in active_trades:
                        print(f"🔄 Закрываем старую сделку {symbol} из-за смены тренда")
                        del active_trades[symbol]  # Закрываем старую сделку

                trend_history[symbol] = signal  

                if symbol not in active_trades and signal:
                    await send_trade_signal(symbol, price, signal)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Отправка сигнала
async def send_trade_signal(symbol, price, trend):
    decimal_places = len(str(price).split(".")[-1])

    tp = round(price + (price * 0.02), decimal_places) if trend == "LONG" else round(price - (price * 0.02), decimal_places)
    sl = round(price - (price * 0.01), decimal_places) if trend == "LONG" else round(price + (price * 0.01), decimal_places)

    active_trades[symbol] = {"signal": trend, "entry": price, "tp": tp, "sl": sl}
    await send_message_safe(f"🟢 **{trend} {symbol}**\n🔹 Вход: {price} USDT\n🎯 TP: {tp} USDT\n⛔ SL: {sl} USDT")

# 🔹 Безопасная отправка сообщений
async def send_message_safe(message):
    try:
        print(f"📤 Отправка сообщения: {message}")
        await bot.send_message(TELEGRAM_CHAT_ID, message)
    except TelegramRetryAfter as e:
        print(f"⏳ Telegram ограничил отправку, ждем {e.retry_after} сек...")
        await asyncio.sleep(e.retry_after)
        await send_message_safe(message)
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")

# 🔹 Функции индикаторов
def compute_atr(df, period=14):
    return df['close'].diff().abs().rolling(window=period).mean()

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

# 🔹 Запуск WebSocket и бота
async def main():
    print("🚀 Бот стартует...")
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
