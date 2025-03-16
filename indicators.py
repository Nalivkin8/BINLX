import pandas as pd
import requests

# Получение данных с Binance Futures
def get_futures_data(symbol, interval='15m', limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
    }
    
    response = requests.get(url, headers=headers)
    
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
