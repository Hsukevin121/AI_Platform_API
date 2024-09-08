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
                f'https://192.168.135.102:16000/api/v2/idle-state/bbu/enable',
                headers={'accept': 'application/json'},
                verify=False
            )
            return jsonify({"message": f"{devicename} open the energy saving model"}), 200
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500

    elif model == "2":
        try:
            response = requests.get(
                f'https://192.168.135.102:16000/api/v2/idle-state/bbu/disable',
                headers={'accept': 'application/json'},
                verify=False
            )
            return jsonify({"message": f"{devicename} close the energy saving model"}), 200
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500

    else:
        return jsonify({"error": "Invalid model parameter"}), 400

@app.route('/api/v1/ORAN/cu/info', methods=['GET'])
#@authenticate
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
    url = f'https://192.168.135.102:16000/api/mplane-proxy/oran-mp/operation/tx-power/ru1'

    # 发送请求来设置RU的 tx_power
    try:
        response = requests.post(
            url,
            json={"tx_power": tx_power},  # 只发送数值
            headers={'accept': 'application/json'},
            verify=False  # 如果不验证证书，确保设置 verify=False
        )

        # 处理返回的真实回报
        if response.status_code == 200:
            response_data = response.json()

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

@app.route('/api/v1/ORAN/ru/info', methods=['GET'])
#@authenticate
def info_ru():
    try:
        # 调用底层API获取RU信息
        response = requests.get(
            'https://192.168.135.102:16000/api/mplane-proxy/oran-mp/ru/info/software',
            headers={'accept': 'application/json'},
            verify=False
        )
        
        if response.status_code == 200:
            response_data = response.json()

            # 保留 ru1 并将其重命名为 RU01001，删除 ru2
            if 'msg' in response_data and 'ru1' in response_data['msg']:
                response_data['msg']['RU01001'] = response_data['msg'].pop('ru1')

            # 删除 ru2
            if 'ru2' in response_data['msg']:
                del response_data['msg']['ru2']

            return jsonify({"message": "RU Info", "response": response_data}), 200
        else:
            return jsonify({"error": f"Failed to get RU info. Status code: {response.status_code}"}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500 

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
