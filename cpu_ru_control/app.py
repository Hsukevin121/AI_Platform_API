from flask import Flask, jsonify, request
import requests
import base64
import pymysql
from functools import wraps
import urllib3
import config  # 引入config.py

app = Flask(__name__)

# 禁用 InsecureRequestWarning 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 使用全局会话管理 HTTP 连接
session = requests.Session()
session.headers.update({'accept': 'application/json'})

def get_db_connection():
    try:
        connection = pymysql.connect(
            host=config.DB_HOST,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_DATABASE,
            autocommit=True
        )
        print("Database connection successful")
        return connection
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

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
                if username == config.USERNAME and password == config.PASSWORD:
                    return func(*args, **kwargs)
        return jsonify({'status': 'Unauthorized'}), 401
    return decorated_function

def update_device_model(devicename, model_value):
    db_connection = get_db_connection()
    if not db_connection:
        print("Failed to get database connection")
        return False  # 数据库连接失败
    try:
        with db_connection.cursor() as cursor:
            if devicename == "RU01001":
                sql = "UPDATE devicelist SET model = %s WHERE devicename = %s"
                cursor.execute(sql, (model_value, devicename))
            elif devicename == "CU01001":
                sql = "UPDATE devicelist SET model = %s WHERE devicename = %s OR devicename = %s"
                cursor.execute(sql, (model_value, "CU01001", "DU01001"))
            else:
                print(f"Device {devicename} is not supported.")
                return False
            db_connection.commit()
            print(f"Successfully updated model for {devicename}")
            return True
    except Exception as e:
        print(f"Failed to update model for {devicename}: {e}")
        return False
    finally:
        db_connection.close()


@app.route('/api/v1/ORAN/cu/info', methods=['GET'])
#@authenticate
def info_cpu():
    try:
        # 调用底层API获取CU信息
        with session.get(
            f'{config.API_BASE_URL}/api/v2/info/hardware/bbu',
            verify=config.VERIFY_SSL
        ) as response:
            return jsonify({"message": "CPU Info", "response": response.json()}), 200
    except requests.exceptions.RequestException as e:
        print(f"Failed to call API: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/ORAN/cu', methods=['PUT'])
def control_cpu_energy_saving():
    data = request.json
    devicename = data.get('devicename')
    model = data.get('model')

    if not devicename or not model:
        return jsonify({"error": "Missing devicename or model parameter"}), 400

    url = f'{config.API_BASE_URL}/api/v2/idle-state/bbu/{"enable" if model == "1" else "disable"}'
    try:
        with session.get(url, verify=config.VERIFY_SSL) as response:
            if response.status_code == 200 and update_device_model("CU01001", int(model)):
                action = "open" if model == "1" else "close"
                return jsonify({"message": f"CU01001 and DU01001 {action} the energy saving model"}), 200
            else:
                return jsonify({"error": "Failed to update database or call API"}), 500
    except requests.exceptions.RequestException as e:
        print(f"Failed to call API: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/ORAN/ru', methods=['PUT'])
#@authenticate
def control_ru_power():
    data = request.json
    devicename = data.get('devicename')
    model = data.get('model')

    if not devicename or not model:
        return jsonify({"error": "Missing devicename or model parameter"}), 400

    tx_power_map = {
        "1": "24",
        "2": "22",
        "3": "20",
        "4": "18",
        "5": "16",
        "6": "14",
        "7": "12",
        "8": "10"
    }
    tx_power = tx_power_map.get(model)
    if not tx_power:
        return jsonify({"error": "Invalid model parameter"}), 400

    url = f'{config.API_BASE_URL}/api/mplane-proxy/oran-mp/operation/tx-power/ru1'

    try:
        with session.post(
            url,
            json={"tx_power": tx_power},
            verify=config.VERIFY_SSL
        ) as response:
            if response.status_code == 200:
                response_data = response.json()
                if update_device_model("RU01001", int(model)):
                    if 'msg' in response_data and 'ru1' in response_data['msg']:
                        response_data['msg'][devicename] = response_data['msg'].pop('ru1')
                    return jsonify({"response": response_data}), 200
                else:
                    return jsonify({"error": "Failed to update database"}), 500
            else:
                return jsonify({
                    "error": f"Failed to set tx_power. Status code: {response.status_code}",
                    "details": response.text
                }), 500
    except requests.exceptions.RequestException as e:
        print(f"Failed to call API: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
