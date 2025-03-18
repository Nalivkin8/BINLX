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

# 🔹 Храним активные сделки и тренды
active_trades = {}
price_history = {"TSTUSDT": [], "IPUSDT": [], "ADAUSDT": [], "ETHUSDT": []}
trend_history = {}

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

# 🔹 Обрабатываем WebSocket-сообщения
async def process_futures_message(message):
    global active_trades, price_history, trend_history
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

                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    print(f"🎯 {symbol} достиг Take Profit ({trade['tp']} USDT)")
                    await send_message_safe(f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]
                    return

                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    print(f"⛔ {symbol} достиг Stop Loss ({trade['sl']} USDT)")
                    await send_message_safe(f"⛔ **{symbol} достиг Stop Loss ({trade['sl']} USDT)**")
                    del active_trades[symbol]
                    return

            # Обновление истории цен
            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 50:
                    price_history[symbol].pop(0)

                    df = pd.DataFrame(price_history[symbol], columns=['close'])
                    df['RSI'] = compute_rsi(df['close'])
                    df['MACD'], df['Signal_Line'] = compute_macd(df['close'])
                    df['ADX'] = compute_adx(df)

                    last_rsi = df['RSI'].iloc[-1]
                    last_macd = df['MACD'].iloc[-1]
                    last_signal_line = df['Signal_Line'].iloc[-1]
                    last_adx = df['ADX'].iloc[-1]

                    # 🔹 Новый фильтр тренда: ADX > 20 подтверждает силу
                    signal = None
                    if last_macd > last_signal_line and last_rsi < 55 and last_adx > 20:
                        signal = "LONG"
                    elif last_macd < last_signal_line and last_rsi > 45 and last_adx > 20:
                        signal = "SHORT"

                    # Проверка смены тренда
                    if symbol in trend_history and trend_history[symbol] != signal:
                        print(f"⚠️ {symbol}: Тренд изменился с {trend_history[symbol]} на {signal}")

                        if symbol in active_trades:
                            print(f"🔄 Закрываем старую сделку {symbol}")
                            await send_message_safe(f"⚠️ **{symbol} изменил тренд! Старая сделка закрыта.**")
                            del active_trades[symbol]

                        await send_trade_signal(symbol, price, signal)

                    trend_history[symbol] = signal  

                    if symbol not in active_trades and signal:
                        await send_trade_signal(symbol, price, signal)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")

# 🔹 Отправка сигнала
async def send_trade_signal(symbol, price, trend):
    decimal_places = len(str(price).split(".")[-1])  

    tp_multiplier = 3  
    sl_multiplier = 1.5  

    tp = round(price + (price * 0.01 * tp_multiplier) if trend == "LONG" else price - (price * 0.01 * tp_multiplier), decimal_places)
    sl = round(price - (price * 0.01 * sl_multiplier) if trend == "LONG" else price + (price * 0.01 * sl_multiplier), decimal_places)

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
    return prices.diff().rolling(window=period).mean()

def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window, adjust=False).mean()
    long_ema = prices.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

def compute_adx(df, period=14):
    return df['close'].diff().abs().rolling(window=period).mean()

async def send_message_safe(message):
    await bot.send_message(TELEGRAM_CHAT_ID, message)

async def main():
    asyncio.create_task(start_futures_websocket())  
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
