import asyncio
import json
import os
import websocket
import pandas as pd
import numpy as np
from statistics import mean
from telegram import Bot
from datetime import datetime

# 🔹 API-ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 🔹 WebSocket Binance Futures
TRADE_PAIRS = ["adausdt", "ipusdt", "tstusdt"]
STREAMS = [f"{pair}@kline_1m" for pair in TRADE_PAIRS]  # 1-минутные свечи для скальпинга
BINANCE_WS_URL = f"wss://fstream.binance.com/stream?streams=" + "/".join(STREAMS)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
candle_data = {pair: pd.DataFrame(columns=["timestamp", "close", "volume"]) for pair in TRADE_PAIRS}
last_signal = {pair: None for pair in TRADE_PAIRS}  # Запоминаем последний сигнал
scalping_mode = True  # Включен режим скальпинга

async def send_telegram_message(text):
    """🔹 Отправка сообщений в Telegram"""
    print(f"📨 Telegram: {text}")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

def calculate_rsi(df, period=14):
    """🔹 Рассчет RSI"""
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else None

def calculate_vwap(df):
    """🔹 Рассчет VWAP (Volume Weighted Average Price)"""
    typical_price = (df["close"] + df["close"].shift(1)) / 2
    vwap = (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()
    return vwap.iloc[-1] if not vwap.empty else None

def calculate_sma(df, period=10):
    """🔹 Рассчет SMA"""
    return df["close"].rolling(window=period).mean().iloc[-1] if not df.empty else None

def calculate_volatility(df, period=10):
    """🔹 Рассчет волатильности"""
    if len(df) < period:
        return None
    return mean(df["close"].pct_change().abs().tail(period))

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
            volume = float(data["data"]["k"]["v"])
            is_closed = data["data"]["k"]["x"]

            if is_closed:
                df = candle_data[pair]
                new_row = pd.DataFrame({"timestamp": [timestamp], "close": [price], "volume": [volume]})
                candle_data[pair] = pd.concat([df, new_row], ignore_index=True)

                if len(candle_data[pair]) > 50:
                    candle_data[pair] = candle_data[pair].iloc[-50:]

                # Рассчитываем индикаторы
                rsi = calculate_rsi(candle_data[pair], period=5)
                sma_10 = calculate_sma(candle_data[pair], period=10)
                vwap = calculate_vwap(candle_data[pair])
                volatility = calculate_volatility(candle_data[pair], period=5)

                # Условия для скальпинга
                signal = ""
                take_profit = None
                stop_loss = None

                if rsi and sma_10 and vwap and volatility:
                    risk_factor = round(volatility * 5, 6)  # Увеличиваем TP при высокой волатильности
                    timestamp_str = datetime.utcfromtimestamp(timestamp // 1000).strftime('%H:%M:%S')

                    if rsi < 30 and price > vwap:
                        take_profit = round(price + risk_factor, 6)
                        stop_loss = round(price - (risk_factor / 2), 6)
                        signal = f"🚀 **Лонг {pair}**\n⏰ {timestamp_str}\n💰 Цена: {price}\n🎯 TP: {take_profit}\n🛑 SL: {stop_loss}\n📊 RSI: {rsi:.2f} | VWAP: {vwap:.6f} | SMA-10: {sma_10:.6f}"

                    elif rsi > 70 and price < vwap:
                        take_profit = round(price - risk_factor, 6)
                        stop_loss = round(price + (risk_factor / 2), 6)
                        signal = f"⚠️ **Шорт {pair}**\n⏰ {timestamp_str}\n💰 Цена: {price}\n🎯 TP: {take_profit}\n🛑 SL: {stop_loss}\n📊 RSI: {rsi:.2f} | VWAP: {vwap:.6f} | SMA-10: {sma_10:.6f}"

                # Проверка на дубли сигналов
                if signal and last_signal[pair] != signal:
                    last_signal[pair] = signal
                    asyncio.run(send_telegram_message(signal))

def start_websocket():
    """🔹 Запуск WebSocket"""
    ws = websocket.WebSocketApp(BINANCE_WS_URL, on_message=on_message)
    ws.run_forever()

async def main():
    """🔹 Запуск WebSocket-бота"""
    loop = asyncio.get_running_loop()
    websocket_task = loop.run_in_executor(None, start_websocket)
    await asyncio.gather(websocket_task)

if __name__ == "__main__":
    asyncio.run(main(), debug=True)
