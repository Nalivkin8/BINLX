import ccxt
import time
import os
import pandas as pd
from telegram import Bot
from dotenv import load_dotenv

print("🚀 Запуск бота...")

# 🔹 Загружаем API-ключи из .env (если используем локально)
load_dotenv()

# Получаем API-ключи из переменных Railway
# Загружаем API-ключи из Railway
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")  # ✅ Добавили эту строку
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
    raise Exception("❌ Ошибка: API-ключи Binance не загружены! Проверь переменные в Railway.")

print("✅ API-ключи загружены!")

# Торговые пары (фьючерсы)
TRADE_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]

# Подключение к Binance Futures API (используем альтернативный сервер)
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',  # Используем реальные фьючерсы
        'adjustForTimeDifference': True
    },
    'urls': {
        'api': 'https://fapi.binance.com'  # ✅ Основной API Binance Futures
    }
})



print("📡 Подключение к Binance...")

# Получение данных рынка
def get_market_data(symbol, timeframe="15m"):
    try:
        print(f"📊 Получаю данные для {symbol}...")
        candles = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = df['close'].astype(float)
        return df
    except Exception as e:
        print(f"⚠️ Ошибка при получении данных для {symbol}: {str(e)}")
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

# Функция отправки сигнала в Telegram
def send_signal(message):
    try:
        print(f"📩 Отправляю сообщение в Telegram: {message}")
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"⚠️ Ошибка при отправке сообщения в Telegram: {str(e)}")

# Основной цикл мониторинга рынка
def monitor_market():
    print("🚀 Запуск мониторинга рынка...")
    while True:
        for pair in TRADE_PAIRS:
            df = get_market_data(pair)
            if df is None:
                continue

            rsi = calculate_rsi(df)
            if rsi is None:
                continue

            last_price = df['close'].iloc[-1]
            message = f"RSI {pair}: {rsi} | Цена: {last_price}"

            print(f"📊 {message}")

            if rsi < 30:
                send_signal(f"🚀 Лонг на {pair}!\nЦена: {last_price}\nRSI: {rsi} (Перепроданность!)")
            elif rsi > 70:
                send_signal(f"⚠️ Шорт на {pair}!\nЦена: {last_price}\nRSI: {rsi} (Перекупленность!)")

        print("⏳ Жду 60 секунд перед следующим анализом...")
        time.sleep(60)

# Запуск мониторинга
monitor_market()
