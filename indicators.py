import pandas as pd
import requests

# Получение исторических данных через Binance API
def get_historical_data(symbol, interval='1h', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"❌ Ошибка Binance API: {response.status_code}")
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
    df['RSI'] = 100 - (100 / (1 + df['close'].pct_change().rolling(window=14).mean()))
    df['MACD'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
    return df

# Генерация торговых сигналов
def generate_signal(df):
    if df.empty:
        return None, None

    last_row = df.iloc[-1]

    if last_row['close'] > last_row['SMA_50'] and last_row['RSI'] < 30:
        return "BUY", last_row['close']
    elif last_row['close'] < last_row['SMA_50'] and last_row['RSI'] > 70:
        return "SELL", last_row['close']
    
    return None, None
