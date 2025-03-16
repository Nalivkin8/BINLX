import websocket
import json
import asyncio
import pandas as pd
import time
from aiogram.exceptions import TelegramRetryAfter

# Храним активные сделки и последние тренды
active_trades = {}  # {"TSTUSDT": {"signal": "LONG", "tp": 5.55, "sl": 5.40}}
last_trend = {}  # {"TSTUSDT": "Bullish"}

# Переменные для сигналов и истории
price_history = {"TSTUSDT": [], "IPUSDT": []}

# Подключение к WebSocket Binance Futures
async def start_futures_websocket(bot, chat_id):
    loop = asyncio.get_event_loop()
    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_message=lambda ws, msg: loop.create_task(process_futures_message(bot, chat_id, msg)),
        on_open=on_open
    )
    await asyncio.to_thread(ws.run_forever)

# Обрабатываем сообщения WebSocket
async def process_futures_message(bot, chat_id, message):
    global active_trades, last_trend, price_history
    try:
        data = json.loads(message)

        if 's' in data and 'p' in data:
            symbol = data['s']
            price = float(data['p'])

            # Проверяем активные сделки
            if symbol in active_trades:
                trade = active_trades[symbol]
                if (trade["signal"] == "LONG" and price >= trade["tp"]) or (trade["signal"] == "SHORT" and price <= trade["tp"]):
                    await bot.send_message(chat_id, f"🎯 **{symbol} достиг Take Profit ({trade['tp']} USDT)**")
                    del active_trades[symbol]
                elif (trade["signal"] == "LONG" and price <= trade["sl"]) or (trade["signal"] == "SHORT" and price >= trade["sl"]):
                    await bot.send_message(chat_id, f"⛔ **{symbol} достиг Stop Loss ({trade['sl']} USDT)**")
                    del active_trades[symbol]

            if symbol in price_history:
                price_history[symbol].append(price)

                if len(price_history[symbol]) > 200:
                    price_history[symbol].pop(0)

                    df = pd.DataFrame(price_history[symbol], columns=['close'])
                    df['SMA_50'] = df['close'].rolling(window=50).mean()
                    df['SMA_200'] = df['close'].rolling(window=200).mean()
                    df['EMA_9'] = df['close'].ewm(span=9, adjust=False).mean()
                    df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()
                    df['RSI'] = compute_rsi(df['close'])
                    df['MACD'], df['Signal_Line'] = compute_macd(df['close'])
                    df['VWAP'] = compute_vwap(df)
                    df['ADX'] = compute_adx(df)

                    last_sma_50 = df['SMA_50'].iloc[-1]
                    last_sma_200 = df['SMA_200'].iloc[-1]
                    last_ema_9 = df['EMA_9'].iloc[-1]
                    last_ema_21 = df['EMA_21'].iloc[-1]
                    last_macd = df['MACD'].iloc[-1]
                    last_signal_line = df['Signal_Line'].iloc[-1]
                    last_adx = df['ADX'].iloc[-1]

                    # Определяем тренд
                    trend = "Neutral"
                    if last_sma_50 > last_sma_200 and last_ema_9 > last_ema_21:
                        trend = "Bullish"
                    elif last_sma_50 < last_sma_200 and last_ema_9 < last_ema_21:
                        trend = "Bearish"

                    # Если тренд изменился, проверяем подтверждение
                    if symbol in last_trend and last_trend[symbol] != trend:
                        confirmation = 0
                        if df['SMA_50'].iloc[-2] > df['SMA_200'].iloc[-2] and last_sma_50 < last_sma_200:
                            confirmation += 1  # Пересечение SMA 50/200 вниз
                        if df['EMA_9'].iloc[-2] > df['EMA_21'].iloc[-2] and last_ema_9 < last_ema_21:
                            confirmation += 1  # Пересечение EMA 9/21 вниз
                        if df['MACD'].iloc[-2] > 0 and last_macd < 0:
                            confirmation += 1  # MACD пересек 0 вниз
                        if last_adx < 20:
                            confirmation += 1  # ADX показывает слабый тренд

                        # Если подтверждено на 100% (4 из 4 факторов)
                        if confirmation >= 4:
                            await bot.send_message(chat_id, f"⚠️ **ВНИМАНИЕ! Тренд по {symbol} резко изменился! Сделка под угрозой.**\n🔹 **Текущий тренд**: {trend}")

                    last_trend[symbol] = trend  # Обновляем последний тренд

                    # Генерация нового сигнала без ограничения по времени
                    signal = None
                    if trend == "Bullish" and df['RSI'].iloc[-1] < 30 and last_macd > last_signal_line and last_adx > 25:
                        signal = "LONG"
                    elif trend == "Bearish" and df['RSI'].iloc[-1] > 70 and last_macd < last_signal_line and last_adx > 25:
                        signal = "SHORT"

                    # Take Profit +10%, Stop Loss -5%
                    take_profit = round(price * 1.10, 2)
                    stop_loss = round(price * 0.95, 2)

                    if signal:
                        active_trades[symbol] = {"signal": signal, "tp": take_profit, "sl": stop_loss}

                        message = (
                            f"📌 **Сигнал на {signal} {symbol} (Futures)**\n"
                            f"🔹 **Цена входа**: {price} USDT\n"
                            f"🎯 **Take Profit (+10%)**: {take_profit} USDT\n"
                            f"⛔ **Stop Loss (-5%)**: {stop_loss} USDT\n"
                            f"📊 **Тренд**: {trend}"
                        )
                        await bot.send_message(chat_id, message)

    except Exception as e:
        print(f"❌ Ошибка WebSocket: {e}")
