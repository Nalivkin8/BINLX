import asyncio
import json
import os
import websocket
import pandas as pd
from statistics import mean
from telegram import Bot

# 🔹 API-ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 🔹 Торговые пары
TRADE_PAIRS = ["adausdt", "ipusdt", "tstusdt"]

# 🔹 WebSocket Binance Futures
STREAMS = [f"{pair}@kline_1m" for pair in TRADE_PAIRS]  # 1-минутные свечи для быстрого анализа
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams=" + "/".join(STREAMS)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
candle_data = {pair: pd.DataFrame(columns=["timestamp", "close"]) for pair in TRADE_PAIRS}
last_signal = {pair: None for pair in TRADE_PAIRS}  # Запоминаем последний сигнал

def calculate_rsi(df, period=14):
    """🔹 Рассчет RSI"""
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else None

def calculate_sma(df, period=50):
    """🔹 Рассчет SMA"""
    return df["close"].rolling(window=period).mean().iloc[-1] if not df.empty else None

def on_message(ws, message):
    """🔹 Обработка входящих данных из WebSocket"""
    data = json.loads(message)

    if "stream" in data and "data" in data:
        stream = data["stream"]
        pair = stream.split("@")[0].upper()
        event_type = stream.split("@")[1]

        if event_type.startswith("kline"):
            # 📊 Обработка свечей (Kline)
            price = float(data["data"]["k"]["c"])
            timestamp = data["data"]["k"]["t"]
            is_closed = data["data"]["k"]["x"]

            if is_closed:
                df = candle_data[pair]
                new_row = pd.DataFrame({"timestamp": [timestamp], "close": [price]})
                candle_data[pair] = pd.concat([df, new_row], ignore_index=True)

                if len(candle_data[pair]) > 50:
                    candle_data[pair] = candle_data[pair].iloc[-50:]

                # Рассчитываем индикаторы
                rsi = calculate_rsi(candle_data[pair])
                sma_50 = calculate_sma(candle_data[pair], period=50)
                sma_200 = calculate_sma(candle_data[pair], period=200)

                # Условия для Лонга/Шорта
                signal = ""
                take_profit = None
                stop_loss = None

                if rsi and sma_50 and sma_200:
                    if rsi < 30 and price > sma_50:
                        take_profit = round(price * 1.02, 6)  # TP +2%
                        stop_loss = round(price * 0.98, 6)  # SL -2%
                        signal = f"🚀 **Лонг {pair}**\n💰 Цена: {price}\n🎯 TP: {take_profit}\n🛑 SL: {stop_loss}\n📊 RSI: {rsi:.2f} | SMA-50: {sma_50:.6f}"

                    elif rsi > 70 and price < sma_50:
                        take_profit = round(price * 0.98, 6)  # TP -2%
                        stop_loss = round(price * 1.02, 6)  # SL +2%
                        signal = f"⚠️ **Шорт {pair}**\n💰 Цена: {price}\n🎯 TP: {take_profit}\n🛑 SL: {stop_loss}\n📊 RSI: {rsi:.2f} | SMA-50: {sma_50:.6f}"

                # Проверка, был ли такой же сигнал ранее
                if signal and last_signal[pair] != signal:
                    last_signal[pair] = signal  # Запоминаем последний сигнал
                    asyncio.run(bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=signal))

def start_websocket():
    """🔹 Запуск WebSocket"""
    ws = websocket.WebSocketApp(BINANCE_WS_URL, on_message=on_message)
    ws.run_forever()

async def main():
    """🔹 Запуск WebSocket-бота"""
    loop = asyncio.get_running_loop()
    websocket_task = loop.run_in_executor(None, start_websocket)
    await websocket_task

if __name__ == "__main__":
    asyncio.run(main(), debug=True)
