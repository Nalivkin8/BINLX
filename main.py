import websocket
import json
import numpy as np
import matplotlib.pyplot as plt
import io
import os
import schedule
import time
from telegram import Bot
import ccxt  # Используем для получения баланса Binance

# 🔹 Загружаем API-ключи из Railway Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# 🔹 Подключение к Binance
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET_KEY,
    'options': {'defaultType': 'future'}
})

# 🔹 Telegram-бот
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# 🔹 Торговые пары
TRADE_PAIRS = ["btcusdt", "ethusdt", "solusdt", "xrpusdt", "adausdt", "dotusdt", "maticusdt", "bnbusdt", "linkusdt", "ipusdt", "tstusdt"]

# 🔹 Данные для анализа
candle_data = {pair: [] for pair in TRADE_PAIRS}
candle_volumes = {pair: [] for pair in TRADE_PAIRS}

# 🔹 Binance WebSocket URL
SOCKETS = {pair: f"wss://fstream.binance.com/ws/{pair}@kline_15m" for pair in TRADE_PAIRS}

# 🔹 Счётчик сделок и прибыли/убытков
daily_trades = 0
total_profit_loss = 0

# 🔹 Функции расчёта индикаторов
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

def calculate_sma(prices, period=50):
    if len(prices) < period:
        return None
    return np.mean(prices[-period:])

def calculate_macd(prices, short_window=12, long_window=26, signal_window=9):
    if len(prices) < long_window:
        return None, None
    short_ema = np.mean(prices[-short_window:])
    long_ema = np.mean(prices[-long_window:])
    macd_line = short_ema - long_ema
    signal_line = np.mean([macd_line for _ in range(signal_window)])
    return macd_line, signal_line

def calculate_bollinger_bands(prices, period=20):
    if len(prices) < period:
        return None, None
    sma = np.mean(prices[-period:])
    std_dev = np.std(prices[-period:])
    upper_band = sma + (2 * std_dev)
    lower_band = sma - (2 * std_dev)
    return round(lower_band, 4), round(upper_band, 4)

def check_volume(pair):
    if len(candle_volumes[pair]) < 10:
        return False
    avg_volume = np.mean(candle_volumes[pair][-10:])
    last_volume = candle_volumes[pair][-1]
    return last_volume > avg_volume * 1.5

# 🔹 Получение баланса аккаунта
def get_balance():
    balance_info = exchange.fetch_balance()
    balance = balance_info['total']['USDT'] if 'USDT' in balance_info['total'] else 0
    return round(balance, 2)

# 🔹 Получение информации по открытым позициям
def get_open_positions():
    positions = exchange.fetch_positions()
    open_positions = [p for p in positions if float(p['contracts']) > 0]
    
    if not open_positions:
        return "🔹 Нет открытых позиций"
    
    report = "📌 Открытые позиции:\n"
    for pos in open_positions:
        report += f"🔹 {pos['symbol']}: {pos['side']} {pos['contracts']} контрактов, PnL: {round(float(pos['unrealizedPnl']), 2)} USDT\n"
    
    return report

# 🔹 График RSI + цены в Telegram
def send_chart(pair, prices, rsi):
    plt.figure(figsize=(10, 5))

    plt.subplot(2, 1, 1)
    plt.plot(prices, label="Цена", color="blue")
    plt.title(f"{pair.upper()} Цена и RSI")
    plt.legend()

    plt.subplot(2, 1, 2)
    plt.plot(rsi, label="RSI", color="red")
    plt.axhline(30, color="green", linestyle="--")
    plt.axhline(70, color="red", linestyle="--")
    plt.legend()

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format="png")
    img_buf.seek(0)
    bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=img_buf)
    plt.close()

# 🔹 Дневной отчёт в Telegram
def daily_report():
    balance = get_balance()
    open_positions = get_open_positions()
    
    report = f"📊 Дневной отчёт\n🔹 Баланс: {balance} USDT\n🔹 Сделок за сутки: {daily_trades}\n🔹 Общий P/L: {round(total_profit_loss, 2)} USDT\n\n{open_positions}"
    
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=report)

schedule.every().day.at("00:00").do(daily_report)

# 🔹 Обработка данных WebSocket
def on_message(ws, message, pair):
    global daily_trades, total_profit_loss
    data = json.loads(message)
    candle = data['k']
    price = float(candle['c'])  
    volume = float(candle['v'])
    is_closed = candle['x']

    if is_closed:
        candle_data[pair].append(price)
        candle_volumes[pair].append(volume)

        if len(candle_data[pair]) > 50:
            candle_data[pair].pop(0)
            candle_volumes[pair].pop(0)

        rsi = calculate_rsi(candle_data[pair])
        sma_50 = calculate_sma(candle_data[pair])
        macd, signal = calculate_macd(candle_data[pair])
        bb_lower, bb_upper = calculate_bollinger_bands(candle_data[pair])

        stop_loss = round(price * 0.98, 4)
        take_profit = round(price * 1.02, 4)

        if rsi and macd and bb_lower and bb_upper and check_volume(pair):
            if rsi < 30 and price < bb_lower and macd > signal and price > sma_50:
                daily_trades += 1
                total_profit_loss += take_profit - price
                message = f"🚀 Лонг {pair.upper()}! Цена: {price}\nRSI: {rsi}\n🔹 SL: {stop_loss} | TP: {take_profit}"
            elif rsi > 70 and price > bb_upper and macd < signal and price < sma_50:
                daily_trades += 1
                total_profit_loss += price - stop_loss
                message = f"⚠️ Шорт {pair.upper()}! Цена: {price}\nRSI: {rsi}\n🔹 SL: {stop_loss} | TP: {take_profit}"

            if message:
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                send_chart(pair, candle_data[pair], [calculate_rsi(candle_data[pair], i) for i in range(1, len(candle_data[pair]) + 1)])

# 🔹 Запуск WebSocket
for pair in TRADE_PAIRS:
    ws = websocket.WebSocketApp(SOCKETS[pair], on_message=lambda ws, msg: on_message(ws, msg, pair))
    ws.run_forever()
