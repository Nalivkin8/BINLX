import pandas as pd

# 🔹 ATR (Средний истинный диапазон)
def compute_atr(df, period=14):
    df['tr'] = df['close'].diff().abs()
    atr = df['tr'].rolling(window=period).mean()
    return atr

# 🔹 RSI (Индекс относительной силы)
def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# 🔹 MACD (Сходимость/Расходимость скользящих средних)
def compute_macd(prices, short_window=12, long_window=26, signal_window=9):
    short_ema = prices.ewm(span=short_window, adjust=False).mean()
    long_ema = prices.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line
