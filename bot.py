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

# 🔹 Храним активные сделки и статусы TP/SL
active_trades = {}  
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": [], "ETHUSDT": []}
trade_status = {}  # {"TSTUSDT": {"last_tp": 1.05, "last_sl": 0.95}}

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
            "tstusdt@trade", "ipusdt@trade", "adausdt@trade", "ethusdt@trade"
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
    global active_trades, price_history, trade_status
    try:
        data = json.loads(message)

        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            # 🔹 Фильтр ошибочных значений (0.0 USDT)
            if price <= 0.0:
                print(f"⚠️ Ошибка данных: {symbol} получил некорректную цену ({price} USDT), пропуск...")
                return

            print(f"📊 {symbol}: Текущая цена {price} USDT")

            # Проверяем TP/SL
            if symbol in active_trades:
                trade = active_trades[symbol]

                if symbol not in trade_status:
                    trade_status[symbol] = {"last_tp": None, "last_sl": None}

                # TP достигнут (и изменился)
                if price >= trade["tp"] and trade_status[symbol]["last_tp"] != trade["tp"]:
                    print(f"🎯 {symbol} достиг Take Profit ({trade['tp']} USDT)")
                    trade_status[symbol]["last_tp"] = trade["tp"]
                    await send_message_safe(f"🎯 **Take Profit {symbol} ({trade['tp']} USDT)**")
                    del active_trades[symbol]  # Убираем сделку
                    return

                # SL достигнут (и изменился)
                if price <= trade["sl"] and trade_status[symbol]["last_sl"] != trade["sl"]:
                    print(f"⛔ {symbol} достиг Stop Loss ({trade['sl']} USDT)")
                    trade_status[symbol]["last_sl"] = trade["sl"]
                    await send_message_safe(f"⛔ **Stop Loss {symbol} ({trade['sl']} USDT)**")
                    del active_trades[symbol]  # Убираем сделку
                    return

            # Если по паре уже есть сделка – новые сигналы не отправляем
            if symbol in active_trades:
                return

            # Обновление истории цен
            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 50:
                    price_history[symbol].pop(0)

                    df = pd.DataFrame(price_history[symbol], columns=['close'])
                    df['RSI'] = compute_rsi(df['close'])
                    df['MACD'], df['Signal_Line'] = compute_macd(df['close'])

                    last_rsi = df['RSI'].iloc[-1]
                    last_macd = df['MACD'].iloc[-1]
                    last_signal_line = df['Signal_Line'].iloc[-1]

                    signal = None
                    if last_macd > last_signal_line and last_rsi < 55:
                        signal = "LONG"
                    elif last_macd < last_signal_line and last_rsi > 45:
                        signal = "SHORT"

                    if signal:
                        await send_trade_signal(symbol, price, signal)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Отправка сигнала
async def send_trade_signal(symbol, price, trend):
    decimal_places = get_decimal_places(price)

    tp_percent = 0.02 if trend == "LONG" else -0.02  # TP от 2%
    sl_percent = 0.01 if trend == "LONG" else -0.01  # SL от 1%

    tp = round(price * (1 + tp_percent), decimal_places)
    sl = round(price * (1 - sl_percent), decimal_places)

    # 🔹 Расчёт ROI
    roi_tp = round(((tp - price) / price) * 100, 2) if trend == "LONG" else round(((price - tp) / price) * 100, 2)
    roi_sl = round(((sl - price) / price) * 100, 2) if trend == "LONG" else round(((price - sl) / price) * 100, 2)

    active_trades[symbol] = {"signal": trend, "entry": price, "tp": tp, "sl": sl}

    signal_emoji = "🟢" if trend == "LONG" else "🔴"

    message = (
        f"{signal_emoji} **{trend} {symbol} (Futures)**\n"
        f"🔹 **Вход**: {price:.{decimal_places}f} USDT\n"
        f"🎯 **TP**: {tp:.{decimal_places}f} USDT | ROI: {roi_tp}%\n"
        f"⛔ **SL**: {sl:.{decimal_places}f} USDT | ROI: {roi_sl}%"
    )
    await send_message_safe(message)

# 🔹 Функции индикаторов
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

# 🔹 Запуск WebSocket и бота
async def main():
    print("🚀 Бот стартует...")
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
