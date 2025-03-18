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
active_trades = {}  # Храним открытые сигналы

# 🔹 Подключение к Binance WebSocket (асинхронно)
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
            close_price = float(candle['c'])  # Цена закрытия

            print(f"📊 {symbol}: Закрытие свечи {close_price} USDT")

            # Добавляем цену в историю
            if symbol in price_history:
                price_history[symbol].append(close_price)

                if len(price_history[symbol]) > 50:
                    price_history[symbol].pop(0)

                df = pd.DataFrame(price_history[symbol], columns=['close'])
                df['ATR'] = compute_atr(df)
                df['RSI'] = compute_rsi(df['close'])
                df['MACD'], df['Signal_Line'] = compute_macd(df['close'])

                last_rsi = df['RSI'].iloc[-1]
                last_macd = df['MACD'].iloc[-1]
                last_signal_line = df['Signal_Line'].iloc[-1]
                last_atr = df['ATR'].iloc[-1]

                # 💡 Определяем новый сигнал
                signal = None
                if last_macd > last_signal_line and last_rsi < 50:
                    signal = "LONG"
                elif last_macd < last_signal_line and last_rsi > 50:
                    signal = "SHORT"

                # 📌 Проверка: если уже есть активная сделка, новые сигналы не даём
                if symbol in active_trades:
                    trade = active_trades[symbol]

                    # Проверяем TP и SL
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
                    
                    # Если сделка активна, новые сигналы не отправляем
                    return  

                # 📢 Отправляем сигнал, если нет активных сделок
                if signal:
                    tp, sl = compute_dynamic_tp_sl(df, close_price, signal, last_atr)

                    active_trades[symbol] = {"signal": signal, "entry": close_price, "tp": tp, "sl": sl}

                    message = (
                        f"🔹 **{signal} {symbol} (Futures)**\n"
                        f"🔹 **Вход**: {close_price} USDT\n"
                        f"🎯 **TP**: {tp} USDT\n"
                        f"⛔ **SL**: {sl} USDT\n"
                        f"📊 RSI: {round(last_rsi, 2)}, MACD: {round(last_macd, 6)}, ATR: {round(last_atr, 6)}"
                    )
                    await send_message_safe(message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

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

# 🔹 Динамический расчет TP и SL
def compute_dynamic_tp_sl(df, close_price, signal, atr):
    atr_multiplier = 2  # Базовый множитель ATR
    if df['ATR'].mean() > 0.01:
        atr_multiplier = 3  # Если высокая волатильность, увеличиваем TP/SL

    tp = close_price + atr_multiplier * atr if signal == "LONG" else close_price - atr_multiplier * atr
    sl = close_price - atr_multiplier * 0.5 * atr if signal == "LONG" else close_price + atr_multiplier * 0.5 * atr

    return round(tp, 6), round(sl, 6)

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

# 🔹 Запуск WebSocket и бота
async def main():
    print("🚀 Бот стартует...")
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
