from flask import Flask, request, jsonify
import pymysql
import base64
import hashlib
from functools import wraps
import datetime

app = Flask(__name__)

# 用户名和密码
USERNAME = 'AIadmin'
PASSWORD = 'admin0000'

# MySQL数据库连接信息
db_connection = pymysql.connect(
    host='localhost',
    user='root',
    password='rtlab666',
    database='devicelist'
)

# 验证装饰器
def authenticate(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if auth_header:
            auth_type, credentials = auth_header.split(' ')
            if auth_type.lower() == 'basic':
                # Base64 解码
                decoded_credentials = base64.b64decode(credentials).decode('utf-8')
                
                # 使用 MD5 加密
                md5_hash = hashlib.md5(decoded_credentials.encode('utf-8')).hexdigest()
                
                # 分离用户名和密码
                username, password = decoded_credentials.split(':')
                
                # 对比 Base64+MD5 加密后的用户名和密码
                if username == USERNAME and md5_hash == hashlib.md5(PASSWORD.encode('utf-8')).hexdigest():
                    return func(*args, **kwargs)
        return jsonify({'status': 'Unauthorized'}), 401
    return decorated_function

@app.route('/api/v1/ORAN/deviceList', methods=['GET'])
@authenticate
def get_device_list():
    serverid = request.args.get('serverid')
    if serverid != "10001":
        return jsonify({"error": "Invalid serverid parameter"}), 400

    try:
        with db_connection.cursor() as cursor:
            # 从数据库中检索devicelist
            sql = "SELECT deviceid, devicetype, status FROM devicelist"
            cursor.execute(sql)
            device_list = cursor.fetchall()

            # 格式化数据以匹配API响应格式
            devices = [{"deviceid": row[0], "devicetype": row[1], "status": row[2]} for row in device_list]

        response = {
            "status": "healthy",
            "reporttime": datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S"),
            "deviceslist": devices
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
