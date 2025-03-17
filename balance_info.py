import requests
import hmac
import hashlib
import time
import os

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

BASE_URL = "https://fapi.binance.com"  # Binance Futures API

# Функция подписи запроса
def sign_request(params):
    query_string = '&'.join([f"{key}={params[key]}" for key in sorted(params)])
    signature = hmac.new(BINANCE_SECRET_KEY.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    params['signature'] = signature
    return params

# Получение баланса
def get_balance():
    endpoint = "/fapi/v2/balance"
    params = {
        "timestamp": int(time.time() * 1000)
    }
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    response = requests.get(BASE_URL + endpoint, params=sign_request(params), headers=headers)
    return response.json()

# Получение открытых позиций
def get_open_positions():
    endpoint = "/fapi/v2/positionRisk"
    params = {
        "timestamp": int(time.time() * 1000)
    }
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    response = requests.get(BASE_URL + endpoint, params=sign_request(params), headers=headers)
    return response.json()

# Запуск API-сервера с Flask
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/balance", methods=["GET"])
def balance():
    balance_data = get_balance()
    return jsonify(balance_data)

@app.route("/positions", methods=["GET"])
def positions():
    positions_data = get_open_positions()
    return jsonify(positions_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
