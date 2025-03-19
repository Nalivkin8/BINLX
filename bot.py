import websocket
import json
import asyncio
import os
import pandas as pd
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter

# 🔹 Загружаем переменные среды
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Ошибка: TELEGRAM_CHAT_ID не задан в Railway Variables!")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# 🔹 Активные сделки
active_trades = {}
price_history = {"IPUSDT": [], "ADAUSDT": [], "ETHUSDT": [], "LTCUSDT": [], "ETCUSDT": []}

# 🔹 Минимальный процент для TP и SL (чтобы не было копеечных значений)
MIN_TP_SL_PERCENT = 0.005  # 0.5%

# 🔹 Функции индикаторов
def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss.replace(0, 1e-9)  
    return 100 - (100 / (1 + rs))

def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window, adjust=False).mean()
    long_ema = prices.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

def compute_atr(prices, period=14):
    tr = prices.diff().abs()
    atr = tr.rolling(window=period).mean()
    return atr

def compute_tp_sl(price, atr, signal, decimal_places):
    if pd.isna(atr) or atr == 0:  
        atr = price * 0.002  # Если ATR `nan` или 0, ставим минимальное значение (0.2% от цены)
    
    tp_multiplier = 5  
    sl_multiplier = 3  
    min_tp_sl = price * MIN_TP_SL_PERCENT  

    tp = price + max(tp_multiplier * atr, min_tp_sl) if signal == "LONG" else price - max(tp_multiplier * atr, min_tp_sl)
    sl = price - max(sl_multiplier * atr, min_tp_sl) if signal == "LONG" else price + max(sl_multiplier * atr, min_tp_sl)

    return round(tp, decimal_places), round(sl, decimal_places)

async def send_message_safe(message):
    try:
        print(f"📤 Отправка в Telegram: {message}")
        await bot.send_message(TELEGRAM_CHAT_ID, message)
    except TelegramRetryAfter as e:
        print(f"⏳ Telegram ограничил отправку, ждем {e.retry_after} сек...")
        await asyncio.sleep(e.retry_after)
        await send_message_safe(message)
    except Exception as e:
        print(f"❌ Ошибка Telegram: {e}")

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

def get_decimal_places(price):
    price_str = f"{price:.10f}".rstrip('0')
    return len(price_str.split('.')[1]) if '.' in price_str else 0

async def process_futures_message(message):
    global active_trades, price_history
    try:
        data = json.loads(message)

        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            if price <= 0.0:
                return

            print(f"📊 {symbol}: Текущая цена {price} USDT")

            if symbol in active_trades:
                trade = active_trades[symbol]
                tp_price = trade["tp"]
                sl_price = trade["sl"]

                # ✅ Фиксация TP/SL даже если цена их перепрыгнула
                if (trade["signal"] == "LONG" and price >= tp_price) or (trade["signal"] == "SHORT" and price <= tp_price):
                    del active_trades[symbol]
                    await send_message_safe(f"✅ **{format_symbol(symbol)} достиг Take Profit ({tp_price} USDT)** 🎯")
                    return  

                if (trade["signal"] == "LONG" and price <= sl_price) or (trade["signal"] == "SHORT" and price >= sl_price):
                    del active_trades[symbol]
                    await send_message_safe(f"❌ **{format_symbol(symbol)} достиг Stop Loss ({sl_price} USDT)** ⛔")
                    return  

                print(f"⚠️ Пропущен сигнал для {symbol} – активная сделка еще не закрыта")
                return  

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
                    tp, sl = compute_tp_sl(price, last_atr, signal, decimal_places)

                    active_trades[symbol] = {"signal": signal, "entry": price, "tp": tp, "sl": sl}

                    signal_emoji = "🟢" if signal == "LONG" else "🔴"
                    message = (
                        f"{signal_emoji} **{signal} {format_symbol(symbol)}**\n"
                        f"🔹 **Вход**: {price:.{decimal_places}f} USDT\n"
                        f"🎯 **TP**: {tp:.{decimal_places}f} USDT\n"
                        f"⛔ **SL**: {sl:.{decimal_places}f} USDT"
                    )
                    await send_message_safe(message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

def format_symbol(symbol):
    return symbol.replace("USDT", "/USDT")

async def main():
    print("🚀 Бот стартует...")
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
