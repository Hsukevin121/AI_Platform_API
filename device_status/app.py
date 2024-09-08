from flask import Flask, request, jsonify
import pymysql
import base64
from functools import wraps
import datetime

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

@app.route('/api/v1/ORAN/deviceList/status', methods=['GET'])
#@authenticate
def get_device_list():
    serverid = request.args.get('serverid')
    if serverid != "10001":
        return jsonify({"error": "Invalid serverid parameter"}), 400

    try:
        # 在每次请求时重新建立数据库连接
        db_connection = pymysql.connect(
            host='192.168.0.39',
            user='root',
            password='rtlab666',
            database='devicelist'
        )

        with db_connection.cursor() as cursor:
            # 从数据库中检索devicelist，增加updated_at列
            sql = "SELECT deviceid, devicename, status, message, updated_at FROM devicelist"
            cursor.execute(sql)
            device_list = cursor.fetchall()

            # 检查所有设备的状态
            system_status = "healthy" if all(row[2] == 1 for row in device_list) else "issue"

        response = {
            "status": system_status,
            "deviceslist": [
                {
                    "deviceid": row[0], 
                    "devicename": row[1], 
                    "status": row[2], 
                    "message": row[3], 
                    "reporttime": row[4].strftime('%Y-%m-%d %H:%M:%S')  # 格式化时间
                } for row in device_list
            ]
        }

        db_connection.close()

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
