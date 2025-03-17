import requests
import time
import hmac
import hashlib
import os
import json
from urllib.parse import urlencode

# Загружаем API-ключи из переменных среды
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_SECRET_KEY")

# URL Binance Futures API
BASE_URL = "https://fapi.binance.com"

# Функция для подписи запроса
def sign_request(params):
    query_string = urlencode(params)
    signature = hmac.new(API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

# Функция для запроса к API Binance
def send_signed_request(method, endpoint, params=None):
    headers = {
        "X-MBX-APIKEY": API_KEY
    }
    params = params or {}
    params["timestamp"] = int(time.time() * 1000)
    params = sign_request(params)

    if method == "GET":
        response = requests.get(BASE_URL + endpoint, headers=headers, params=params)
    else:
        response = requests.post(BASE_URL + endpoint, headers=headers, params=params)

    return response.json()

# Функция для получения баланса USDT
def get_balance():
    response = send_signed_request("GET", "/fapi/v2/balance")
    for asset in response:
        if asset["asset"] == "USDT":
            return f"💰 Баланс USDT: {asset['balance']} USDT"

# Функция для получения открытых позиций
def get_open_positions():
    response = send_signed_request("GET", "/fapi/v2/positionRisk")
    positions = []
    
    for position in response:
        if float(position["positionAmt"]) != 0:  # Фильтруем только активные сделки
            positions.append(f"📊 {position['symbol']} | Кол-во: {position['positionAmt']} | PNL: {position['unRealizedProfit']} USDT")
    
    return "\n".join(positions) if positions else "✅ Нет открытых позиций"

# Основная функция для вывода информации
def main():
    balance = get_balance()
    positions = get_open_positions()
    print(balance)
    print(positions)

if __name__ == "__main__":
    main()
