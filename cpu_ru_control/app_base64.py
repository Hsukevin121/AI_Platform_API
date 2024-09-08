from flask import Flask, jsonify, request
import requests
import base64
from functools import wraps

app = Flask(__name__)

# 用户名和密码
USERNAME = 'AIadmin'
PASSWORD = 'admin0000'

# 验证装饰器
def authenticate(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if auth_header:
            auth_type, credentials = auth_header.split(' ')
            if auth_type.lower() == 'basic':
                decoded_credentials = base64.b64decode(credentials).decode('utf-8')
                username, password = decoded_credentials.split(':')
                if username == USERNAME and password == PASSWORD:
                    return func(*args, **kwargs)
        return jsonify({'status': 'Unauthorized'}), 401
    return decorated_function

@app.route('/api/v1/ORAN/cpu', methods=['PUT'])
@authenticate
def control_cpu():
    data = request.json
    status = data.get('status')

    if status == "1":
        try:
            response = requests.get(
                'https://192.168.135.102:16000/api/v2/idle-state/bbu/enable',
                headers={'accept': 'application/json'},
                verify=False
            )
            return response.json(), 200
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500

    elif status == "2":
        try:
            response = requests.get(
                'https://192.168.135.102:16000/api/v2/idle-state/bbu/disable',
                headers={'accept': 'application/json'},
                verify=False
            )
            return response.json(), 200
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500

    else:
        return jsonify({"error": "Invalid status parameter"}), 400

@app.route('/api/v1/ORAN/cpu/info', methods=['GET'])
@authenticate
def info_cpu():
    try:
        response = requests.get(
            'https://192.168.135.102:16000/api/v2/info/hardware/bbu',
            headers={'accept': 'application/json'},
            verify=False
        )
        return jsonify({"message": "CPU Info", "response": response.json()}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500    
    
@app.route('/api/v1/ORAN/ru', methods=['PUT'])
@authenticate
def control_ru():
    data = request.json
    model = data.get('model')

    tx_power_map = {
        "1": {"ru_id": "ru1", "tx_power": "24"},
        "2": {"ru_id": "ru1", "tx_power": "22"},
        "3": {"ru_id": "ru1", "tx_power": "20"},
        "4": {"ru_id": "ru1", "tx_power": "18"},
        "5": {"ru_id": "ru1", "tx_power": "16"},
        "6": {"ru_id": "ru1", "tx_power": "14"},
        "7": {"ru_id": "ru1", "tx_power": "12"},
        "8": {"ru_id": "ru1", "tx_power": "10"},
    }

    # 查找 model 对应的 tx_power 和 ru_id
    ru_info = tx_power_map.get(model)
    if ru_info is None:
        return jsonify({"error": "Invalid model parameter"}), 400

    ru_id = ru_info["ru_id"]
    tx_power = ru_info["tx_power"]

    url = f"https://192.168.135.102:16000/api/mplane-proxy/oran-mp/operation/tx-power/{ru_id}"

    # 发送PUT请求来设置TX power
    try:
        response = requests.post(
            url,
            json={"tx_power": tx_power},
            headers={'accept': 'application/json'},
            verify=False
        )
        return jsonify({"response": response.json()}), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/ORAN/ru/info', methods=['GET'])
@authenticate
def info_ru():
    
    try:
        response = requests.get(
            'https://192.168.135.102:16000/api/mplane-proxy/oran-mp/ru/info/software',
            headers={'accept': 'application/json'},
            verify=False
        )
        return jsonify({"message": "RU Info", "response": response.json()}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500    

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
