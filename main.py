import websocket
import json
import numpy as np
import matplotlib.pyplot as plt
import io
import os
from telegram import Bot

# 🔹 Загружаем API-ключи из Railway Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 🔹 Telegram-бот
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# 🔹 Торговые пары
TRADE_PAIRS = ["btcusdt", "ethusdt", "solusdt", "xrpusdt", "adausdt", "dotusdt", "maticusdt", "bnbusdt", "linkusdt"]

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

# 🔹 Функция рисует график RSI + цены и отправляет в Telegram
def send_chart(pair, prices, rsi):
    plt.figure(figsize=(10, 5))

    # 🔹 График цены
    plt.subplot(2, 1, 1)
    plt.plot(prices, label="Цена", color="blue")
    plt.title(f"{pair.upper()} Цена и RSI")
    plt.legend()

    # 🔹 График RSI
    plt.subplot(2, 1, 2)
    plt.plot(rsi, label="RSI", color="red")
    plt.axhline(30, color="green", linestyle="--")  # Линия перепроданности
    plt.axhline(70, color="red", linestyle="--")  # Линия перекупленности
    plt.legend()

    # 🔹 Сохраняем график и отправляем в Telegram
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format="png")
    img_buf.seek(0)
    bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=img_buf)
    plt.close()

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

        # 📈 Рассчитываем RSI и Stop-Loss/Take-Profit
        rsi = calculate_rsi(candle_data[pair])
        if rsi is not None:
            message = None
            stop_loss = round(price * 0.98, 4)  # -2% от текущей цены
            take_profit = round(price * 1.02, 4)  # +2% от текущей цены

            if rsi < 30:
                message = f"🚀 Лонг {pair.upper()}!\nЦена: {price}\nRSI: {rsi} (Перепроданность)\n🔹 SL: {stop_loss} | TP: {take_profit}"
            elif rsi > 70:
                message = f"⚠️ Шорт {pair.upper()}!\nЦена: {price}\nRSI: {rsi} (Перекупленность)\n🔹 SL: {stop_loss} | TP: {take_profit}"

            if message:
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                send_chart(pair, candle_data[pair], [calculate_rsi(candle_data[pair], i) for i in range(1, len(candle_data[pair]) + 1)])

# 🔹 Автоматический перезапуск WebSocket при разрыве
def connect_ws(pair):
    while True:
        try:
            ws = websocket.WebSocketApp(
                SOCKETS[pair],
                on_message=lambda ws, message: on_message(ws, message, pair),
                on_open=lambda ws: print(f"✅ Подключено к {pair.upper()} WebSocket"),
                on_error=lambda ws, error: print(f"⚠️ Ошибка WebSocket {pair.upper()}: {error}"),
                on_close=lambda ws, code, msg: print(f"❌ WebSocket закрыт {pair.upper()}, перезапуск..."),
            )
            ws.run_forever()
        except Exception as e:
            print(f"⚠️ Ошибка при подключении к {pair.upper()}, перезапуск через 5 секунд...")
            time.sleep(5)

# 🔹 Запуск WebSocket для всех пар
import threading
for pair in TRADE_PAIRS:
    thread = threading.Thread(target=connect_ws, args=(pair,))
    thread.start()

print("🚀 Бот запущен и отслеживает рынок через WebSocket!")
