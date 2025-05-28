from flask import Flask, request, jsonify
import pymysql
import base64
from functools import wraps
import datetime
import config  # 引入配置文件

app = Flask(__name__)

#USERNAME = config.USERNAME
#PASSWORD = config.PASSWORD

def authenticate(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('AIadmin')
        if auth_header:
            decoded_credentials = base64.b64decode(auth_header).decode('utf-8')
            username, password = decoded_credentials.split(':')
            if username == USERNAME and password == PASSWORD:
                return func(*args, **kwargs)
        return jsonify({'status': 'Unauthorized'}), 401
    return decorated_function

def get_device_table(devicename):
    if devicename.startswith("CU"):
        return "CUdevicelist"
    elif devicename.startswith("DU"):
        return "DUdevicelist"
    elif devicename.startswith("RU") or devicename.startswith("RUi"):
        return "RUdevicelist"
    elif devicename.startswith("PDU"):
        return "PDUdevicelist"
    return None

@app.route('/api/v1/ORAN/web', methods=['POST'])
#@authenticate
def register_device():
    try:
        data = request.get_json()
        required_fields = ["devicename", "deviceid", "IP", "Port", "Greigns_id", "ran_id"]
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        devicename = data["devicename"]
        device_type = get_device_table(devicename)
        if not device_type:
            return jsonify({"error": "Unsupported device type"}), 400

        connection = pymysql.connect(
            host=config.DB_HOST,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_DATABASE,
            cursorclass=pymysql.cursors.DictCursor
        )

        with connection.cursor() as cursor:
            check_sql = f"SELECT * FROM {device_type} WHERE devicename = %s"
            cursor.execute(check_sql, (devicename,))
            existing = cursor.fetchone()

            if existing:
                return jsonify({"error": "Device already registered"}), 400

            insert_sql = f'''
                INSERT INTO {device_type} (devicename, deviceid, IP, Port, Greigns_id, ran_id, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            '''
            cursor.execute(insert_sql, (
                devicename,
                data["deviceid"],
                data["IP"],
                data["Port"],
                data["Greigns_id"],
                data["ran_id"]
            ))
            connection.commit()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/ORAN/web', methods=['PUT'])
#@authenticate
def update_device():
    try:
        data = request.get_json()
        devicename = data.get("devicename")
        device_type = get_device_table(devicename)
        if not device_type:
            return jsonify({"error": "Unsupported device type"}), 400

        update_fields = ["deviceid", "IP", "Port", "Greigns_id", "ran_id"]
        update_values = [data.get(field) for field in update_fields if field in data]

        if not update_values:
            return jsonify({"error": "No fields to update"}), 400

        set_clause = ", ".join(f"{field} = %s" for field in update_fields if field in data)
        update_sql = f"UPDATE {device_type} SET {set_clause}, updated_at = NOW() WHERE devicename = %s"

        connection = pymysql.connect(
            host=config.DB_HOST,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_DATABASE,
            cursorclass=pymysql.cursors.DictCursor
        )

        with connection.cursor() as cursor:
            cursor.execute(update_sql, update_values + [devicename])
            connection.commit()

        return jsonify({"status": "updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/ORAN/web', methods=['DELETE'])
#@authenticate
def delete_device():
    try:
        data = request.get_json()
        devicename = data.get("devicename")
        device_type = get_device_table(devicename)
        if not device_type:
            return jsonify({"error": "Unsupported device type"}), 400

        delete_sql = f"DELETE FROM {device_type} WHERE devicename = %s"

        connection = pymysql.connect(
            host=config.DB_HOST,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_DATABASE,
            cursorclass=pymysql.cursors.DictCursor
        )

        with connection.cursor() as cursor:
            cursor.execute(delete_sql, (devicename,))
            connection.commit()

        return jsonify({"status": "deleted"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
