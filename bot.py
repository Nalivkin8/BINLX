import asyncio
import json
import os
import pandas as pd
import websockets
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

# 🔹 Храним историю цен и активные сделки
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": [], "ETHUSDT": []}
active_trades = {}

# 🔹 Подключение к Binance WebSocket
async def start_futures_websocket():
    uri = "wss://fstream.binance.com/ws"
    print("🔄 Запуск WebSocket Binance Futures...")
    
    async with websockets.connect(uri) as ws:
        subscribe_message = json.dumps({
            "method": "SUBSCRIBE",
            "params": [
                "tstusdt@kline_1m", "ipusdt@kline_1m", "adausdt@kline_1m", "ethusdt@kline_1m"
            ],
            "id": 1
        })
        await ws.send(subscribe_message)
        print("✅ Подписка на Binance Futures (свечи)")

        async for message in ws:
            await process_futures_message(message)

# 🔹 Обрабатываем входящие данные WebSocket
async def process_futures_message(message):
    global price_history, active_trades
    try:
        data = json.loads(message)

        if 'k' in data:
            candle = data['k']
            symbol = data['s']
            close_price = float(candle['c'])

            print(f"📊 {symbol}: Закрытие свечи {close_price} USDT")

            if symbol in price_history:
                price_history[symbol].append(close_price)

                if len(price_history[symbol]) > 100:
                    price_history[symbol].pop(0)

                df = pd.DataFrame(price_history[symbol], columns=['close'])
                df['ATR'] = compute_atr(df)
                df['RSI'] = compute_rsi(df['close'])
                df['MACD'], df['Signal_Line'] = compute_macd(df['close'])
                df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
                df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
                df['ADX'] = compute_adx(df)
                df['Volume_MA'] = df['close'].rolling(window=20).mean()

                support, resistance = find_support_resistance(df)

                last_rsi = df['RSI'].iloc[-1]
                last_macd = df['MACD'].iloc[-1]
                last_signal_line = df['Signal_Line'].iloc[-1]
                last_atr = df['ATR'].iloc[-1]
                last_adx = df['ADX'].iloc[-1]

                # 📌 Фильтр слабых сигналов
                if last_atr < close_price * 0.0005 or last_adx < 20:
                    return  

                # 💡 Определяем новый сигнал
                signal = None
                if last_macd > last_signal_line and last_rsi < 50 and close_price > df['EMA_50'].iloc[-1]:
                    signal = "LONG"
                elif last_macd < last_signal_line and last_rsi > 50 and close_price < df['EMA_50'].iloc[-1]:
                    signal = "SHORT"

                # 📌 Проверка активной сделки
                if symbol in active_trades:
                    trade = active_trades[symbol]
                    if (trade["signal"] == "LONG" and close_price >= trade["tp"]) or \
                       (trade["signal"] == "SHORT" and close_price <= trade["tp"]):
                        await send_message_safe(f"✅ {symbol} достиг TP ({trade['tp']} USDT)!")
                        del active_trades[symbol]
                        return
                    if (trade["signal"] == "LONG" and close_price <= trade["sl"]) or \
                       (trade["signal"] == "SHORT" and close_price >= trade["sl"]):
                        await send_message_safe(f"❌ {symbol} достиг SL ({trade['sl']} USDT), закрываем сделку.")
                        del active_trades[symbol]
                        return
                    return  

                if signal:
                    tp, sl = compute_dynamic_tp_sl(close_price, signal, last_atr)
                    precision = get_price_precision(close_price)

                    active_trades[symbol] = {
                        "signal": signal,
                        "entry": close_price,
                        "tp": round(tp, precision),
                        "sl": round(sl, precision)
                    }

                    message = (
                        f"🔹 **{signal} {symbol} (Futures)**\n"
                        f"🔹 **Вход**: {close_price} USDT\n"
                        f"🎯 **TP**: {round(tp, precision)} USDT\n"
                        f"⛔ **SL**: {round(sl, precision)} USDT\n"
                        f"📊 RSI: {round(last_rsi, 2)}, MACD: {round(last_macd, 6)}, ATR: {last_atr}, ADX: {last_adx}"
                    )
                    await send_message_safe(message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Поддержка и сопротивление
def find_support_resistance(df):
    support = df['close'].rolling(window=50).min().iloc[-1]
    resistance = df['close'].rolling(window=50).max().iloc[-1]
    return support, resistance

# 🔹 Динамический TP и SL
def compute_dynamic_tp_sl(close_price, signal, atr):
    atr_multiplier = 3
    tp = close_price + atr_multiplier * atr if signal == "LONG" else close_price - atr_multiplier * atr
    sl = close_price - atr_multiplier * 0.7 * atr if signal == "LONG" else close_price + atr_multiplier * 0.7 * atr
    return tp, sl

# 🔹 Определение точности цены
def get_price_precision(price):
    price_str = f"{price:.10f}".rstrip('0')
    return len(price_str.split('.')[1]) if '.' in price_str else 0

# 🔹 Функции индикаторов
def compute_atr(df, period=14):
    df['tr'] = df['close'].diff().abs().fillna(0)
    return df['tr'].rolling(window=period).mean()

def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))

def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window, adjust=False).mean()
    long_ema = prices.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

def compute_adx(df, period=14):
    df['atr'] = df['close'].diff().abs().rolling(window=period).mean()
    df['adx'] = (df['atr'] / df['close']) * 100
    return df['adx']

async def main():
    print("🚀 Бот стартует...")
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
