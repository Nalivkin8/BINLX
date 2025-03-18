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

# 🔹 Безопасная отправка сообщений в Telegram
async def send_message_safe(message):
    try:
        print(f"📤 Отправка сообщения в Telegram: {message}")
        await bot.send_message(TELEGRAM_CHAT_ID, message)
    except TelegramRetryAfter as e:
        print(f"⏳ Telegram ограничил отправку, ждем {e.retry_after} сек...")
        await asyncio.sleep(e.retry_after)
        await send_message_safe(message)
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")

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
                df['MACD'], df['Signal_Line'] = compute_macd(df['close'])
                df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
                df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
                df['ADX'] = compute_adx(df)

                last_macd = df['MACD'].iloc[-1]
                last_signal_line = df['Signal_Line'].iloc[-1]
                last_atr = df['ATR'].iloc[-1]
                last_adx = df['ADX'].iloc[-1]

                # 🛠 Фильтр слабых сигналов (если ATR NaN или слишком маленький)
                if pd.isna(last_atr) or last_atr < close_price * 0.0005:
                    print(f"🚫 {symbol}: ATR слишком мал или NaN, пропускаем сигнал")
                    return  

                # 💡 Определяем новый сигнал
                signal = None
                if last_macd > last_signal_line and close_price > df['EMA_50'].iloc[-1]:
                    signal = "LONG"
                elif last_macd < last_signal_line and close_price < df['EMA_50'].iloc[-1]:
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
                    roi = compute_roi(close_price, tp, sl)

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
                        f"💰 **ROI**: {roi:.2f}%"
                    )
                    await send_message_safe(message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Динамический TP и SL
def compute_dynamic_tp_sl(close_price, signal, atr):
    if pd.isna(atr) or atr == 0:
        return close_price, close_price  # Возвращаем цену входа, если ATR сломан
    atr_multiplier = 3
    tp = close_price + atr_multiplier * atr if signal == "LONG" else close_price - atr_multiplier * atr
    sl = close_price - atr_multiplier * 0.7 * atr if signal == "LONG" else close_price + atr_multiplier * 0.7 * atr
    return tp, sl

# 🔹 ROI расчет
def compute_roi(entry, tp, sl):
    if pd.isna(tp) or pd.isna(sl):
        return 0  # Если TP или SL NaN, ROI = 0
    tp_roi = ((tp - entry) / entry) * 100 if tp > entry else ((entry - tp) / entry) * 100
    sl_roi = ((sl - entry) / entry) * 100 if sl > entry else ((entry - sl) / entry) * 100
    return (tp_roi + sl_roi) / 2  

# 🔹 Фикс NaN в ATR
def compute_atr(df, period=14):
    df['tr'] = df['close'].diff().abs().fillna(0)
    return df['tr'].rolling(window=period).mean().fillna(0)

