import requests
import pandas as pd

def get_historical_data(symbol, interval='1h', limit=10):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"❌ Ошибка запроса Binance API: {response.status_code}")
        return pd.DataFrame()

    data = response.json()
    
    if not data:
        print("❌ Binance API вернул пустой массив!")
        return pd.DataFrame()
    
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'])
    df['close'] = df['close'].astype(float)
    
    print("✅ Данные Binance API загружены!")
    print(df.tail())  # Выводим последние свечи
    return df

df = get_historical_data("BTCUSDT")
