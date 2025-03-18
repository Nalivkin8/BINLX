import websocket
import json
import asyncio
import pandas as pd
import time
import os
import requests
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter

# Загружаем переменные среды из Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  
BINANCE_API_URL = "https://fapi.binance.com/fapi/v1/klines"  # Binance Futures API

if not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Ошибка: TELEGRAM_CHAT_ID не задан в Railway Variables!")

# Создаём бота и диспетчер
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Храним активные сделки
active_trades = {}  
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": []}

# 🔹 Логируем запуск WebSocket
async def start_futures_websocket():
    print("🔄 Запуск WebSocket...")
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(msg)),
        on_open=on_open  
    )
    print("⏳ Ожидание подключения к WebSocket...")
    await asyncio.to_thread(ws.run_forever)

# 🔹 Подписка на пары Binance
def on_open(ws):
    print("✅ Успешное подключение к WebSocket!")
    subscribe_message = json.dumps({
        "method": "SUBSCRIBE",
        "params": ["tstusdt@trade", "ipusdt@trade", "adausdt@trade"],
        "id": 1
    })
    ws.send(subscribe_message)
    print("📩 Отправлен запрос на подписку к Binance Futures")

# 🔹 Функция для запроса свечей с Binance API
def get_candles(symbol, interval, limit=100):
    url = f"{BINANCE_API_URL}?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Ошибка запроса свечей Binance API: {response.text}")
        return None

# 🔹 Анализ тренда на разных таймфреймах
def analyze_trend(symbol):
    timeframes = ["1m", "15m", "30m", "1h"]
    trend_scores = {"LONG": 0, "SHORT": 0}

    for tf in timeframes:
        candles = get_candles(symbol, tf)
        if not candles:
            continue

        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'trades', 'taker_base', 'taker_quote', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['ATR'] = compute_atr(df)
        df['RSI'] = compute_rsi(df['close'])
        df['MACD'], df['Signal_Line'] = compute_macd(df['close'])

        last_atr = df['ATR'].iloc[-1]
        last_rsi = df['RSI'].iloc[-1]
        last_macd = df['MACD'].iloc[-1]
        last_signal_line = df['Signal_Line'].iloc[-1]

        if last_macd > last_signal_line and last_rsi < 70:
            trend_scores["LONG"] += 1
        elif last_macd < last_signal_line and last_rsi > 30:
            trend_scores["SHORT"] += 1

    if trend_scores["LONG"] >= 3:
        return "LONG"
    elif trend_scores["SHORT"] >= 3:
        return "SHORT"
    else:
        return None  # Неопределённый тренд

# 🔹 Обрабатываем входящие сообщения WebSocket
async def process_futures_message(message):
    global active_trades, price_history
    try:
        data = json.loads(message)

        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])
            print(f"📊 Получено обновление цены {symbol}: {price} USDT")

            # Проверяем TP/SL
            if symbol in active_trades:
                trade = active_trades[symbol]

                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    print(f"🎯 {symbol} достиг Take Profit ({trade['tp']} USDT)")
                    await send_message_safe(f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]

                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    print(f"⛔ {symbol} достиг Stop Loss ({trade['sl']} USDT)")
                    await send_message_safe(f"⛔ **{symbol} достиг Stop Loss ({trade['sl']} USDT)**")
                    del active_trades[symbol]

                return  

            trend = analyze_trend(symbol)
            if not trend:
                return  # Если тренд не подтверждён, игнорируем сигнал

            # Генерация сигнала
            tp_percent = max(1, price * 0.05) / 100  
            sl_percent = min(0.5 + price * 0.02, 20) / 100  

            tp = round(price * (1 + tp_percent) if trend == "LONG" else price * (1 - tp_percent), 6)
            sl = round(price * (1 - sl_percent) if trend == "LONG" else price * (1 + sl_percent), 6)

            active_trades[symbol] = {"signal": trend, "entry": price, "tp": tp, "sl": sl}

            signal_emoji = "🟢" if trend == "LONG" else "🔴"

            message = (
                f"{signal_emoji} **{trend} {symbol} (Futures)**\n"
                f"🔹 **Вход**: {price} USDT\n"
                f"🎯 **TP**: {tp} USDT\n"
                f"⛔ **SL**: {sl} USDT"
            )
            await send_message_safe(message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Функции индикаторов (MACD, RSI, ATR)
def compute_atr(df, period=14):
    high = df['close'].rolling(window=period).max()
    low = df['close'].rolling(window=period).min()
    tr = high - low
    atr = tr.rolling(window=period).mean()
    return atr

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
