from flask import Flask, request, jsonify
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

@app.route('/api/v1/ORAN/deviceList', methods=['GET'])
@authenticate
def get_device_list():
    serverid = request.args.get('serverid')
    if serverid != "10001":
        return jsonify({"error": "Invalid serverid parameter"}), 400

    device_list = [
        {"deviceid": 2001, "devicetype": "RU01001", "status": 1},
        {"deviceid": 3001, "devicetype": "DU01001", "status": 1},
        {"deviceid": 4001, "devicetype": "CU01001", "status": 1},
        {"deviceid": 5001, "devicetype": "PDU01001", "status": 1}
    ]

    response = {
        "status": "healthy",
        "reporttime": "20240723115349",
        "deviceslist": device_list
    }

    return jsonify(response), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
