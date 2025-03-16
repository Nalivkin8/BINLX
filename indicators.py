import pandas as pd
import requests

# Получение данных с Binance Futures
def get_futures_data(symbol, interval='15m', limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"❌ Ошибка Binance Futures API: {response.status_code}")
        return pd.DataFrame()

    data = response.json()
    
    if not data:
        print("❌ Binance API вернул пустой массив!")
        return pd.DataFrame()
    
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'])
    df['close'] = df['close'].astype(float)
    return df

# Рассчет индикаторов
def compute_indicators(df):
    df['SMA_50'] = df['close'].rolling(window=50).mean()
    df['SMA_200'] = df['close'].rolling(window=200).mean()
    df['ATR'] = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    return df

# Генерация сигналов с расчетом TP/SL
def generate_signal(df):
    if df.empty:
        return None, None, None, None

    last_row = df.iloc[-1]

    take_profit = last_row['close'] + 1.5 * last_row['ATR']
    stop_loss = last_row['close'] - 1.5 * last_row['ATR']

    if last_row['close'] > last_row['SMA_50'] and last_row['close'] > last_row['SMA_200']:
        return "LONG", last_row['close'], take_profit, stop_loss
    elif last_row['close'] < last_row['SMA_50'] and last_row['close'] < last_row['SMA_200']:
        return "SHORT", last_row['close'], take_profit, stop_loss
    
    return None, None, None, None
