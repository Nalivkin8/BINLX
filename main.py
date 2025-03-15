import websocket
import json
import numpy as np
from telegram import Bot
import os

# 🔹 Загружаем API-ключи из Railway Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 🔹 Telegram-бот
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# 🔹 Торговые пары
TRADE_PAIRS = ["btcusdt", "ethusdt", "solusdt", "xrpusdt"]

# 🔹 Данные для RSI (история свечей)
candle_data = {pair: [] for pair in TRADE_PAIRS}

# 🔹 Binance WebSocket URL
SOCKETS = {pair: f"wss://fstream.binance.com/ws/{pair}@kline_15m" for pair in TRADE_PAIRS}

# 🔹 Функция расчёта RSI
def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return None
    delta = np.diff(prices)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])
    rs = avg_gain / avg_loss if avg_loss != 0 else 0
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

# 🔹 Функция обработки данных WebSocket
def on_message(ws, message, pair):
    data = json.loads(message)
    candle = data['k']
    price = float(candle['c'])  # Цена закрытия
    is_closed = candle['x']  # True, если свеча закрылась

    if is_closed:
        candle_data[pair].append(price)
        if len(candle_data[pair]) > 50:
            candle_data[pair].pop(0)  # Удаляем старую свечу

        # Рассчитываем RSI и отправляем сигнал в Telegram
        rsi = calculate_rsi(candle_data[pair])
        if rsi is not None:
            message = None
            if rsi < 30:
                message = f"🚀 Лонг {pair.upper()}!\nЦена: {price}\nRSI: {rsi} (Перепроданность)"
            elif rsi > 70:
                message = f"⚠️ Шорт {pair.upper()}!\nЦена: {price}\nRSI: {rsi} (Перекупленность)"

            if message:
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# 🔹 Подключаем WebSocket для каждой торговой пары
def connect_ws(pair):
    def on_message_wrapper(ws, message):
        on_message(ws, message, pair)

    ws = websocket.WebSocketApp(
        SOCKETS[pair],
        on_message=on_message_wrapper,
        on_open=lambda ws: print(f"✅ Подключено к {pair.upper()} WebSocket"),
        on_error=lambda ws, error: print(f"⚠️ Ошибка WebSocket {pair.upper()}: {error}"),
        on_close=lambda ws, code, msg: print(f"❌ WebSocket закрыт {pair.upper()}")
    )
    ws.run_forever()

# 🔹 Запуск WebSocket для всех пар
import threading
for pair in TRADE_PAIRS:
    thread = threading.Thread(target=connect_ws, args=(pair,))
    thread.start()

print("🚀 Бот запущен и отслеживает рынок через WebSocket!")
