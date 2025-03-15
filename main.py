import ccxt
import time
import os
import pandas as pd
from telegram import Bot

# 🔹 Переменные (получаем из Railway)
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Торговые пары
TRADE_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]

# Проверяем, есть ли API-ключ
if not BINANCE_API_KEY:
    raise Exception("❌ Binance API-ключ отсутствует! Проверь API в Railway Variables.")

# Подключение к Binance Futures API
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',  # Переключаем на фьючерсы
        'adjustForTimeDifference': True
    },
    'urls': {
        'api': {
            'public': 'https://fapi.binance.com',  # Binance Futures API (фьючерсы)
            'private': 'https://fapi.binance.com'
        }
    }
})

# Получение данных рынка
def get_market_data(symbol, timeframe="15m"):
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = df['close'].astype(float)
        return df
    except Exception as e:
        print(f"Ошибка при получении данных для {symbol}: {str(e)}")
        return None

# Расчет RSI
def calculate_rsi(df, period=14):
    if df is None:
        return None
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 2)

# Функция отправки сигнала
def send_signal(message):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"Ошибка при отправке сообщения в Telegram: {str(e)}")

# Основной цикл
def monitor_market():
    while True:
        for pair in TRADE_PAIRS:
            df = get_market_data(pair)
            if df is None:
                continue  # Пропускаем, если данных нет

            rsi = calculate_rsi(df)
            if rsi is None:
                continue

            last_price = df['close'].iloc[-1]
            message = ""

            if rsi < 30:
                message = f"🚀 Лонг на {pair}!\nЦена: {last_price}\nRSI: {rsi} (Перепроданность!)"
            elif rsi > 70:
                message = f"⚠️ Шорт на {pair}!\nЦена: {last_price}\nRSI: {rsi} (Перекупленность!)"

            if message:
                send_signal(message)

        time.sleep(60)  # Обновление каждую минуту

# Запуск мониторинга
monitor_market()
