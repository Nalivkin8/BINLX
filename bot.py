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

# 🔹 Храним активные сделки (по парам)
active_trades = {}
price_history = {
    "IPUSDT": [], "ADAUSDT": [], "ETHUSDT": [],
    "LTCUSDT": [], "ETCUSDT": []
}

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
        "params": [
            "ipusdt@trade", "adausdt@trade", "ethusdt@trade",
            "ltcusdt@trade", "etcusdt@trade"
        ],
        "id": 1
    })
    ws.send(subscribe_message)
    print("📩 Подписка на Binance Futures")

# 🔹 Определяем количество знаков после запятой
def get_decimal_places(price):
    price_str = f"{price:.10f}".rstrip('0')
    return len(price_str.split('.')[1]) if '.' in price_str else 0

# 🔹 Обрабатываем входящие данные WebSocket
async def process_futures_message(message):
    global active_trades, price_history
    try:
        data = json.loads(message)

        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            # 🔹 Фильтр ошибочных значений (0.0 USDT)
            if price <= 0.0:
                return

            print(f"📊 {symbol}: Текущая цена {price} USDT")

            # 📌 Проверка активных сделок на TP/SL
            if symbol in active_trades:
                trade = active_trades[symbol]

                # 🎯 Take Profit (TP)
                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    await send_message_safe(f"✅ **{symbol} достиг Take Profit ({trade['tp']} USDT)** 🎯")
                    del active_trades[symbol]
                    return  

                # ⛔ Stop Loss (SL)
                if (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    await send_message_safe(f"❌ **{symbol} достиг Stop Loss ({trade['sl']} USDT)** ⛔")
                    del active_trades[symbol]
                    return  

            # **Фильтр сигналов** – новый сигнал даётся только после TP/SL
            if symbol in active_trades:
                print(f"⚠️ Пропущен сигнал для {symbol} – активная сделка ещё не закрыта")
                return  

            # Обновление истории цен
            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 50:
                    price_history[symbol].pop(0)

                    df = pd.DataFrame(price_history[symbol], columns=['close'])

                    if len(df) < 14:
                        return  

                    df['RSI'] = compute_rsi(df['close'])
                    df['MACD'], df['Signal_Line'] = compute_macd(df['close'])
                    df['ATR'] = compute_atr(df['close'])

                    last_rsi = df['RSI'].iloc[-1]
                    last_macd = df['MACD'].iloc[-1]
                    last_signal_line = df['Signal_Line'].iloc[-1]
                    last_atr = df['ATR'].iloc[-1]

                    signal = None
                    if last_macd > last_signal_line and last_rsi < 50:
                        signal = "LONG"
                    elif last_macd < last_signal_line and last_rsi > 50:
                        signal = "SHORT"

                    if signal:
                        decimal_places = get_decimal_places(price)

                        # 🔹 Динамический TP и SL на основе ATR
                        tp, sl = compute_tp_sl(price, last_atr, signal, decimal_places)

                        roi_tp = round(((tp - price) / price) * 100, 2)
                        roi_sl = round(((sl - price) / price) * 100, 2)

                        active_trades[symbol] = {"signal": signal, "entry": price, "tp": tp, "sl": sl}

                        signal_emoji = "🟢" if signal == "LONG" else "🔴"

                        message = (
                            f"{signal_emoji} **{signal} {symbol} (Futures)**\n"
                            f"🔹 **Вход**: {price:.{decimal_places}f} USDT\n"
                            f"🎯 **TP**: {tp:.{decimal_places}f} USDT | ROI: {roi_tp}%\n"
                            f"⛔ **SL**: {sl:.{decimal_places}f} USDT | ROI: {roi_sl}%"
                        )
                        await send_message_safe(message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Функция безопасной отправки сообщений в Telegram
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

# 🔹 Динамический TP и SL на основе ATR
def compute_tp_sl(price, atr, signal, decimal_places):
    tp_multiplier = 3  
    sl_multiplier = 2  
    min_step = price * 0.005  

    tp = price + max(tp_multiplier * atr, min_step) if signal == "LONG" else price - max(tp_multiplier * atr, min_step)
    sl = price - max(sl_multiplier * atr, min_step) if signal == "LONG" else price + max(sl_multiplier * atr, min_step)

    return round(tp, decimal_places), round(sl, decimal_places)

# 🔹 Функция расчёта MACD
def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window, adjust=False).mean()
    long_ema = prices.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

async def main():
    print("🚀 Бот стартует...")
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
