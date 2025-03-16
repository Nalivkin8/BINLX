import pandas as pd
import requests

def get_historical_data(symbol, interval='1h', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()
    
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'])
    df['close'] = df['close'].astype(float)
    return df

def compute_indicators(df):
    df['SMA_50'] = df['close'].rolling(window=50).mean()
    df['SMA_200'] = df['close'].rolling(window=200).mean()

    delta = df['close'].diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    df['MACD'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    return df

def generate_signal(df):
    last_row = df.iloc[-1]

    buy_signal = (last_row['close'] > last_row['SMA_50'] and last_row['MACD'] > last_row['Signal_Line'] and last_row['RSI'] < 30)
    sell_signal = (last_row['close'] < last_row['SMA_50'] and last_row['MACD'] < last_row['Signal_Line'] and last_row['RSI'] > 70)

    if buy_signal:
        return "BUY", last_row['close']
    elif sell_signal:
        return "SELL", last_row['close']
    return None, None
