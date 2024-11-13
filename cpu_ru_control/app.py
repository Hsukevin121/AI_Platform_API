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

# 数据库连接
db_connection = pymysql.connect(
    host=config.DB_HOST,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    database=config.DB_DATABASE,
    autocommit=True
)

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

# 更新数据库中设备的 model 字段
def update_device_model(devicename, model_value):
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
            db_connection.commit()
    except Exception as e:
        print(f"Failed to update model for {devicename}: {e}")
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()


#def update_device_model1(devicename1, devicename2, model_value):
#    try:
#        with db_connection.cursor() as cursor:
#            sql = "UPDATE devicelist SET model = %s WHERE devicename = %s OR devicename = %s"
#            cursor.execute(sql, (model_value, devicename1, devicename2))
#            db_connection.commit()
#    except Exception as e:
#        print(f"Failed to update model for {devicename1} and {devicename2}: {e}")




@app.route('/api/v1/ORAN/cu/info', methods=['GET'])
#@authenticate
def info_cpu():
    try:
        # 调用底层API获取CU信息
        response = requests.get(
            f'{config.API_BASE_URL}/api/v2/info/hardware/bbu',
            headers={'accept': 'application/json'},
            verify=config.VERIFY_SSL
        )
        return jsonify({"message": "CPU Info", "response": response.json()}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/ORAN/cu', methods=['PUT'])
#@authenticate
def control_cpu_energy_saving():
    data = request.json
    devicename = data.get('devicename')
    model = data.get('model')

    # 检查是否缺少必需的参数
    if not devicename or not model:
        return jsonify({"error": "Missing devicename or model parameter"}), 400

    # CPU 节能模式映射
    if model == "1":
        try:
            response = requests.get(
                f'{config.API_BASE_URL}/api/v2/idle-state/bbu/enable',
                headers={'accept': 'application/json'},
                verify=config.VERIFY_SSL
            )

            # 更新数据库中的 model 字段
            update_device_model("CU01001", 1)

            return jsonify({"message":"CU01001 and DU01001 open the energy saving model"}), 200
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500

    elif model == "2":
        try:
            response = requests.get(
                f'{config.API_BASE_URL}/api/v2/idle-state/bbu/disable',
                headers={'accept': 'application/json'},
                verify=config.VERIFY_SSL
            )

            # 更新数据库中的 model 字段
            update_device_model("CU01001", 2)

            return jsonify({"message": "CU01001 and DU01001 close the energy saving model"}), 200
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500

    else:
        return jsonify({"error": "Invalid model parameter"}), 400

@app.route('/api/v1/ORAN/ru', methods=['PUT'])
#@authenticate
def control_ru_power():
    data = request.json
    devicename = data.get('devicename')
    model = data.get('model')

    # 检查是否缺少必需的参数
    if not devicename or not model:
        return jsonify({"error": "Missing devicename or model parameter"}), 400

    # 定义 tx_power 的映射 (只传递数值)
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

    # 获取对应的 tx_power 数值
    tx_power = tx_power_map.get(model)
    if not tx_power:
        return jsonify({"error": "Invalid model parameter"}), 400

    # 使用传入的 devicename 来构建 URL
    url = f'{config.API_BASE_URL}/api/mplane-proxy/oran-mp/operation/tx-power/ru1'

    # 发送请求来设置RU的 tx_power
    try:
        response = requests.post(
            url,
            json={"tx_power": tx_power},  # 只发送数值
            headers={'accept': 'application/json'},
            verify=config.VERIFY_SSL  # 如果不验证证书，确保设置 verify=config.VERIFY_SSL
        )

        if response.status_code == 200:
            response_data = response.json()

            # 更新数据库中的 model 字段
            update_device_model("RU01001", model)

            # 将 "ru1" 替换为 devicename ("RU01001")
            if 'msg' in response_data and 'ru1' in response_data['msg']:
                response_data['msg'][devicename] = response_data['msg'].pop('ru1')

            return jsonify({
                "response": {
                    "msg": {
                        devicename: {
                            "success": response_data['msg'][devicename]['success'],
                            "tx_power": response_data['msg'][devicename]['tx_power']
                        }
                    },
                    "success": response_data['success']
                }
            }), 200

        else:
            return jsonify({
                "error": f"Failed to set tx_power. Status code: {response.status_code}",
                "details": response.text
            }), 500

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run( host='0.0.0.0', port=8080)
