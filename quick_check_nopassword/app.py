from flask import Flask, request, jsonify
import xml.etree.ElementTree as ET
import requests
from ncclient import manager
import config  # 引用配置文件
from datetime import datetime, timedelta

app = Flask(__name__)

# Function to check if InfluxDB is alive
def check_influxdb_status():
    """
    檢查 InfluxDB 是否活著（通過 /ping API）。
    """
    url = f"{config.INFLUXDB_URL}/ping"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 204:  # InfluxDB /ping 成功返回 204
            return True
        return False
    except Exception as e:
        print(f"InfluxDB status check failed: {e}")
        return False

# Function to execute NETCONF command and parse data
def get_bbu_info():
    """
    從 NETCONF 取得 BBU 資訊。
    """
    try:
        with manager.connect(**config.device_params, hostkey_verify=False) as m:
            print("NETCONF Session Connected Successfully.")
            get_reply = m.get(filter=('subtree', config.filter_str))
            root = ET.fromstring(str(get_reply))
            namespaces = {'multiran': 'urn:reign-altran-o1-cm-multiran:1.0'}

            ran_data = {}
            for multiran_cm in root.findall('.//multiran:multiran-cm', namespaces):
                ran_id = multiran_cm.find('multiran:ran-id', namespaces).text
                ran_data[ran_id] = {"status": "ok"}
            return ran_data
    except Exception as e:
        print(f"Failed to retrieve BBU Info from NETCONF: {e}")
        return None

# Function to check InfluxDB data availability
def check_influxdb_data_consistency(measurement):
    """
    檢查 InfluxDB 最新一筆數據的參數數量是否與前 60 筆數據中的任意一筆一致。
    """
    query = f'''
    from(bucket: "{config.INFLUXDB_BUCKET_1}")
      |> range(start: -24h)
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> sort(columns: ["_time"], desc: true)
      |> limit(n: 60)
    '''
    headers = {
        "Authorization": f"Token {config.INFLUXDB_TOKEN}",
        "Content-Type": "application/vnd.flux"
    }
    url = f"{config.INFLUXDB_URL}/api/v2/query?org={config.INFLUXDB_ORG}"

    try:
        response = requests.post(url, headers=headers, data=query.encode('utf-8'))
        if response.status_code != 200:
            print(f"InfluxDB query failed: {response.text}")
            return False

        # 解析響應數據並統計每條記錄的參數數量
        lines = response.text.strip().split("\n")
        param_count_list = []

        for line in lines:
            if not line.startswith("_result") and line.strip():  # 過濾非數據行和空行
                param_count_list.append(len(line.split(",")))

        # 檢查數據一致性
        if len(param_count_list) < 2:
            return False  # 不足以比較數據

        latest_param_count = param_count_list[0]  # 最新一筆數據的參數數量
        for count in param_count_list[1:]:
            if count == latest_param_count:
                return True  # 找到一致的數據
        return False
    except Exception as e:
        print(f"Error checking InfluxDB data consistency: {e}")
        return False

@app.route('/api/v1/ORAN/quick_check', methods=['GET'])
def quick_check():
    """
    進行 BBU_Info 和 InfluxDB 狀態檢查。
    """
    report_time = (datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Check BBU Info
    bbu_info = get_bbu_info()
    if not bbu_info or len(bbu_info) == 0:
        return jsonify({
            "reporttime": report_time,
            "status": "error",
            "message": "Failed to retrieve BBU Info from NETCONF."
        }), 400

    # Step 2: Check if InfluxDB is alive
    if not check_influxdb_status():
        return jsonify({
            "reporttime": report_time,
            "status": "error",
            "message": "InfluxDB is not reachable or is down."
        }), 400

    # Step 3: Check InfluxDB data for each measurement
    measurements = ["CU01001", "DU01001"]
    for measurement in measurements:
        result = check_influxdb_data_consistency(measurement)
        if not result:
            return jsonify({
                "reporttime": report_time,
                "status": "error",
                "message": f"No data with matching parameter count for {measurement} in the last 60 records."
            }), 400

    return jsonify({
        "reporttime": report_time,
        "status": "success",
        "message": "BBU Info and InfluxDB data checks passed successfully."
    }), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
