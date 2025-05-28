import requests
from flask import Flask, jsonify, request
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
        return connection
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

def get_device_info(devicename):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cursor:
            if devicename.startswith("CU"):
                table = "CUdevicelist"
            elif devicename.startswith("DU"):
                table = "DUdevicelist"
            elif devicename.startswith("RU"):
                table = "RUdevicelist"
            else:
                return None

            cursor.execute(f"SELECT model, IP, Port, ran_id, Greigns_id FROM {table} WHERE devicename = %s", (devicename,))
            result = cursor.fetchone()
            if result:
                return {
                    "model": result[0],
                    "ip": result[1],
                    "port": result[2],
                    "ran_id": result[3],
                    "greigns_id": result[4]
                }
    finally:
        conn.close()
    return None

def update_device_model_by_ran_id(ran_id, model_value):
    db_connection = get_db_connection()
    if not db_connection:
        return False
    try:
        with db_connection.cursor() as cursor:
            cursor.execute("UPDATE CUdevicelist SET model = %s WHERE ran_id = %s", (model_value, ran_id))
            cursor.execute("UPDATE DUdevicelist SET model = %s WHERE ran_id = %s", (model_value, ran_id))
            db_connection.commit()
            return True
    except Exception as e:
        print(f"Failed to update model for ran_id {ran_id}: {e}")
        return False
    finally:
        db_connection.close()

def update_device_model(devicename, model_value):
    db_connection = get_db_connection()
    if not db_connection:
        return False
    try:
        with db_connection.cursor() as cursor:
            if devicename.startswith("RU"):
                table = "RUdevicelist"
            elif devicename.startswith("CU"):
                table = "CUdevicelist"
            elif devicename.startswith("DU"):
                table = "DUdevicelist"
            else:
                return False
            sql = f"UPDATE {table} SET model = %s WHERE devicename = %s"
            cursor.execute(sql, (model_value, devicename))
            db_connection.commit()
            return True
    except Exception as e:
        print(f"Failed to update model for {devicename}: {e}")
        return False
    finally:
        db_connection.close()

@app.route('/api/v1/ORAN/ru', methods=['PUT'])
def control_ru_power():
    data = request.json
    devicename = data.get('devicename')
    model = data.get('model')

    if not devicename or not model:
        return jsonify({"error": "Missing devicename or model parameter"}), 400

    device_info = get_device_info(devicename)
    if not device_info:
        return jsonify({"error": "Device not found in database"}), 404

    is_indoor = devicename.startswith("RUi")

    if is_indoor:
        tx_power_map = {
            "1": "24", "2": "22", "3": "20", "4": "18", "5": "16", "6": "14", "7": "12", "8": "10"
        }
    else:
        tx_power_map = {
            "1": "37", "2": "35", "3": "33", "4": "31", "5": "29", "6": "27", "7": "25", "8": "23"
        }

    tx_power = tx_power_map.get(str(model))
    if not tx_power:
        return jsonify({"error": "Invalid model parameter"}), 400

    target_antenna = device_info.get("greigns_id")
    if not target_antenna:
        return jsonify({"error": "Missing greigns_id in device info"}), 400

    url = f"https://{device_info['ip']}:{device_info['port']}/api/mplane-proxy/oran-mp/operation/tx-power/{target_antenna}"

    try:
        with session.post(url, json={"tx_power": tx_power}, verify=config.VERIFY_SSL) as response:
            if response.status_code == 200:
                response_data = response.json()
                updated = update_device_model(devicename, int(model))
                if updated:
                    return jsonify({"response": response_data}), 200
                else:
                    return jsonify({"error": "Failed to update database"}), 500
            else:
                return jsonify({
                    "error": f"Failed to set tx_power. Status code: {response.status_code}",
                    "details": response.text
                }), 500
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/ORAN/cu', methods=['PUT'])
def control_cu_du_energy():
    data = request.json
    devicename = data.get('devicename')
    model = data.get('model')

    if not devicename or not model:
        return jsonify({"error": "Missing devicename or model parameter"}), 400

    device_info = get_device_info(devicename)
    if not device_info or not device_info.get("ran_id"):
        return jsonify({"error": "Invalid device or missing ran_id"}), 404

    action = "enable" if model == "1" else "disable"
    url = f"https://{device_info['ip']}:{device_info['port']}/api/v2/idle-state/bbu/{action}"

    try:
        with session.get(url, verify=config.VERIFY_SSL) as response:
            if response.status_code == 200:
                updated = update_device_model_by_ran_id(device_info['ran_id'], int(model))
                if updated:
                    return jsonify({"message": f"CU and DU under {device_info['ran_id']} set to model {model}"}), 200
                else:
                    return jsonify({"error": "Failed to update database"}), 500
            else:
                return jsonify({
                    "error": f"Failed to call energy saving API. Status code: {response.status_code}",
                    "details": response.text
                }), 500
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
